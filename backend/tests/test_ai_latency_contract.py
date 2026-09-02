from app.core.config import Settings
from app.core.metrics import AI_STAGE_DURATION
from app.schemas import TutorResult


def test_ai_pipeline_timeouts_have_independent_defaults():
    settings = Settings(_env_file=None)
    assert settings.CONTEXT_COLLECTION_TIMEOUT == 3.0
    assert settings.RAG_SEARCH_TIMEOUT == 2.0
    assert settings.OPENAI_TIMEOUT == 10.0


def test_stage_metric_uses_only_bounded_operational_labels():
    assert AI_STAGE_DURATION._labelnames == (
        "provider", "model", "environment", "hint_level", "stage", "result"
    )
    for forbidden in ("user_id", "attempt_id", "namespace", "question"):
        assert forbidden not in AI_STAGE_DURATION._labelnames


def test_tutor_result_carries_latency_breakdown():
    result = TutorResult(
        message="힌트", latency_ms=120,
        latency_breakdown={"context_ms": 30.0, "retrieval_ms": 20.0, "llm_ms": 70.0},
    )
    assert result.latency_breakdown["llm_ms"] == 70.0
