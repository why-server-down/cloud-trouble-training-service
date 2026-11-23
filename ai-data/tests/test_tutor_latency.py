import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai.tutor_service import TutorService
from ai_engine import RetrievalResult, TutorRequest


@pytest.mark.asyncio
async def test_runtime_and_sync_retrieval_run_in_parallel_without_blocking_loop(monkeypatch):
    service = TutorService()

    class _Engine:
        model = "test-model"

        @staticmethod
        def retrieve(request):
            time.sleep(0.06)
            return RetrievalResult([], [], 60.0)

    service._engine = _Engine()
    monkeypatch.setattr("app.ai.tutor_service.record_ai_stage", lambda **kwargs: None)

    async def runtime():
        await asyncio.sleep(0.06)
        return {"observations": {}}

    started = time.perf_counter()
    runtime_result, retrieval_result, ticker = await asyncio.gather(
        service._collect_runtime_with_timeout(runtime, "docker", 1),
        service._retrieve_with_timeout(TutorRequest("q"), "docker", 1),
        asyncio.sleep(0.01, result="tick"),
    )
    elapsed = time.perf_counter() - started
    assert elapsed < 0.11
    assert ticker == "tick"
    assert runtime_result[0] == {"observations": {}}
    assert retrieval_result[0].latency_ms == 60.0


@pytest.mark.asyncio
async def test_retrieval_timeout_is_distinct_and_late_result_is_ignored(monkeypatch):
    service = TutorService()

    class _Engine:
        model = "test-model"

        @staticmethod
        def retrieve(request):
            time.sleep(0.08)
            return RetrievalResult(["late"], ["late"], 80.0)

    service._engine = _Engine()
    monkeypatch.setattr("app.ai.tutor_service.settings.RAG_SEARCH_TIMEOUT", 0.01)
    monkeypatch.setattr("app.ai.tutor_service.record_ai_stage", lambda **kwargs: None)
    retrieval, _, error = await service._retrieve_with_timeout(
        TutorRequest("q"), "linux", 1
    )
    assert error == "retrieval_timeout"
    assert retrieval.sources == []
    await asyncio.sleep(0.1)
    assert retrieval.sources == []


@pytest.mark.asyncio
async def test_llm_timeout_returns_safe_response_instead_of_late_provider_result(monkeypatch):
    service = TutorService()

    class _Engine:
        model = "test-model"

        @staticmethod
        def get_response(request, **kwargs):
            time.sleep(0.08)
            return SimpleNamespace(message="late provider response")

    service._engine = _Engine()
    monkeypatch.setattr("app.ai.tutor_service.settings.OPENAI_TIMEOUT", 0.01)
    monkeypatch.setattr("app.ai.tutor_service.record_ai_stage", lambda **kwargs: None)
    monkeypatch.setattr("app.ai.tutor_service.record_ai_call", lambda **kwargs: None)
    result = await service._call_engine(
        user_question="q", hint_level=1, mission_name="m", mission_level=1,
        chaos_type="fault", namespace="user-test", conversation_history=[],
        attempt_id="attempt", runtime_ctx=None, environment="kubernetes",
        retrieval_result=RetrievalResult([], [], 0.0),
    )
    assert result.error_code == "provider_timeout"
    assert "late provider response" not in result.message
    await asyncio.sleep(0.1)
    assert "late provider response" not in result.message


def test_response_reports_all_required_latency_stages():
    from tests.test_ai_engine_environment import _PromptEngine
    from tests.fakes import DeterministicFakeOpenAI
    from ai_engine import AITutorEngine
    from config import AISettings

    engine = object.__new__(AITutorEngine)
    engine.settings = AISettings(AI_BACKEND="mock")
    engine.model = "fake-model"
    engine.use_rag = False
    engine.prompt_engine = _PromptEngine()
    engine.client = DeterministicFakeOpenAI()
    response = engine.get_response(TutorRequest("q"))
    assert {"retrieval_ms", "rerank_ms", "llm_ms", "total_ms"} <= set(
        response.latency_breakdown
    )
