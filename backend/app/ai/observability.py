"""AI 호출 관측 헬퍼. 저카디널리티 label만 사용한다."""
from __future__ import annotations

from app.core.metrics import (
    AI_CALL_DURATION, AI_CALLS, AI_ESTIMATED_COST, AI_STAGE_DURATION, AI_TOKENS,
)

_PRICE_PER_MILLION = {
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}


def record_ai_call(
    *, provider: str, purpose: str, result: str, duration_seconds: float,
    token_usage=None, model: str = "unknown",
) -> None:
    AI_CALLS.labels(provider=provider, purpose=purpose, result=result).inc()
    AI_CALL_DURATION.labels(provider=provider, purpose=purpose).observe(duration_seconds)
    if token_usage is None:
        return
    values = {
        "prompt": getattr(token_usage, "prompt_tokens", None),
        "completion": getattr(token_usage, "completion_tokens", None),
        "total": getattr(token_usage, "total_tokens", None),
    }
    if isinstance(token_usage, dict):
        values = {
            "prompt": token_usage.get("prompt_tokens"),
            "completion": token_usage.get("completion_tokens"),
            "total": token_usage.get("total_tokens"),
        }
    for kind, value in values.items():
        if value is not None:
            AI_TOKENS.labels(provider=provider, purpose=purpose, kind=kind).inc(value)
    normalized_model = model.removeprefix("models/")
    prices = _PRICE_PER_MILLION.get(normalized_model)
    if prices and values["prompt"] is not None and values["completion"] is not None:
        estimated_usd = (
            float(values["prompt"]) * prices[0]
            + float(values["completion"]) * prices[1]
        ) / 1_000_000
        AI_ESTIMATED_COST.labels(
            provider=provider, purpose=purpose, model=normalized_model,
        ).inc(estimated_usd)


def record_ai_stage(
    *, provider: str, model: str, environment: str, hint_level: int,
    stage: str, result: str, duration_ms: float,
) -> None:
    AI_STAGE_DURATION.labels(
        provider=provider,
        model=model,
        environment=environment,
        hint_level=str(max(0, min(3, hint_level))),
        stage=stage,
        result=result,
    ).observe(max(0.0, duration_ms) / 1000)
