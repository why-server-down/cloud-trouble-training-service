"""Docker 환경 장애 주입 (BE-13).

가장 중요한 계약: **등록된 모든 장애는 BE-12 명령 정책 안에서 사용자가 복구할 수
있어야 한다.** 장애는 나는데 아무도 못 고치는 미션은 교육적으로 무의미하다.
"""
import pytest

from app.core import environments
from app.core.config import settings
from app.services.chaos_injector import BaseChaosInjector
from app.services.command_validator import CommandValidator
from app.services.docker_chaos_injector import (
    CONTAINER_STOPPED,
    CPU_THROTTLE,
    NETWORK_DISCONNECT,
    DockerChaosInjector,
)
from app.services.sandbox_service import SandboxRef

APP = settings.SANDBOX_TRAINING_CONTAINER
NET = settings.SANDBOX_TRAINING_NETWORK
NS = "user-abc"

# 각 장애를 사용자가 되돌리는 명령. 정책 통과 여부를 여기서 고정한다.
USER_RECOVERY = {
    NETWORK_DISCONNECT: f"docker network connect {NET} {APP}",
    CONTAINER_STOPPED: f"docker start {APP}",
    CPU_THROTTLE: f"docker update --cpus {settings.SANDBOX_TRAINING_CPUS} {APP}",
}


class _FakeSandboxService:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}
        self.fail_on = None

    def reference_for(self, *, user_id, namespace, environment):
        return SandboxRef(
            id="s1",
            namespace=namespace,
            pod_name="sandbox-s1",
            container_name="dind",
            environment=environment,
        )

    def exec_in_sandbox(self, sandbox, argv):
        self.calls.append(argv)
        if self.fail_on and argv[:len(self.fail_on)] == self.fail_on:
            raise RuntimeError("boom")
        for prefix, value in self.responses.items():
            if argv[: len(prefix)] == list(prefix):
                return value
        return ""


def _injector(**kwargs):
    service = _FakeSandboxService(**kwargs)
    return DockerChaosInjector(sandbox_service=service), service


class TestOnlyRecoverableFaultsAreRegistered:
    """등록 기준: 사용자가 명령 정책 안에서 복구할 수 있어야 한다."""

    def test_every_fault_has_a_user_recovery_command(self):
        injector, _ = _injector()
        assert set(injector.supported_chaos_types()) == set(USER_RECOVERY)

    @pytest.mark.parametrize("chaos_type,command", sorted(USER_RECOVERY.items()))
    def test_recovery_command_passes_command_policy(self, chaos_type, command):
        """복구 명령이 BE-12 정책을 통과하지 못하면 그 장애는 등록될 수 없다."""
        result = CommandValidator().validate_command(
            command, NS, environment=environments.DOCKER
        )
        assert result.is_valid, f"{chaos_type}: {result.error}"

    def test_volume_fault_is_not_registered(self):
        """volume/mount 장애는 사용자가 복구할 수 없어 제외했다.

        실측: docker update 에 마운트 옵션이 없고, 사용 중인 볼륨은 삭제되지 않는다.
        유일한 경로인 docker run 은 BE-12 에서 차단돼 있다.
        """
        injector, _ = _injector()
        assert not any("volume" in t for t in injector.supported_chaos_types())


class TestInject:
    @pytest.mark.asyncio
    async def test_network_disconnect_detaches_training_container(self):
        injector, service = _injector()
        result = await injector.inject(NETWORK_DISCONNECT, NS)
        assert result.success
        assert ["docker", "network", "disconnect", NET, APP] in service.calls

    @pytest.mark.asyncio
    async def test_cpu_throttle_lowers_within_sandbox_limit(self):
        injector, service = _injector()
        await injector.inject(CPU_THROTTLE, NS)
        update = [c for c in service.calls if c[:2] == ["docker", "update"]][0]
        assert update == ["docker", "update", "--cpus", injector.THROTTLED_CPUS, APP]
        assert float(injector.THROTTLED_CPUS) < float(settings.SANDBOX_TRAINING_CPUS)

    @pytest.mark.asyncio
    async def test_chaos_id_encodes_type_for_restart_recovery(self):
        injector, _ = _injector()
        result = await injector.inject(CONTAINER_STOPPED, NS)
        assert BaseChaosInjector.chaos_type_from_id(result.chaos_id) == CONTAINER_STOPPED

    @pytest.mark.asyncio
    async def test_snapshot_is_recorded(self):
        injector, service = _injector(
            responses={("docker", "inspect"): "running"}
        )
        result = await injector.inject(CONTAINER_STOPPED, NS)
        assert result.metadata["snapshot"]["state"] == "running"

    @pytest.mark.asyncio
    async def test_unknown_type_fails_without_touching_sandbox(self):
        injector, service = _injector()
        result = await injector.inject("docker_unknown", NS)
        assert not result.success
        assert service.calls == []

    @pytest.mark.asyncio
    async def test_partial_failure_is_rolled_back(self):
        """주입이 중간에 실패하면 앞 단계를 되돌린다.

        되돌리지 않으면 아무도 시작하지 않았는데 깨져 있는 환경이 된다.
        """
        injector, service = _injector()
        service.fail_on = ["docker", "network", "disconnect"]
        result = await injector.inject(NETWORK_DISCONNECT, NS)
        assert not result.success
        assert any(c[:3] == ["docker", "network", "connect"] for c in service.calls)


class TestRevert:
    @pytest.mark.asyncio
    async def test_reconnects_network(self):
        injector, service = _injector()
        assert await injector.revert("docker-network-disconnect-abc12345", NS) is True
        assert ["docker", "network", "connect", NET, APP] in service.calls

    @pytest.mark.asyncio
    async def test_is_idempotent_when_already_connected(self):
        """이미 연결돼 있으면 다시 연결하지 않는다. docker 가 오류를 낸다."""
        injector, service = _injector(responses={("docker", "inspect"): NET})
        await injector.revert("docker-network-disconnect-abc12345", NS)
        assert not any(c[:3] == ["docker", "network", "connect"] for c in service.calls)

    @pytest.mark.asyncio
    async def test_does_not_restart_running_container(self):
        injector, service = _injector(responses={("docker", "inspect"): "running"})
        await injector.revert("docker-container-stopped-abc12345", NS)
        assert not any(c[:2] == ["docker", "start"] for c in service.calls)

    @pytest.mark.asyncio
    async def test_restores_cpu_limit(self):
        injector, service = _injector()
        await injector.revert("docker-cpu-throttle-abc12345", NS)
        assert [
            "docker", "update", "--cpus", settings.SANDBOX_TRAINING_CPUS, APP
        ] in service.calls

    @pytest.mark.asyncio
    async def test_unknown_chaos_id_returns_false(self):
        injector, _ = _injector()
        assert await injector.revert("bad", NS) is False

    @pytest.mark.asyncio
    async def test_failure_is_reported_for_retry(self):
        """복구 실패는 조용히 삼키지 않고 False 로 알린다."""
        injector, service = _injector()
        service.fail_on = ["docker", "network", "connect"]
        assert await injector.revert("docker-network-disconnect-abc12345", NS) is False


class TestSandboxTargeting:
    @pytest.mark.asyncio
    async def test_uses_server_resolved_sandbox_for_namespace(self):
        injector, service = _injector()
        await injector.inject(CONTAINER_STOPPED, "user-42")
        # namespace 로부터 서버가 복원한 참조만 쓴다
        assert injector._sandbox_for("user-42").namespace == "user-42"

    def test_declares_docker_environment(self):
        injector, _ = _injector()
        assert injector.environment == environments.DOCKER
