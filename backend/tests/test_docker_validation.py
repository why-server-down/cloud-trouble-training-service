"""Docker 환경 해결 검증 (BE-14).

문자열 출력을 그대로 비교하지 않고 필요한 값을 구조적으로 읽는지,
정답이 API 메시지로 새지 않는지를 고정한다.
"""
import pytest

from app.core import environments
from app.core.config import settings
from app.services.docker_chaos_injector import (
    CONTAINER_STOPPED,
    CPU_THROTTLE,
    NETWORK_DISCONNECT,
)
from app.services.docker_validation_service import DockerValidationService
from app.services.sandbox_service import SandboxRef
from app.services.validation_service import RETRY_MESSAGE

NET = settings.SANDBOX_TRAINING_NETWORK
CPUS = settings.SANDBOX_TRAINING_CPUS
NS = "user-abc"


class _FakeSandboxService:
    def __init__(self, output="", fail=False):
        self.output = output
        self.fail = fail
        self.calls = []

    def reference_for(self, *, user_id, namespace, environment):
        return SandboxRef(
            id="s1", namespace=namespace, pod_name="sandbox-s1",
            container_name="dind", environment=environment,
        )

    def exec_in_sandbox(self, sandbox, argv):
        self.calls.append((sandbox.namespace, argv))
        if self.fail:
            raise RuntimeError("boom")
        return self.output


def _service(output="", fail=False):
    fake = _FakeSandboxService(output, fail)
    return DockerValidationService(sandbox_service=fake), fake


class TestContainerStopped:
    @pytest.mark.asyncio
    async def test_resolved_when_running(self):
        service, _ = _service("running")
        result = await service.check_resolution(CONTAINER_STOPPED, NS)
        assert result.is_resolved
        assert result.details == {"state": "running"}

    @pytest.mark.asyncio
    async def test_not_resolved_when_exited(self):
        service, _ = _service("exited")
        assert not (await service.check_resolution(CONTAINER_STOPPED, NS)).is_resolved


class TestNetworkDisconnect:
    @pytest.mark.asyncio
    async def test_resolved_when_reconnected(self):
        service, _ = _service(f"{NET} bridge ")
        result = await service.check_resolution(NETWORK_DISCONNECT, NS)
        assert result.is_resolved
        assert NET in result.details["networks"]

    @pytest.mark.asyncio
    async def test_not_resolved_when_detached(self):
        service, _ = _service("bridge ")
        assert not (await service.check_resolution(NETWORK_DISCONNECT, NS)).is_resolved

    @pytest.mark.asyncio
    async def test_not_resolved_when_no_network(self):
        service, _ = _service("")
        assert not (await service.check_resolution(NETWORK_DISCONNECT, NS)).is_resolved


class TestCpuThrottle:
    @pytest.mark.asyncio
    async def test_resolved_at_baseline(self):
        service, _ = _service(str(int(float(CPUS) * 1_000_000_000)))
        result = await service.check_resolution(CPU_THROTTLE, NS)
        assert result.is_resolved

    @pytest.mark.asyncio
    async def test_resolved_when_partially_restored(self):
        """정확히 같은 값을 넣지 않아도 훈련 목적은 달성된다."""
        service, _ = _service(str(int(float(CPUS) * 1_000_000_000 * 0.6)))
        assert (await service.check_resolution(CPU_THROTTLE, NS)).is_resolved

    @pytest.mark.asyncio
    async def test_resolved_when_limit_removed(self):
        """0 은 제한 없음을 뜻한다."""
        service, _ = _service("0")
        result = await service.check_resolution(CPU_THROTTLE, NS)
        assert result.is_resolved
        assert result.details["cpus"] == "unlimited"

    @pytest.mark.asyncio
    async def test_not_resolved_while_throttled(self):
        service, _ = _service("50000000")  # 0.05 cpu
        assert not (await service.check_resolution(CPU_THROTTLE, NS)).is_resolved


class TestStructuredReading:
    @pytest.mark.asyncio
    async def test_uses_format_template_not_raw_output(self):
        """inspect 전체 출력은 exec 채널에서 표준 JSON 으로 오지 않는다.

        필드별 --format 으로 읽어야 신뢰할 수 있다.
        """
        service, fake = _service("running")
        await service.check_resolution(CONTAINER_STOPPED, NS)
        _, argv = fake.calls[0]
        assert "--format" in argv
        assert argv[-1].startswith("{{") and argv[-1].endswith("}}")


class TestIsolation:
    @pytest.mark.asyncio
    async def test_checks_only_the_given_namespace(self):
        """다른 샌드박스 상태가 검증에 영향을 주지 않는다."""
        service, fake = _service("running")
        await service.check_resolution(CONTAINER_STOPPED, "user-1")
        await service.check_resolution(CONTAINER_STOPPED, "user-2")
        assert [ns for ns, _ in fake.calls] == ["user-1", "user-2"]


class TestFailureHandling:
    @pytest.mark.asyncio
    async def test_exec_failure_becomes_retry(self):
        service, _ = _service(fail=True)
        result = await service.check_resolution(CONTAINER_STOPPED, NS)
        assert not result.is_resolved
        assert result.message == RETRY_MESSAGE

    @pytest.mark.asyncio
    async def test_unknown_chaos_type_becomes_retry(self):
        service, fake = _service("running")
        result = await service.check_resolution("docker_unknown", NS)
        assert not result.is_resolved
        assert fake.calls == []

    @pytest.mark.asyncio
    async def test_message_does_not_leak_the_answer(self):
        """검증 실패 메시지에 해결 방법이 담기면 안 된다."""
        service, _ = _service("exited")
        result = await service.check_resolution(CONTAINER_STOPPED, NS)
        for leak in ("docker", "start", "network", "cpus", "training-app"):
            assert leak not in result.message


class TestEnvironmentActivation:
    def test_docker_is_implemented(self):
        assert environments.is_implemented(environments.DOCKER)

    def test_docker_advertises_what_it_provides(self):
        """capabilities 는 구현과 함께 갱신해야 한다.

        2026-09-02: ai_scenario(환경별 fault type)·tutor(환경 전달)·observability
        (환경별 관측기)가 모두 붙어 (static_mission, terminal) 표기가 낡았다.
        각 capability 의 배선 확인은 test_environment_contract.py 가 담당한다.
        """
        items = {item["id"]: item for item in environments.availability()}
        docker = items[environments.DOCKER]

        assert docker["status"] == "available"
        assert "static_mission" in docker["capabilities"]
        assert "terminal" in docker["capabilities"]

    def test_docker_missions_are_seeded(self):
        from app.services.seed_data import MISSIONS

        docker = [m for m in MISSIONS if m["environment"] == environments.DOCKER]
        assert len(docker) >= 3
        assert sorted(m["level"] for m in docker) == [1, 2, 3]

    def test_every_docker_mission_has_an_injector_and_validator(self):
        """시드에 있는 chaos_type 이 주입·검증 양쪽에 등록돼 있어야 한다."""
        from app.services.docker_chaos_injector import DockerChaosInjector
        from app.services.seed_data import MISSIONS

        injector_types = DockerChaosInjector.__new__(
            DockerChaosInjector
        ).supported_chaos_types()
        for mission in MISSIONS:
            if mission["environment"] != environments.DOCKER:
                continue
            assert mission["chaos_type"] in injector_types
            assert mission["chaos_type"] in DockerValidationService._CHECKS
