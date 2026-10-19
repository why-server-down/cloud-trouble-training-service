"""힌트 단계·debug/resolve 는 서버가 강제한다.

클라이언트가 hint_level=3 을 보내도 산 힌트 수(attempt.hints_used)를 넘을 수 없고,
debug/resolve 는 mock 백엔드가 아니면 숨긴다.
"""
import uuid

import httpx
import pytest

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()


class _Attempt:
    def __init__(self, hints_used):
        self.id = uuid.uuid4()
        self.hints_used = hints_used
        self.attempt_type = "static"
        self.mission_id = uuid.uuid4()
        self.scenario_id = None
        self.environment = "kubernetes"


class _Mission:
    name = "테스트 미션"
    level = 1
    chaos_type = "pod_failure"


class _TutorSpy:
    def __init__(self):
        self.seen_level = None

    async def get_hint(self, *, hint_level, **kwargs):
        from app.schemas import TutorResult

        self.seen_level = hint_level
        return TutorResult(message="ok", hint_level=hint_level, environment="kubernetes")


@pytest.fixture
def chat_client(monkeypatch):
    user = _FakeUser()
    attempt = _Attempt(hints_used=1)
    tutor = _TutorSpy()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: object()

    import app.api.chat as chat_module

    mission_service = type("S", (), {"get_active_attempt": staticmethod(
        lambda db, uid: _async(attempt))})()
    monkeypatch.setattr(chat_module, "get_mission_service", lambda: mission_service)
    monkeypatch.setattr(chat_module, "get_tutor_service", lambda: tutor)

    async def _mission_info(db, att):
        return _Mission.name, _Mission.level, _Mission.chaos_type

    monkeypatch.setattr(chat_module, "_get_mission_info", _mission_info)

    transport = httpx.ASGITransport(app=app)
    yield httpx.AsyncClient(transport=transport, base_url="http://test"), tutor, attempt
    app.dependency_overrides.clear()


async def _async(value):
    return value


class TestHintLevelClamp:
    @pytest.mark.asyncio
    async def test_requested_level_is_capped_to_hints_used(self, chat_client):
        client, tutor, attempt = chat_client  # hints_used=1
        async with client:
            resp = await client.post("/api/chat/", json={"message": "도와줘", "hint_level": 3})
        assert resp.status_code == 200
        assert tutor.seen_level == 1
        assert resp.json()["hint_level"] == 1

    @pytest.mark.asyncio
    async def test_out_of_range_level_rejected_by_schema(self, chat_client):
        client, _, _ = chat_client
        async with client:
            resp = await client.post("/api/chat/", json={"message": "x", "hint_level": 99})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_message_rejected(self, chat_client):
        client, _, _ = chat_client
        async with client:
            resp = await client.post("/api/chat/", json={"message": "", "hint_level": 0})
        assert resp.status_code == 422
