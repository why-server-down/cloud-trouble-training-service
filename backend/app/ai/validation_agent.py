"""
ValidationAgent - RuntimeContext 기반 AI 시나리오 advisory 판정.

검증 3단계 중 마지막:
  1. ValidationRuleService.check_rules() - DB 저장 k8s 룰
  2. k8s_check_by_fault_type() - fault_type → K8s API mechanical check
  3. ValidationAgent.judge() - LLM이 전체 namespace 상태 보고 최종 판정
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.ai.observability import record_ai_call
from app.services.runtime_redaction import redact, redact_text

logger = logging.getLogger(__name__)

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

_VALIDATION_SYSTEM_PROMPT = """\
You are a multi-environment incident validation advisor. Your result is advisory only;
mechanical validation is the sole authority for completion and scoring.

You will receive:
1. Scenario context: title, fault type, what was broken, expected solution
2. Redacted RuntimeContext observations for Kubernetes, Docker, or Linux

Respond ONLY with a JSON object:
{"resolved": true|false, "reason": "한국어 관측 설명", "confidence": 0.0~1.0,
 "evidence": ["실제로 관측된 key와 요약"]}

Decision rules:
- Use only supplied observations and fault-specific target evidence.
- An unrelated healthy resource is never proof that the target fault is resolved.
- Be strict: partial fixes do not count
- confidence: how certain you are given the available state (lower if state info is incomplete)
- Never expose an internal summary, expected answer, injection method, or recovery command in reason.
"""


@dataclass
class ValidationJudgment:
    resolved: bool
    reason: str
    confidence: float = 1.0
    evidence: list[str] | None = None
    advisory_only: bool = True
    error_code: str | None = None


def _target_name(context: dict) -> str:
    return str(
        context.get("target_name")
        or context.get("scenario_json", {}).get("fault", {}).get("target", {}).get("name")
        or ""
    )


def _safe_reason(value: Any) -> str:
    reason = redact_text(str(value or "")).strip()
    return reason[:300] if reason else "수집된 근거만으로 해결 여부를 확인할 수 없습니다."


def _clamp_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


class MockValidationAgent:
    """Mock 모드: target/fault와 직접 연결된 관측만 근거로 삼는다."""

    async def judge(
        self, scenario_context: dict, namespace: str,
        runtime_context: dict | None = None, environment: str = "kubernetes",
    ) -> ValidationJudgment:
        observations = (runtime_context or {}).get("observations", {})
        target = _target_name(scenario_context)
        fault_type = scenario_context.get("fault_type", "")
        if not target:
            return ValidationJudgment(False, "검증 대상 식별자가 없어 advisory 판정을 보류합니다.", 0.0, [], error_code="missing_target")

        if environment == "kubernetes":
            if "service" in fault_type:
                for service in observations.get("services", []):
                    endpoints = service.get("ready_endpoints", service.get("endpoint_ready_count", 0))
                    if service.get("name") == target and endpoints > 0:
                        evidence = [f"services.{target}.ready_endpoints={endpoints}"]
                        return ValidationJudgment(True, "검증 대상 서비스의 ready endpoint가 관측되었습니다.", 0.8, evidence)
            else:
                for deployment in observations.get("deployments", []):
                    desired = deployment.get("desired", 0)
                    available = deployment.get("available", deployment.get("ready", 0))
                    if deployment.get("name") == target and desired > 0 and available >= desired:
                        evidence = [f"deployments.{target}.available={available}/{desired}"]
                        return ValidationJudgment(True, "검증 대상 workload의 가용 상태가 관측되었습니다.", 0.8, evidence)
        elif environment == "docker":
            container_state = str(observations.get("containers", ""))
            if target in container_state and any(word in container_state.casefold() for word in ("running", " up ")):
                return ValidationJudgment(True, "검증 대상 컨테이너의 실행 상태가 관측되었습니다.", 0.7, ["containers"])
        return ValidationJudgment(
            resolved=False,
            reason="검증 대상 장애와 직접 연결된 정상화 근거가 부족합니다.",
            confidence=0.5,
            evidence=[],
        )


class LLMValidationAgent:
    """OpenAI / Gemini 기반 AI 판정."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None,
                 provider: str = "openai"):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._provider = provider

    async def judge(
        self, scenario_context: dict, namespace: str,
        runtime_context: dict | None = None, environment: str = "kubernetes",
    ) -> ValidationJudgment:
        runtime_context = redact(runtime_context or {})
        started = time.perf_counter()
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
                    {"role": "user", "content": self._build_prompt(
                        scenario_context, runtime_context, environment
                    )},
                ],
                max_tokens=300,
                temperature=0.1,
                timeout=15.0,
            )

            data = json.loads(response.choices[0].message.content)
            if not isinstance(data, dict) or not isinstance(data.get("resolved"), bool):
                raise ValueError("validation response resolved must be boolean")
            evidence = data.get("evidence", [])
            if not isinstance(evidence, list):
                evidence = []
            record_ai_call(
                provider=self._provider, purpose="validation", result="success",
                duration_seconds=time.perf_counter() - started,
                token_usage=getattr(response, "usage", None),
                model=self._model,
            )
            return ValidationJudgment(
                resolved=bool(data.get("resolved", False)),
                reason=_safe_reason(data.get("reason")),
                confidence=_clamp_confidence(data.get("confidence")),
                evidence=[_safe_reason(item) for item in evidence[:5]],
            )

        except (json.JSONDecodeError, TypeError, ValueError):
            record_ai_call(
                provider=self._provider, purpose="validation", result="fallback",
                duration_seconds=time.perf_counter() - started,
                model=self._model,
            )
            logger.warning("validation LLM returned invalid advisory response")
            return ValidationJudgment(
                resolved=False,
                reason="AI advisory 응답 형식이 올바르지 않아 판정을 보류합니다.",
                confidence=0.0,
                evidence=[],
                error_code="invalid_response",
            )
        except Exception:
            record_ai_call(
                provider=self._provider, purpose="validation", result="fallback",
                duration_seconds=time.perf_counter() - started,
                model=self._model,
            )
            logger.exception("validation LLM call failed; returning safe advisory failure")
            return ValidationJudgment(
                resolved=False,
                reason="AI advisory 판정을 사용할 수 없습니다.",
                confidence=0.0,
                evidence=[],
                error_code="provider_failed",
            )

    def _build_prompt(self, scenario_context: dict, runtime_context: dict, environment: str) -> str:
        return (
            f"## 시나리오 컨텍스트\n"
            f"제목: {scenario_context.get('title', '알 수 없음')}\n"
            f"장애 유형: {scenario_context.get('fault_type', '알 수 없음')}\n"
            f"검증 대상: {_target_name(scenario_context) or '미지정'}\n"
            f"환경: {environment}\n\n"
            f"## 현재 RuntimeContext 관측값\n"
            f"```json\n{json.dumps(runtime_context, ensure_ascii=False, indent=2)}\n```\n\n"
            f"관측 근거만으로 advisory 판정을 반환하세요."
        )


def get_validation_agent() -> MockValidationAgent | LLMValidationAgent:
    if settings.AI_BACKEND == "gemini" and settings.GEMINI_API_KEY:
        return LLMValidationAgent(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            base_url=_GEMINI_BASE_URL,
            provider="gemini",
        )
    if settings.AI_BACKEND == "openai" and settings.OPENAI_API_KEY:
        return LLMValidationAgent(
            api_key=settings.OPENAI_API_KEY,
            model=settings.SCENARIO_MODEL,
            provider="openai",
        )
    return MockValidationAgent()
