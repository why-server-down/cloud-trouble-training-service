"""AI 호출 관측 헬퍼. 저카디널리티 label만 사용한다."""
from __future__ import annotations

from app.core.metrics import AI_CALL_DURATION, AI_CALLS, AI_TOKENS


def record_ai_call(
    *, provider: str, purpose: str, result: str, duration_seconds: float,
    token_usage=None,
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
