"""환경 기반 구현체 선택과 재시작 복구 (BE-08).

- 미구현·미등록 환경 요청이 kubernetes 구현으로 조용히 대체되지 않는다.
- 주입된 장애는 프로세스 메모리가 아니라 DB 의 chaos_id 로 되돌린다.
"""
import uuid

import pytest

from app.core import environments
from app.services import service_factory
from app.services.chaos_injector import BaseChaosInjector, ChaosMeshInjector, MockChaosInjector
from app.services.mission_service import MissionService, namespace_for
from app.services.validation_service import MockValidationService


class TestFactoryKeyIsEnvironmentAware:
    def test_registry_is_keyed_by_environment_and_backend(self):
        for key in service_factory._INJECTOR_FACTORIES:
            assert isinstance(key, tuple) and len(key) == 2
        for key in service_factory._VALIDATION_FACTORIES:
            assert isinstance(key, tuple) and len(key) == 2

    def test_unimplemented_environment_is_rejected(self):
        """docker 요청이 kubernetes injector 를 받지 않는다."""
        for environment in ("docker", "linux"):
            with pytest.raises(ValueError):
                service_factory.create_chaos_injector(environment)
            with pytest.raises(ValueError):
                service_factory.create_validation_service(environment)

    def test_unregistered_backend_raises_clear_error(self, monkeypatch):
        monkeypatch.setattr(service_factory.settings, "CHAOS_BACKEND", "does_not_exist")
        with pytest.raises(ValueError) as excinfo:
            service_factory.create_chaos_injector(environments.KUBERNETES)
        message = str(excinfo.value)
        assert "does_not_exist" in message
        assert "kubernetes" in message  # 등록된 조합을 알려준다

    def test_registered_environment_returns_matching_implementation(self, monkeypatch):
        monkeypatch.setattr(service_factory.settings, "CHAOS_BACKEND", "mock")
        injector = service_factory.create_chaos_injector(environments.KUBERNETES)
        assert isinstance(injector, MockChaosInjector)
        assert injector.environment == environments.KUBERNETES

    def test_mock_validation_declares_environment(self, monkeypatch):
        monkeypatch.setattr(service_factory.settings, "VALIDATION_BACKEND", "mock")
        service = service_factory.create_validation_service(environments.KUBERNETES)
        assert isinstance(service, MockValidationService)
        assert service.environment == environments.KUBERNETES


class TestChaosIdIsSelfDescribing:
    """재시작 후 복구의 전제: chaos_id 만으로 chaos_type 을 복원할 수 있어야 한다."""

    @pytest.mark.parametrize(
        "chaos_id,expected",
        [
            ("pod-failure-a1b2c3d4", "pod_failure"),
            ("compound-probe-cascade-ff00ff00", "compound_probe_cascade"),
            ("cpu-throttle-00112233", "cpu_throttle"),
        ],
    )
    def test_type_is_recoverable_from_id(self, chaos_id, expected):
        assert BaseChaosInjector.chaos_type_from_id(chaos_id) == expected

    def test_malformed_id_returns_none(self):
        assert BaseChaosInjector.chaos_type_from_id("bad") is None
        assert BaseChaosInjector.chaos_type_from_id("") is None

    @pytest.mark.asyncio
    async def test_injected_id_is_parseable(self):
        injector = MockChaosInjector(delay=0)
        result = await injector.inject("memory_stress", "user-x")
        assert BaseChaosInjector.chaos_type_from_id(result.chaos_id) == "memory_stress"

    def test_chaos_mesh_revert_does_not_require_memory(self):
        """재시작으로 주입 이력이 비어도 chaos_id 에서 타입을 복원해 되돌린다."""
        injector = ChaosMeshInjector.__new__(ChaosMeshInjector)
        injector._active_chaos = {}  # 재시작 직후 상태
        reverted = {}

        def fake_revert(self, chaos_id, namespace):
            reverted["chaos_id"] = chaos_id
            reverted["namespace"] = namespace

        injector._CHAOS_HANDLERS = {"pod_failure": (None, fake_revert)}

        assert injector._revert_sync("pod-failure-a1b2c3d4", "user-42") is True
        assert reverted == {"chaos_id": "pod-failure-a1b2c3d4", "namespace": "user-42"}

    def test_revert_fails_clearly_for_unknown_type(self):
        injector = ChaosMeshInjector.__new__(ChaosMeshInjector)
        injector._active_chaos = {}
        injector._CHAOS_HANDLERS = {}
        assert injector._revert_sync("unknown-type-a1b2c3d4", "user-42") is False


class _RecordingInjector(BaseChaosInjector):
    def __init__(self, environment: str):
        self.environment = environment
        self.reverted: list[tuple[str, str]] = []

    async def inject(self, chaos_type: str, namespace: str):  # pragma: no cover
        raise NotImplementedError

    async def revert(self, chaos_id: str, namespace: str) -> bool:
        self.reverted.append((chaos_id, namespace))
        return True


class _FakeAttempt:
    def __init__(self, environment: str, chaos_id: str | None):
        self.id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.environment = environment
        self.chaos_id = chaos_id


