"""
RuntimeContextCollector - AI 계층이 현재 환경 상태를 보고 답할 수 있도록
관측값을 모아 공통 스키마로 반환한다.

환경마다 수집 방법이 다르지만 **출력 스키마는 같다**. AI 담당이 환경별로 분기하지
않아도 되도록 하기 위한 계약이다(BE-19).

    {
      "environment": "docker",
      "scope": {"namespace": "...", "sandbox_id": "..."},
      "mission": {...},
      "recent_user_commands": [...],
      "observations": {...},   # 환경별 상태
      "metrics": {...},
      "logs": [...]
    }

원칙
  - 부분 실패를 허용한다. 수집 하나가 실패하거나 느려도 나머지는 그대로 넘긴다
  - 정답이 아니라 관측값만 넘긴다. 무엇이 문제인지는 AI 가 판단한다
  - 토큰·비밀번호·환경변수는 지운다(runtime_redaction)
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import environments
from app.core.config import settings
from app.models import CommandLog, TerminalSession
from app.services.runtime_redaction import redact

logger = logging.getLogger(__name__)


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
        environment: str = environments.KUBERNETES,
        sandbox=None,
    ) -> dict:
        """환경에 맞는 관측값을 모아 공통 스키마로 돌려준다.

        수집 하나가 실패해도 나머지는 그대로 넘긴다. 튜터 응답이 관측 실패 때문에
        통째로 막히면 안 된다.
        """
        recent_commands = await self._guard(
            self._collect_recent_commands(user_id, db), "recent_commands", default=[]
        )

        observations = await self._guard(
            self._collect_observations(environment, namespace, sandbox),
            "observations",
            default={},
        )

        metrics = {}
        if scenario_id is not None and environment == environments.KUBERNETES:
            prometheus = await self._guard(
                self._collect_prometheus(scenario_id, namespace, db),
                "prometheus",
                default=None,
            )
            if prometheus is not None:
                metrics["prometheus"] = prometheus

        context = {
            "environment": environment,
            "scope": {
                "namespace": namespace,
                "sandbox_id": getattr(sandbox, "id", None),
            },
            "mission": {
                "title": scenario_title,
                "difficulty": difficulty,
                "student_brief": student_brief,
            },
            "recent_user_commands": recent_commands,
            "observations": observations,
            "metrics": metrics,
            "logs": [],
        }

        # 기존 튜터 구현이 쓰는 키를 함께 남긴다. AI 담당이 새 스키마로 옮길 때까지
        # 양쪽이 같이 동작해야 한다(소유 경로가 달라 한 PR 에서 못 바꾼다).
        context["namespace"] = namespace
        context["kubernetes_state"] = observations.get("kubernetes_state")
        context["prometheus"] = metrics.get("prometheus")
        context["loki"] = None

        # AI 프로바이더로 나가기 전에 민감값을 지운다.
        return redact(context)

    # ── 부분 실패 허용 ────────────────────────────────────────────────────────

    async def _guard(self, awaitable, label: str, default):
        """수집 하나가 실패하거나 느려도 전체를 막지 않는다."""
        try:
            return await asyncio.wait_for(
                awaitable, timeout=settings.RUNTIME_CONTEXT_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.warning("runtime context collection timed out", extra={"part": label})
        except Exception:
            logger.exception("runtime context collection failed", extra={"part": label})
        return default

    # ── 환경별 관측 ───────────────────────────────────────────────────────────

    async def _collect_observations(self, environment: str, namespace: str, sandbox) -> dict:
        collector = self._OBSERVERS.get(environment)
        if collector is None:
            return {}
        return await collector(self, namespace, sandbox)

    async def _observe_kubernetes(self, namespace: str, sandbox) -> dict:
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(
            None, lambda: self._collect_k8s_state(namespace)
        )
        return {"kubernetes_state": state}

    async def _observe_docker(self, namespace: str, sandbox) -> dict:
        probes = {
            "containers": ["docker", "ps", "-a", "--format", "{{.Names}} {{.Status}}"],
            "networks": ["docker", "network", "ls", "--format", "{{.Name}}"],
        }
        return await self._probe_sandbox(namespace, sandbox, environments.DOCKER, probes)

    async def _observe_linux(self, namespace: str, sandbox) -> dict:
        probes = {
            "processes": ["sh", "-c", "ps -eo pid,stat,args | head -25"],
            "disk": ["sh", "-c", "df -h | head -10"],
            "memory": ["sh", "-c", "free -m"],
            "load": ["sh", "-c", "cat /proc/loadavg"],
        }
        return await self._probe_sandbox(namespace, sandbox, environments.LINUX, probes)

    async def _probe_sandbox(
        self, namespace: str, sandbox, environment: str, probes: dict
    ) -> dict:
        """샌드박스 안에서 읽기 전용 관측 명령을 돌린다.

        sandbox 가 없으면 서버가 DB 세션 값으로 복원한다. 클라이언트 값은 쓰지 않는다.
        """
        from app.services.sandbox_service import get_sandbox_service

        service = get_sandbox_service()
        if sandbox is None:
            sandbox = service.reference_for(
                user_id=namespace.removeprefix("user-"),
                namespace=namespace,
                environment=environment,
            )

        loop = asyncio.get_event_loop()
        observations = {}
        for key, argv in probes.items():
            try:
                observations[key] = await loop.run_in_executor(
                    None, lambda a=argv: service.exec_in_sandbox(sandbox, a).strip()
                )
            except Exception:
                # 관측 하나가 실패해도 나머지는 넘긴다.
                logger.warning(
                    "sandbox probe failed",
                    extra={"environment": environment, "probe": key},
                )
        return observations

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


RuntimeContextCollector._OBSERVERS = {
    environments.KUBERNETES: RuntimeContextCollector._observe_kubernetes,
    environments.DOCKER: RuntimeContextCollector._observe_docker,
    environments.LINUX: RuntimeContextCollector._observe_linux,
}


def get_runtime_context_collector() -> RuntimeContextCollector:
    global _collector
    if _collector is None:
        _collector = RuntimeContextCollector()
    return _collector
