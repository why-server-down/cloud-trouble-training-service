from types import SimpleNamespace

import pytest

from ai_engine import AITutorEngine, TutorRequest
from config import AISettings
from context_safety import count_tokens
from prompt_engine import SocraticPromptEngine, TrainingContext
from tests.fakes import DeterministicFakeOpenAI


def _engine(settings=None):
    engine = object.__new__(AITutorEngine)
    engine.settings = settings or AISettings(AI_BACKEND="mock")
    engine.model = "gpt-4o-mini"
    engine.use_rag = False
    engine.prompt_engine = SocraticPromptEngine()
    engine.client = DeterministicFakeOpenAI()
    return engine


def test_long_untrusted_input_never_exceeds_context_token_budget():
    settings = AISettings(AI_BACKEND="mock", AI_MAX_CONTEXT_TOKENS=9000)
    prompt = SocraticPromptEngine().generate_prompt(
        "질문" * 20_000,
        training_ctx=TrainingContext(
            observations={"pods": "가" * 20_000},
            logs=["나" * 20_000],
            retrieved_docs=[{"content": "다" * 20_000}] * 10,
        ),
    )
    assert count_tokens(prompt) <= settings.AI_MAX_CONTEXT_TOKENS
    assert "=== YOUR RESPONSE ===" in prompt

    engine = _engine(AISettings(AI_BACKEND="mock", AI_MAX_CONTEXT_TOKENS=1200))
    engine.get_response(TutorRequest(
        "질문" * 20_000,
        training_ctx=TrainingContext(observations={"pods": "가" * 20_000}),
    ))
    sent_prompt = engine.client.chat.completions.calls[0]["messages"][0]["content"]
    assert count_tokens(sent_prompt) <= 1200


def test_completion_and_retrieved_chunk_limits_are_enforced():
    engine = _engine(AISettings(
        AI_BACKEND="mock", AI_MAX_COMPLETION_TOKENS=120,
        AI_MAX_RETRIEVED_CHUNKS=2,
    ))
    engine.get_response(TutorRequest("q"), max_tokens=9999)
    assert engine.client.chat.completions.calls[0]["max_tokens"] == 120

    engine.use_rag = True
    engine.rag_service = SimpleNamespace(search_knowledge=lambda *args, **kwargs: [
        SimpleNamespace(source=f"{i}.md", content="doc", similarity=0.9,
                        metadata={"title": str(i), "environments": ["kubernetes"]})
        for i in range(10)
    ])
    result = engine.retrieve(TutorRequest("q", hint_level=1))
    assert len(result.sources) == 2


def test_retry_is_bounded_to_transient_errors_only(monkeypatch):
    class _Transient(Exception):
        pass

    monkeypatch.setattr("ai_engine.openai.RateLimitError", _Transient)
    monkeypatch.setattr("ai_engine.openai.APIConnectionError", _Transient)
    settings = AISettings(AI_BACKEND="mock", AI_PROVIDER_MAX_ATTEMPTS=2)
    engine = _engine(settings)
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise _Transient("rate limited")

    engine.client.chat.completions.create = fail
    response = engine.get_response(TutorRequest("q"))
    assert response.error_code == "provider_failed"
    assert len(calls) == 2


def test_non_transient_error_is_not_retried():
    engine = _engine(AISettings(AI_BACKEND="mock", AI_PROVIDER_MAX_ATTEMPTS=2))
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise ValueError("bad request")

    engine.client.chat.completions.create = fail
    response = engine.get_response(TutorRequest("q"))
    assert response.error_code == "provider_failed"
    assert len(calls) == 1
