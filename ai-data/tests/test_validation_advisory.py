import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai.validation_agent import LLMValidationAgent, MockValidationAgent


def _context(fault_type="crash_loop", target="nginx"):
    return {
        "title": "장애 훈련",
        "fault_type": fault_type,
        "scenario_json": {"fault": {"target": {"name": target}}},
        "internal_summary": "정답은 deployment를 patch하는 것입니다",
    }


@pytest.mark.asyncio
async def test_unrelated_healthy_deployment_is_not_resolution_evidence():
    judgment = await MockValidationAgent().judge(
        _context(target="broken-app"), "user-test",
        runtime_context={"observations": {"deployments": [
            {"name": "healthy-app", "desired": 1, "available": 1}
        ]}},
        environment="kubernetes",
    )
    assert judgment.resolved is False
    assert judgment.evidence == []


@pytest.mark.asyncio
async def test_fault_specific_target_evidence_can_support_advisory_true():
    judgment = await MockValidationAgent().judge(
        _context(fault_type="service_selector_mismatch", target="web-svc"), "user-test",
        runtime_context={"observations": {"services": [
            {"name": "web-svc", "ready_endpoints": 2}
        ]}},
        environment="kubernetes",
    )
    assert judgment.resolved is True
    assert judgment.evidence == ["services.web-svc.ready_endpoints=2"]
    assert judgment.advisory_only is True


class _Completions:
    content = "{}"

    @classmethod
    def create(cls, **kwargs):
        message = type("Message", (), {"content": cls.content})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice], "usage": None})()


class _OpenAI:
    def __init__(self, **kwargs):
        self.chat = type("Chat", (), {"completions": _Completions()})()


@pytest.mark.asyncio
async def test_invalid_json_returns_safe_false_advisory(monkeypatch):
    import openai
    monkeypatch.setattr(openai, "OpenAI", _OpenAI)
    _Completions.content = "not-json"
    monkeypatch.setattr("app.ai.validation_agent.record_ai_call", lambda **kwargs: None)

    judgment = await LLMValidationAgent("key", "model").judge(
        _context(), "user-test", runtime_context={"observations": {}},
    )
    assert judgment.resolved is False
    assert judgment.confidence == 0.0
    assert judgment.error_code == "invalid_response"
    assert judgment.advisory_only is True


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_confidence,expected", [(9, 1.0), (-2, 0.0), ("bad", 0.0)])
async def test_confidence_is_clamped_and_evidence_is_preserved(
    monkeypatch, raw_confidence, expected
):
    import openai
    monkeypatch.setattr(openai, "OpenAI", _OpenAI)
    _Completions.content = json.dumps({
        "resolved": True,
        "reason": "대상 workload가 정상입니다.",
        "confidence": raw_confidence,
        "evidence": ["deployments.nginx.available=1/1"],
    })
    monkeypatch.setattr("app.ai.validation_agent.record_ai_call", lambda **kwargs: None)

    judgment = await LLMValidationAgent("key", "model").judge(
        _context(), "user-test", runtime_context={"observations": {}},
    )
    assert judgment.confidence == expected
    assert judgment.evidence == ["deployments.nginx.available=1/1"]


def test_prompt_uses_runtime_context_and_never_includes_internal_answer():
    prompt = LLMValidationAgent("key", "model")._build_prompt(
        _context(), {"observations": {"pods": [{"name": "nginx"}]}}, "kubernetes"
    )
    assert "RuntimeContext" in prompt
    assert "정답은" not in prompt
    assert "patch" not in prompt