class TestCleanupUsesStoredChaosId:
    @pytest.mark.asyncio
    async def test_cleanup_reverts_with_db_chaos_id(self):
        """프로세스 메모리가 아니라 attempt.chaos_id 로 정리한다."""
        injectors = {}

        def factory(environment):
            injectors.setdefault(environment, _RecordingInjector(environment))
            return injectors[environment]

        service = MissionService(
            injector_for=factory,
            validation_for=lambda env: MockValidationService(environment=env),
            scoring_service=object(),
        )
        attempt = _FakeAttempt(environments.KUBERNETES, "pod-failure-a1b2c3d4")

        await service._cleanup_chaos(attempt)

        injector = injectors[environments.KUBERNETES]
        assert injector.reverted == [
            ("pod-failure-a1b2c3d4", namespace_for(attempt.user_id))
        ]
        # 두 번 정리해도 안전하도록 비운다
        assert attempt.chaos_id is None

    @pytest.mark.asyncio
    async def test_cleanup_is_noop_without_chaos_id(self):
        injector = _RecordingInjector(environments.KUBERNETES)
        service = MissionService(
            injector_for=lambda env: injector,
            validation_for=lambda env: MockValidationService(environment=env),
            scoring_service=object(),
        )
        await service._cleanup_chaos(_FakeAttempt(environments.KUBERNETES, None))
        assert injector.reverted == []

    @pytest.mark.asyncio
    async def test_cleanup_selects_injector_by_attempt_environment(self):
        """attempt 의 환경으로 주입기를 고른다. 다른 환경 주입기를 쓰지 않는다."""
        seen = []

        def factory(environment):
            seen.append(environment)
            return _RecordingInjector(environment)

        service = MissionService(
            injector_for=factory,
            validation_for=lambda env: MockValidationService(environment=env),
            scoring_service=object(),
        )
        await service._cleanup_chaos(_FakeAttempt(environments.KUBERNETES, "pod-failure-1"))
        assert seen == [environments.KUBERNETES]


class TestServiceIsStateless:
    def test_services_do_not_keep_in_memory_chaos_ids(self):
        """환경별 인스턴스 대신 factory lookup 을 쓰므로 서비스는 상태를 갖지 않는다."""
        mission = service_factory.create_mission_service()
        scenario = service_factory.create_scenario_service()
        assert not hasattr(mission, "_active_chaos_ids")
        assert not hasattr(scenario, "_active_chaos_ids")


class TestNetworkLatencyRolloutStrategy:
    """미션 4가 실제로 장애를 만들도록 롤아웃 전략을 함께 조정한다 (BE-10).

    RollingUpdate 기본값에서는 새 Pod 가 Ready 가 되지 못해도 기존 Ready Pod 가
    남아 엔드포인트가 유지된다. 그러면 서비스가 정상 동작해 사용자가 아무 장애도
    겪지 않는다. 실클러스터 회귀에서 확인된 결함이다.
    """

    def _injector(self):
        from app.services.chaos_injector import ChaosMeshInjector

        injector = ChaosMeshInjector.__new__(ChaosMeshInjector)
        calls = []

        class _FakeAppsApi:
            def patch_namespaced_deployment(self, name, namespace, body):
                calls.append(body)

        injector._apps_api = _FakeAppsApi()
        return injector, calls

    def test_inject_makes_existing_pod_step_down(self):
        injector, calls = self._injector()
        injector._apply_network_chaos("network-latency-1", "user-1")

        strategies = [
            c["spec"]["strategy"]["rollingUpdate"] for c in calls if "strategy" in c.get("spec", {})
        ]
        assert strategies, "롤아웃 전략을 조정해야 기존 Ready Pod 가 남지 않는다"
        assert strategies[0] == {"maxUnavailable": 1, "maxSurge": 0}

    def test_inject_sets_failing_readiness_probe(self):
        injector, calls = self._injector()
        injector._apply_network_chaos("network-latency-1", "user-1")

        probes = [
            c["spec"]["template"]["spec"]["containers"][0].get("readinessProbe")
            for c in calls
            if "template" in c.get("spec", {})
        ]
        assert probes and probes[0]["httpGet"]["path"] == "/healthz-notexist"

    def test_revert_restores_default_strategy(self):
        injector, calls = self._injector()
        injector._revert_network_latency("network-latency-1", "user-1")

        strategies = [
            c["spec"]["strategy"]["rollingUpdate"] for c in calls if "strategy" in c.get("spec", {})
        ]
        assert strategies == [{"maxUnavailable": "25%", "maxSurge": "25%"}]

        probes = [
            c["spec"]["template"]["spec"]["containers"][0].get("readinessProbe", "missing")
            for c in calls
            if "template" in c.get("spec", {})
        ]
        assert probes == [None], "복구는 readinessProbe 를 제거해야 한다"


class TestSandboxImageIsConfigurable:
    def test_toolbox_image_comes_from_settings(self):
        """이미지를 하드코딩하면 태그가 사라졌을 때 샌드박스가 뜨지 않는다."""
        from app.core.config import settings
        from app.services.sandbox_service import SandboxService

        service = SandboxService(
            core_api=object(), rbac_api=object(), networking_api=object(), k8s_setup=object()
        )
        assert service.TOOLBOX_IMAGE == settings.SANDBOX_TOOLBOX_IMAGE
        assert service.READINESS_TIMEOUT_SECONDS == settings.SANDBOX_READINESS_TIMEOUT_SECONDS

    def test_chaos_mesh_namespace_comes_from_settings(self):
        from app.core.config import settings
        from app.services.chaos_injector import ChaosMeshInjector

        injector = ChaosMeshInjector.__new__(ChaosMeshInjector)
        assert injector.CHAOS_NAMESPACE == settings.CHAOS_MESH_NAMESPACE
