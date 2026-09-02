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

        # 구현된 환경은 available 이고 capabilities 를 알린다
        for env in environments.IMPLEMENTED_ENVIRONMENTS:
            assert by_id[env]["status"] == "available"
            assert by_id[env]["capabilities"], f"{env} 가 제공 기능을 알리지 않는다"

        # 아직 구현되지 않은 환경은 preparing 이고 기능을 광고하지 않는다
        for env in environments.SUPPORTED_ENVIRONMENTS:
            if env in environments.IMPLEMENTED_ENVIRONMENTS:
                continue
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


class TestCapabilitiesMatchImplementation:
    """capabilities 는 **광고이지 관문이 아니다.**

    요청을 막는 것은 `assert_implemented` 이고, capabilities 값으로 400 을 내지
    않는다. 그래서 틀려도 서버는 아무 일 없이 돌아가고, 대신 프론트가 잘못된
    화면을 그린다 — 없는 기능을 광고하면 열 수 없는 화면을, 있는 기능을 빼면
    쓸 수 있는 화면을 잠근다.

    실제로 docker/linux 의 capabilities 가 (static_mission, terminal) 에 멈춰 있어
    프론트가 문의를 남겼다(2026-09-02). 값을 손으로 맞추는 대신, 각 capability 가
    **정말 배선돼 있는지**를 구현에서 끌어와 확인한다.
    """

    KNOWN = {"static_mission", "ai_scenario", "terminal", "tutor", "observability"}

    def _capabilities(self, environment: str) -> set[str]:
        items = {item["id"]: item for item in environments.availability()}
        return set(items[environment]["capabilities"])

    @pytest.mark.parametrize("environment", environments.IMPLEMENTED_ENVIRONMENTS)
    def test_only_known_capability_names(self, environment):
        """프론트 타입은 닫힌 union 이다. 새 이름을 조용히 늘리면 타입이 깨진다."""
        assert self._capabilities(environment) <= self.KNOWN

    @pytest.mark.parametrize("environment", environments.IMPLEMENTED_ENVIRONMENTS)
    def test_terminal_capability_has_a_command_policy(self, environment):
        from app.services.command_validator import CommandValidator

        if "terminal" in self._capabilities(environment):
            assert environment in CommandValidator._POLICIES

    @pytest.mark.parametrize("environment", environments.IMPLEMENTED_ENVIRONMENTS)
    def test_observability_capability_has_an_observer(self, environment):
        from app.services.runtime_context import RuntimeContextCollector

        if "observability" in self._capabilities(environment):
            assert environment in RuntimeContextCollector._OBSERVERS

    @pytest.mark.parametrize("environment", environments.IMPLEMENTED_ENVIRONMENTS)
    def test_static_mission_capability_has_seeded_missions(self, environment):
        from app.services.seed_data import MISSIONS

        if "static_mission" in self._capabilities(environment):
            assert [m for m in MISSIONS if m["environment"] == environment]

    @pytest.mark.parametrize("environment", environments.IMPLEMENTED_ENVIRONMENTS)
    def test_ai_scenario_capability_has_injectable_fault_types(self, environment):
        """생성 가능한 fault type 이 그 환경 주입기가 아는 타입이어야 한다.

        이름만 있고 주입기가 모르면 시나리오는 만들어지는데 시작에서 실패한다.
        """
        from app.services.chaos_injector import ChaosMeshInjector
        from app.services.chaos_plan import (
            FAULT_TYPE_TO_CHAOS_TYPE,
            allowed_fault_types,
        )
        from app.services.docker_chaos_injector import DockerChaosInjector
        from app.services.linux_chaos_injector import LinuxChaosInjector

        if "ai_scenario" not in self._capabilities(environment):
            return

        supported = {
            environments.KUBERNETES: lambda: set(ChaosMeshInjector._CHAOS_HANDLERS),
            environments.DOCKER: lambda: set(
                DockerChaosInjector(sandbox_service=object()).supported_chaos_types()
            ),
            environments.LINUX: lambda: set(
                LinuxChaosInjector(sandbox_service=object()).supported_chaos_types()
            ),
        }[environment]()

        fault_types = allowed_fault_types(environment)
        assert fault_types
        unmapped = {
            fault for fault in fault_types
            if FAULT_TYPE_TO_CHAOS_TYPE.get(fault, fault) not in supported
        }
        assert not unmapped, f"{environment} 주입기가 모르는 fault type: {sorted(unmapped)}"

    @pytest.mark.parametrize("environment", environments.IMPLEMENTED_ENVIRONMENTS)
    def test_tutor_capability_receives_the_attempt_environment(self, environment):
        """튜터가 환경을 받아 답하는지. 받지 않으면 kubernetes 기준으로 답한다."""
        import inspect

        from app.ai.tutor_service import TutorService

        if "tutor" in self._capabilities(environment):
            source = inspect.getsource(TutorService.get_hint)
            assert "attempt_environment" in source


class TestChatResponseCarriesEnvironment:
    """튜터 답변이 어느 환경을 근거로 만들어졌는지 응답에 실린다.

    TutorResult 에는 있었지만 ChatResponse 가 내보내지 않아, 프론트가
    "요청 환경 != 응답 환경" 을 계약 오류로 잡을 수 없었다(2026-09-02 보고).
    """

    def test_field_exists_with_a_valid_default(self):
        from app.schemas import ChatResponse

        assert "environment" in ChatResponse.model_fields
        assert ChatResponse(response="", hint_level=0).environment in (
            environments.SUPPORTED_ENVIRONMENTS
        )

    def test_unknown_environment_is_rejected(self):
        from app.schemas import ChatResponse

        with pytest.raises(ValidationError):
            ChatResponse(response="", hint_level=0, environment="windows")

    def test_endpoint_passes_the_tutor_environment_through(self):
        """기본값으로 덮어쓰면 불일치를 영영 못 잡는다."""
        import inspect

        from app.api.chat import chat_with_tutor

        source = inspect.getsource(chat_with_tutor)
        assert "environment=tutor_result.environment" in source
