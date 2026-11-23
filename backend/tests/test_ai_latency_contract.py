from app.core.config import Settings
from app.core.metrics import (
    AI_ESTIMATED_COST,
    AI_INGESTION_CHANGES,
    AI_RETRIEVAL_CONTAMINATION,
    AI_RETRIEVAL_RESULT_COUNT,
    AI_RETRIEVALS,
    AI_SCENARIO_CANDIDATES,
    AI_STAGE_DURATION,
    AI_TUTOR_RESULTS,
    AI_VALIDATION_AGREEMENT,
)
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


def test_token_cost_budget_defaults_are_bounded():
    settings = Settings(_env_file=None)
    assert settings.AI_MAX_CONTEXT_TOKENS == 9_000
    assert settings.AI_MAX_COMPLETION_TOKENS == 500
    assert settings.AI_MAX_RETRIEVED_CHUNKS == 5
    assert settings.AI_PROVIDER_MAX_ATTEMPTS == 2


def test_cost_metric_has_no_user_or_content_labels():
    assert AI_ESTIMATED_COST._labelnames == ("provider", "purpose", "model")


def test_ai_quality_metrics_use_only_bounded_labels():
    metrics = (
        AI_TUTOR_RESULTS, AI_RETRIEVALS, AI_RETRIEVAL_RESULT_COUNT,
        AI_RETRIEVAL_CONTAMINATION, AI_SCENARIO_CANDIDATES,
        AI_VALIDATION_AGREEMENT, AI_INGESTION_CHANGES,
    )
    forbidden = {"user_id", "attempt_id", "namespace", "question", "source", "title"}
    for metric in metrics:
        assert forbidden.isdisjoint(metric._labelnames)
