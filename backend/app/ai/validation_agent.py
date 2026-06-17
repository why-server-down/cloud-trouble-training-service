"""
ValidationAgent - LLM 기반 AI 시나리오 완료 판정.
K8s 현재 상태를 직접 수집하여 LLM에게 해결 여부 판단 요청.

검증 3단계 중 마지막:
  1. ValidationRuleService.check_rules() - DB 저장 k8s 룰
  2. k8s_check_by_fault_type() - fault_type → K8s API mechanical check
  3. ValidationAgent.judge() - LLM이 전체 namespace 상태 보고 최종 판정
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from app.core.config import settings

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

_VALIDATION_SYSTEM_PROMPT = """\
You are a Kubernetes incident validator. Determine if a user has successfully resolved a Kubernetes failure scenario.

You will receive:
1. Scenario context: title, fault type, what was broken, expected solution
2. Current Kubernetes state: deployments, pods, services, endpoints, recent warning events

Respond ONLY with a JSON object:
{"resolved": true|false, "reason": "한국어로 1-2문장 설명", "confidence": 0.0~1.0}

Decision rules:
- resolved=true: primary fault clearly fixed (pods running & ready, services have ready endpoints, no crash loops)
- resolved=false: pods still in error state OR restart count high OR service has 0 endpoints when it should have some
- Be strict: partial fixes do not count
- confidence: how certain you are given the available state (lower if state info is incomplete)
"""


@dataclass
class ValidationJudgment:
    resolved: bool
    reason: str
    confidence: float = 1.0


def _collect_k8s_state(namespace: str) -> dict:
    """namespace의 K8s 현재 상태 수집 (동기, executor에서 실행)."""
    try:
        from kubernetes import client, config as k8s_config
        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()

        apps_api = client.AppsV1Api()
        core_api = client.CoreV1Api()

        deployments = []
        try:
            for dep in apps_api.list_namespaced_deployment(namespace=namespace).items:
                deployments.append({
                    "name": dep.metadata.name,
                    "desired": dep.spec.replicas,
                    "ready": dep.status.ready_replicas or 0,
                    "available": dep.status.available_replicas or 0,
                })
        except Exception:
            pass

        pods = []
        try:
            for pod in core_api.list_namespaced_pod(namespace=namespace).items:
                containers = []
                for cs in (pod.status.container_statuses or []):
                    if cs.state.running:
                        state = "running"
                    elif cs.state.waiting:
                        state = f"waiting:{cs.state.waiting.reason}"
                    elif cs.state.terminated:
                        state = f"terminated:{cs.state.terminated.reason}"
                    else:
                        state = "unknown"
                    containers.append({
                        "name": cs.name,
                        "ready": cs.ready,
                        "restart_count": cs.restart_count,
                        "state": state,
                    })
                pods.append({
                    "name": pod.metadata.name,
                    "phase": pod.status.phase,
                    "ready": all(c["ready"] for c in containers),
                    "containers": containers,
                })
        except Exception:
            pass

        services = []
        try:
            for svc in core_api.list_namespaced_service(namespace=namespace).items:
                ep_ready = 0
                try:
                    ep = core_api.read_namespaced_endpoints(name=svc.metadata.name, namespace=namespace)
                    ep_ready = sum(len(s.addresses or []) for s in (ep.subsets or []))
                except Exception:
                    pass
                services.append({
                    "name": svc.metadata.name,
                    "selector": svc.spec.selector or {},
                    "endpoint_ready_count": ep_ready,
                })
        except Exception:
            pass

        events = []
        try:
            ev_list = core_api.list_namespaced_event(
                namespace=namespace, field_selector="type=Warning"
            )
            for ev in sorted(
                ev_list.items,
                key=lambda e: e.last_timestamp or "",
                reverse=True,
            )[:5]:
                events.append({
                    "reason": ev.reason,
                    "message": (ev.message or "")[:120],
                    "count": ev.count,
                })
        except Exception:
            pass

        return {
            "deployments": deployments,
            "pods": pods,
            "services": services,
            "recent_warning_events": events,
        }
    except Exception as e:
        return {"error": str(e)}


class MockValidationAgent:
    """Mock 모드: K8s 상태 직접 파싱으로 단순 판정 (LLM 없이)."""

    async def judge(self, scenario_context: dict, namespace: str) -> ValidationJudgment:
        state = await asyncio.get_event_loop().run_in_executor(
            None, _collect_k8s_state, namespace
        )

        for dep in state.get("deployments", []):
            if dep.get("available", 0) > 0:
                return ValidationJudgment(
                    resolved=True,
                    reason="Deployment가 정상 가용 상태입니다.",
                    confidence=0.8,
                )

        for svc in state.get("services", []):
            if svc.get("endpoint_ready_count", 0) > 0:
                return ValidationJudgment(
                    resolved=True,
                    reason="서비스 엔드포인트가 정상 연결되어 있습니다.",
                    confidence=0.8,
                )

        return ValidationJudgment(
            resolved=False,
            reason="아직 정상화 조건을 만족하지 못했습니다.",
            confidence=0.7,
        )


class LLMValidationAgent:
    """OpenAI / Gemini 기반 AI 판정."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url

    async def judge(self, scenario_context: dict, namespace: str) -> ValidationJudgment:
        state = await asyncio.get_event_loop().run_in_executor(
            None, _collect_k8s_state, namespace
        )

        try:
            import openai
            client_kwargs: dict = {"api_key": self._api_key}
            if self._base_url:
                client_kwargs["base_url"] = self._base_url
            client = openai.OpenAI(**client_kwargs)

            response = client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _VALIDATION_SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_prompt(scenario_context, state)},
                ],
                max_tokens=300,
                temperature=0.1,
                timeout=15.0,
            )

            data = json.loads(response.choices[0].message.content)
            return ValidationJudgment(
                resolved=bool(data.get("resolved", False)),
                reason=str(data.get("reason", "")),
                confidence=float(data.get("confidence", 0.5)),
            )

        except Exception as e:
            print(f"[ValidationAgent] LLM 호출 실패, K8s 상태 기반 fallback: {e}")
            return await MockValidationAgent().judge(scenario_context, namespace)

    def _build_prompt(self, scenario_context: dict, k8s_state: dict) -> str:
        return (
            f"## 시나리오 컨텍스트\n"
            f"제목: {scenario_context.get('title', '알 수 없음')}\n"
            f"장애 유형: {scenario_context.get('fault_type', '알 수 없음')}\n"
            f"시나리오 설명: {scenario_context.get('student_brief', '')}\n"
            f"내부 요약: {scenario_context.get('internal_summary', '')}\n\n"
            f"## 현재 Kubernetes 상태 (namespace: {scenario_context.get('namespace', '')})\n"
            f"```json\n{json.dumps(k8s_state, ensure_ascii=False, indent=2)}\n```\n\n"
            f"이 사용자가 장애를 성공적으로 해결했는지 판단해주세요."
        )


def get_validation_agent() -> MockValidationAgent | LLMValidationAgent:
    if settings.AI_BACKEND == "gemini" and settings.GEMINI_API_KEY:
        return LLMValidationAgent(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            base_url=_GEMINI_BASE_URL,
        )
    if settings.AI_BACKEND == "openai" and settings.OPENAI_API_KEY:
        return LLMValidationAgent(
            api_key=settings.OPENAI_API_KEY,
            model=settings.SCENARIO_MODEL,
        )
    return MockValidationAgent()
