"""Qdrant 자동 적재가 backend Settings 를 따른다.

예전에는 켜짐 여부를 `os.getenv("AI_BACKEND")` 로, 키·주소를 ai-data 의 환경변수 config 로 읽었다.
backend/.env 는 pydantic Settings 만 읽고 os.environ 에 넣지 않으므로, .env 에 gemini 와 키를 적어도
적재가 늘 건너뛰어졌다(튜터는 Settings 를 써서 문서 없는 RAG 로 답했다).
"""
import pytest

from app.services import qdrant_init


@pytest.fixture
def ran(monkeypatch):
    calls = []
    monkeypatch.setattr(qdrant_init, "_run_ingestion", lambda: calls.append(True))
    monkeypatch.delenv("AI_BACKEND", raising=False)
    return calls


@pytest.mark.asyncio
async def test_ingests_when_settings_say_gemini_even_without_shell_env(monkeypatch, ran):
    monkeypatch.setattr(qdrant_init.settings, "AI_BACKEND", "gemini")
    await qdrant_init.auto_ingest_if_empty()
    assert ran == [True]


@pytest.mark.asyncio
async def test_skips_in_mock_mode(monkeypatch, ran):
    monkeypatch.setattr(qdrant_init.settings, "AI_BACKEND", "mock")
    await qdrant_init.auto_ingest_if_empty()
    assert ran == []


def test_rag_service_gets_backend_settings(monkeypatch):
    """키와 Qdrant 주소도 Settings 에서 온다 — RAGService 에 넘기는 설정을 확인한다."""
    assert qdrant_init._ensure_ai_data_path()
    import rag_service

    seen = {}

    class _FakeRAG:
        def __init__(self, settings=None, **_kwargs):
            seen["settings"] = settings
            raise rag_service.RAGServiceError("멈춤")

    monkeypatch.setattr(rag_service, "RAGService", _FakeRAG)
    monkeypatch.setattr(qdrant_init.settings, "AI_BACKEND", "gemini")
    monkeypatch.setattr(qdrant_init.settings, "GEMINI_API_KEY", "key-from-dotenv")
    monkeypatch.setattr(qdrant_init.settings, "QDRANT_URL", "http://qdrant.test:6333")

    qdrant_init._run_ingestion()

    assert seen["settings"].AI_BACKEND == "gemini"
    assert seen["settings"].GEMINI_API_KEY == "key-from-dotenv"
    assert seen["settings"].QDRANT_URL == "http://qdrant.test:6333"
