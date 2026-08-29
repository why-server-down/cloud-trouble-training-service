"""environment 가 API 계약을 관통하는지 검증한다 (BE-03).

DB 없이 FastAPI dependency override 로 라우터 계약만 확인한다.
"""
import uuid
from typing import get_args

import httpx
import pytest
from pydantic import ValidationError

from app.api.deps import get_current_user
from app.core import environments
from app.core.database import get_db
from app.main import app
from app.schemas import (
    MissionAttemptResponse,
    MissionResponse,
    ScenarioGenerateRequest,
)


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "tester"


class _FakeMission:
    """DB 에서 읽어온 미션 행 대역. environment 가 kubernetes 가 아니다."""

    def __init__(self, environment: str):
        self.id = uuid.uuid4()
        self.name = "docker 훈련"
        self.level = 1
        self.description = "컨테이너 네트워크 단절"
        self.chaos_type = "network_disconnect"
        self.environment = environment
        self.base_score = 100
        self.time_limit = 600
        self.hint_penalty = 5


@pytest.fixture
def client():
    """lifespan 을 태우지 않는 ASGI 클라이언트.

    starlette TestClient 는 설치된 httpx 버전에 민감하고 lifespan(=DB 접속·seed)을
    실행한다. 이 테스트는 라우터 계약만 보므로 ASGITransport 를 직접 쓴다.
    """
    user = _FakeUser()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: None
    transport = httpx.ASGITransport(app=app)
    yield httpx.AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


class TestEnvironmentTypeContract:
    def test_literal_matches_supported_list(self):
        """API 계약(Literal)과 런타임 검증 목록이 갈라지지 않는다."""
        assert set(get_args(environments.EnvironmentId)) == set(
            environments.SUPPORTED_ENVIRONMENTS
        )

    def test_application_is_not_supported(self):
        """application 은 목업 한정이므로 계약에 포함되지 않는다."""
        assert "application" not in environments.SUPPORTED_ENVIRONMENTS
        assert not environments.is_supported("application")

    def test_invalid_environment_rejected_by_schema(self):
        with pytest.raises(ValidationError):
            ScenarioGenerateRequest(difficulty="beginner", environment="application")

    def test_valid_environments_accepted_by_schema(self):
        for env in environments.SUPPORTED_ENVIRONMENTS:
            body = ScenarioGenerateRequest(difficulty="beginner", environment=env)
            assert body.environment == env


class TestEnvironmentAvailabilityApi:
    @pytest.mark.asyncio
    async def test_lists_all_supported_environments(self, client):
        async with client:
            response = await client.get("/api/environments")
        assert response.status_code == 200
        items = response.json()["items"]
        assert [item["id"] for item in items] == list(environments.SUPPORTED_ENVIRONMENTS)

    @pytest.mark.asyncio
    async def test_only_implemented_environment_is_available(self, client):
        async with client:
            items = (await client.get("/api/environments")).json()["items"]
        by_id = {item["id"]: item for item in items}

        assert by_id["kubernetes"]["status"] == "available"
        assert by_id["kubernetes"]["capabilities"]

        for env in ("docker", "linux"):
            assert by_id[env]["status"] == "preparing"
            assert by_id[env]["capabilities"] == []


class TestMissionEnvironmentPassthrough:
    @pytest.mark.asyncio
    async def test_db_environment_is_not_replaced_by_default(self, client):
        """DB 의 docker 미션이 응답에서 kubernetes 로 바뀌지 않는다."""

        class _FakeMissionService:
            def __init__(self):
                self.requested_environment = None

            async def list_missions(self, db, user, environment="kubernetes"):
                self.requested_environment = environment
                return [{"mission": _FakeMission("docker"), "is_unlocked": True}]

        # get_mission_service 는 Depends 가 아니라 라우터에서 직접 호출되므로
        # 모듈 속성을 임시 교체한다.
        import app.api.missions as missions_module

        original = missions_module.get_mission_service
        missions_module.get_mission_service = lambda: _FakeMissionService()
        try:
            async with client:
                response = await client.get("/api/missions/")
        finally:
            missions_module.get_mission_service = original

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["environment"] == "docker"

    def test_mission_response_requires_valid_environment(self):
        mission = _FakeMission("application")
        with pytest.raises(ValidationError):
            MissionResponse(
                id=mission.id,
                name=mission.name,
                level=mission.level,
                description=mission.description,
                chaos_type=mission.chaos_type,
                environment=mission.environment,
                base_score=mission.base_score,
                time_limit=mission.time_limit,
                hint_penalty=mission.hint_penalty,
                is_unlocked=True,
            )


class TestAttemptEnvironment:
    def test_attempt_response_carries_environment(self):
        """attempt 는 mission/scenario 를 join 하지 않고도 환경을 알려준다."""

        class _FakeAttempt:
            id = uuid.uuid4()
            user_id = uuid.uuid4()
            mission_id = uuid.uuid4()
            attempt_type = "static_mission"
            scenario_id = None
            environment = "docker"
            status = "in_progress"
            start_time = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            end_time = None
            final_score = None
            hints_used = 0

        response = MissionAttemptResponse.model_validate(_FakeAttempt())
        assert response.environment == "docker"
