"""
RuntimeContextCollector - AI 튜터가 현재 클러스터 상태를 보고 답할 수 있도록
K8s / Prometheus / CommandLog를 수집해 컨텍스트 dict로 반환.

Phase 4: K8s state + Prometheus validation 수집 구현
Phase 5: Loki log 수집 추가 예정
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CommandLog, TerminalSession


class RuntimeContextCollector:

    async def collect(
        self,
        user_id: uuid.UUID,
        namespace: str,
        db: AsyncSession,
        scenario_title: str = "",
        student_brief: str = "",
        difficulty: str = "",
        scenario_id: uuid.UUID | None = None,
    ) -> dict:
        recent_commands = await self._collect_recent_commands(user_id, db)

        loop = asyncio.get_event_loop()
        k8s_state = await loop.run_in_executor(
            None, lambda: self._collect_k8s_state(namespace)
        )

        prometheus_result = None
        if scenario_id is not None:
            prometheus_result = await self._collect_prometheus(scenario_id, namespace, db)

        return {
            "namespace": namespace,
            "mission": {
                "title": scenario_title,
                "difficulty": difficulty,
                "student_brief": student_brief,
            },
            "recent_user_commands": recent_commands,
            "kubernetes_state": k8s_state,
            "prometheus": prometheus_result,
            "loki": None,  # Phase 5
        }

    # ── K8s state ─────────────────────────────────────────────────────────────

    def _collect_k8s_state(self, namespace: str) -> dict | None:
        try:
            from kubernetes import client, config as k8s_config
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

            apps_api = client.AppsV1Api()
            core_api = client.CoreV1Api()

            pods = self._collect_pods(core_api, namespace)
            deployments = self._collect_deployments(apps_api, namespace)
            services = self._collect_services(core_api, namespace)
            events = self._collect_events(core_api, namespace)

            return {
                "pods": pods,
                "deployments": deployments,
                "services": services,
                "recent_events": events,
            }
        except Exception as e:
            return {"error": f"K8s 조회 실패: {e}"}

    def _collect_pods(self, core_api, namespace: str) -> list[dict]:
        pods = []
        for pod in core_api.list_namespaced_pod(namespace=namespace).items:
            phase = pod.status.phase or "Unknown"
            ready = False
            restarts = 0
            for cs in (pod.status.container_statuses or []):
                restarts += cs.restart_count or 0
                ready = cs.ready or False
                if cs.state.waiting:
                    phase = cs.state.waiting.reason or "Waiting"
                elif cs.state.terminated:
                    phase = f"Terminated({cs.state.terminated.reason or ''})"
            pods.append({
                "name": pod.metadata.name,
                "phase": phase,
                "ready": ready,
                "restarts": restarts,
                "labels": pod.metadata.labels or {},
            })
        return pods

    def _collect_deployments(self, apps_api, namespace: str) -> list[dict]:
        deps = []
        for dep in apps_api.list_namespaced_deployment(namespace=namespace).items:
            deps.append({
                "name": dep.metadata.name,
                "available": dep.status.available_replicas or 0,
                "desired": dep.spec.replicas or 0,
            })
        return deps

    def _collect_services(self, core_api, namespace: str) -> list[dict]:
        svcs = []
        for svc in core_api.list_namespaced_service(namespace=namespace).items:
            try:
                ep = core_api.read_namespaced_endpoints(
                    name=svc.metadata.name, namespace=namespace
                )
                ready_count = sum(
                    len(subset.addresses or [])
                    for subset in (ep.subsets or [])
                )
            except Exception:
                ready_count = 0
            svcs.append({
                "name": svc.metadata.name,
                "selector": svc.spec.selector or {},
                "ready_endpoints": ready_count,
            })
        return svcs

    def _collect_events(self, core_api, namespace: str) -> list[str]:
        event_list = core_api.list_namespaced_event(namespace=namespace)
        warnings = [e for e in event_list.items if e.type == "Warning"]
        sorted_events = sorted(
            warnings,
            key=lambda e: e.last_timestamp.isoformat() if e.last_timestamp else "",
            reverse=True,
        )
        return [
            f"{e.reason}: {e.message[:120]}"
            for e in sorted_events[:5]
            if e.message
        ]

    # ── Prometheus validation results ─────────────────────────────────────────

    async def _collect_prometheus(
        self,
        scenario_id: uuid.UUID,
        namespace: str,
        db: AsyncSession,
    ) -> dict | None:
        try:
            from app.services.validation_rule_service import ValidationRuleService
            from app.core.config import settings
            vrs = ValidationRuleService(prometheus_url=settings.PROMETHEUS_URL)
            _, rule_results = await vrs.check_rules(
                scenario_id=scenario_id,
                namespace=namespace,
                db=db,
                use_mock=False,
            )
            return {
                "validation_results": [
                    {"rule": r.name, "passed": r.passed, "value": r.last_value}
                    for r in rule_results
                ]
            }
        except Exception as e:
            return {"error": f"Prometheus 조회 실패: {e}"}

    # ── CommandLog ────────────────────────────────────────────────────────────

    async def _collect_recent_commands(
        self, user_id: uuid.UUID, db: AsyncSession, limit: int = 10
    ) -> list[dict]:
        result = await db.execute(
            select(TerminalSession)
            .where(TerminalSession.user_id == user_id, TerminalSession.is_active == True)  # noqa: E712
            .order_by(TerminalSession.last_activity.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()
        if not session:
            return []

        logs_result = await db.execute(
            select(CommandLog)
            .where(CommandLog.session_id == session.id)
            .order_by(CommandLog.executed_at.desc())
            .limit(limit)
        )
        logs = logs_result.scalars().all()
        return [
            {
                "command": log.command,
                "exit_code": log.exit_code,
                "output_summary": log.output[:200] if log.output else "",
            }
            for log in reversed(logs)
        ]


# ── 컨텍스트 → 프롬프트 문자열 변환 유틸 ─────────────────────────────────────

def format_k8s_state(k8s_state: dict | None) -> str:
    """K8s state dict를 LLM 프롬프트용 텍스트로 변환."""
    if not k8s_state:
        return "K8s 상태 미수집 (mock 환경)"
    if "error" in k8s_state:
        return k8s_state["error"]

    lines = []

    for dep in k8s_state.get("deployments", []):
        lines.append(f"[Deployment] {dep['name']}: {dep['available']}/{dep['desired']} available")

    for pod in k8s_state.get("pods", []):
        mark = "✓" if pod["ready"] else "✗"
        lines.append(
            f"[Pod] [{mark}] {pod['name']}: {pod['phase']} (재시작={pod['restarts']})"
        )

    for svc in k8s_state.get("services", []):
        lines.append(
            f"[Service] {svc['name']}: endpoints={svc['ready_endpoints']}, selector={svc['selector']}"
        )

    return "\n".join(lines) if lines else "리소스 없음"


def format_recent_commands(commands: list[dict]) -> str:
    """최근 명령 이력을 LLM 프롬프트용 텍스트로 변환."""
    if not commands:
        return "(명령 이력 없음)"
    lines = []
    for cmd in commands[-5:]:
        exit_info = f"[exit={cmd['exit_code']}]" if cmd.get("exit_code") is not None else ""
        summary = cmd.get("output_summary", "")
        line = f"$ {cmd['command']} {exit_info}"
        if summary:
            line += f"\n  → {summary[:100]}"
        lines.append(line)
    return "\n".join(lines)


def format_events(k8s_state: dict | None) -> str:
    """최근 K8s 이벤트 + Prometheus 검증 결과를 텍스트로 변환."""
    parts = []

    if k8s_state and "recent_events" in k8s_state:
        events = k8s_state["recent_events"]
        if events:
            parts.append("=== K8s Warning Events ===")
            parts.extend(f"  {e}" for e in events)
        else:
            parts.append("(최근 Warning 이벤트 없음)")

    return "\n".join(parts) if parts else "(이벤트 없음)"


_collector: RuntimeContextCollector | None = None


def get_runtime_context_collector() -> RuntimeContextCollector:
    global _collector
    if _collector is None:
        _collector = RuntimeContextCollector()
    return _collector
