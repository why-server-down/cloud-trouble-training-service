import ast
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai import observability


class _Metric:
    def __init__(self):
        self.labels_seen = []
        self.values = []

    def labels(self, **labels):
        self.labels_seen.append(labels)
        return self

    def inc(self, value=1):
        self.values.append(value)

    def observe(self, value):
        self.values.append(value)


def test_record_ai_call_uses_only_provider_purpose_result_and_token_kind(monkeypatch):
    calls, duration, tokens = _Metric(), _Metric(), _Metric()
    monkeypatch.setattr(observability, "AI_CALLS", calls)
    monkeypatch.setattr(observability, "AI_CALL_DURATION", duration)
    monkeypatch.setattr(observability, "AI_TOKENS", tokens)

    observability.record_ai_call(
        provider="openai", purpose="tutor", result="success", duration_seconds=0.25,
        token_usage={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    )

    assert calls.labels_seen == [{"provider": "openai", "purpose": "tutor", "result": "success"}]
    assert duration.labels_seen == [{"provider": "openai", "purpose": "tutor"}]
    assert {labels["kind"] for labels in tokens.labels_seen} == {"prompt", "completion", "total"}
    assert all(set(labels) == {"provider", "purpose", "kind"} for labels in tokens.labels_seen)


def test_record_ai_call_accepts_openai_usage_object(monkeypatch):
    tokens = _Metric()
    monkeypatch.setattr(observability, "AI_CALLS", _Metric())
    monkeypatch.setattr(observability, "AI_CALL_DURATION", _Metric())
    monkeypatch.setattr(observability, "AI_TOKENS", tokens)
    observability.record_ai_call(
        provider="gemini", purpose="scenario", result="success", duration_seconds=0.1,
        token_usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
    )
    assert tokens.values == [3, 2, 5]


def test_record_ai_call_estimates_known_model_cost_without_user_labels(monkeypatch):
    cost = _Metric()
    monkeypatch.setattr(observability, "AI_CALLS", _Metric())
    monkeypatch.setattr(observability, "AI_CALL_DURATION", _Metric())
    monkeypatch.setattr(observability, "AI_TOKENS", _Metric())
    monkeypatch.setattr(observability, "AI_ESTIMATED_COST", cost)
    observability.record_ai_call(
        provider="openai", purpose="tutor", result="success", duration_seconds=0.1,
        token_usage={"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        model="gpt-4o-mini",
    )
    assert cost.labels_seen == [{
        "provider": "openai", "purpose": "tutor", "model": "gpt-4o-mini"
    }]
    assert cost.values == [0.75]


def test_stage_metric_has_only_bounded_pipeline_labels(monkeypatch):
    duration = _Metric()
    monkeypatch.setattr(observability, "AI_STAGE_DURATION", duration)
    observability.record_ai_stage(
        provider="openai", model="gpt-4o-mini", environment="docker",
        hint_level=9, stage="retrieval", result="success", duration_ms=125,
    )
    assert duration.labels_seen == [{
        "provider": "openai", "model": "gpt-4o-mini", "environment": "docker",
        "hint_level": "3", "stage": "retrieval", "result": "success",
    }]
    assert duration.values == [0.125]


def test_ai_owned_code_has_no_print_calls():
    offenders = []
    for path in (BACKEND / "app" / "ai").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


def test_all_llm_purposes_are_instrumented():
    sources = {
        "tutor": (BACKEND / "app" / "ai" / "tutor_service.py").read_text(),
        "scenario": (BACKEND / "app" / "ai" / "scenario_agent.py").read_text(),
        "validation": (BACKEND / "app" / "ai" / "validation_agent.py").read_text(),
    }
    for purpose, source in sources.items():
        assert "record_ai_call(" in source
        assert f'purpose="{purpose}"' in source
