"""주입 실패 시 롤백 계약 (BE-24).

장애 주입은 여러 단계를 밟는다. 중간에 실패했는데 앞 단계를 그대로 두면
**아무도 시작하지 않았는데 깨져 있는 환경**이 된다. 사용자는 시작도 못 한 채
고장난 네임스페이스를 받고, 서버는 되돌릴 chaos_id 조차 갖고 있지 않다.

세 환경의 주입기가 모두 같은 계약을 지키는지 한자리에서 확인한다.
  - 주입이 실패하면 success=False 를 돌려준다(예외를 밖으로 던지지 않는다).
  - 실패하면 앞 단계를 되돌리는 호출이 나간다.
  - 되돌리기까지 실패해도 호출자에게는 여전히 success=False 가 간다.
"""
import pytest

from app.services.chaos_injector import ChaosMeshInjector
from app.services.docker_chaos_injector import NETWORK_DISCONNECT, DockerChaosInjector
from app.services.linux_chaos_injector import DISK_PRESSURE, LinuxChaosInjector
from app.services.sandbox_service import SandboxRef

NS = "user-rollback"


class _FakeSandboxService:
    def __init__(
        self, *, container_name, fail_on=None, fail_when=None, raise_on_reference=False
    ):
        self.calls = []
        self.container_name = container_name
        self.fail_on = fail_on
        # argv 전체를 보고 실패시킬 조건. fail_on 으로 표현할 수 없는 경우에 쓴다.
        self.fail_when = fail_when
        self.raise_on_reference = raise_on_reference

    def reference_for(self, *, user_id, namespace, environment):
        if self.raise_on_reference:
            raise RuntimeError("sandbox is gone")
        return SandboxRef(
            id="s1",
            namespace=namespace,
            pod_name="sandbox-s1",
            container_name=self.container_name,
            environment=environment,
        )

    def exec_in_sandbox(self, sandbox, argv):
        self.calls.append(argv)
        if self.fail_on and argv[: len(self.fail_on)] == self.fail_on:
            raise RuntimeError("boom")
        if self.fail_when and self.fail_when(argv):
            raise RuntimeError("boom")
        return ""

    def flat(self):
        return " | ".join(" ".join(c) for c in self.calls)


class TestDockerRollback:
    @pytest.mark.asyncio
    async def test_failed_inject_reconnects_the_network(self):
        service = _FakeSandboxService(
            container_name="dind", fail_on=["docker", "network", "disconnect"]
        )
        result = await DockerChaosInjector(sandbox_service=service).inject(
            NETWORK_DISCONNECT, NS
        )

        assert not result.success
        assert any(c[:3] == ["docker", "network", "connect"] for c in service.calls)

    @pytest.mark.asyncio
    async def test_rollback_failure_still_reports_failure(self):
        """되돌리기까지 실패해도 호출자는 '주입 실패'를 받아야 한다."""
        service = _FakeSandboxService(container_name="dind", fail_on=["docker"])
        result = await DockerChaosInjector(sandbox_service=service).inject(
            NETWORK_DISCONNECT, NS
        )
        assert not result.success


class TestLinuxRollback:
    @pytest.mark.asyncio
    async def test_failed_inject_clears_the_signal_file(self):
        """신호 파일이 남으면 supervisor 가 나중에 장애를 일으킨다."""

        def fails_while_raising_the_signal(argv):
            joined = " ".join(argv)
            return ".signals/disk_pressure" in joined and "rm" not in joined

        service = _FakeSandboxService(
            container_name="shell", fail_when=fails_while_raising_the_signal
        )
        result = await LinuxChaosInjector(sandbox_service=service).inject(DISK_PRESSURE, NS)

        assert not result.success
        cleanup = [c for c in service.calls if "rm" in " ".join(c)]
        assert any(".signals/disk_pressure" in " ".join(c) for c in cleanup)

    @pytest.mark.asyncio
    async def test_missing_sandbox_does_not_raise(self):
        """샌드박스 자체를 못 찾아도 예외가 아니라 실패 결과로 돌려준다."""
        service = _FakeSandboxService(container_name="shell", raise_on_reference=True)
        result = await LinuxChaosInjector(sandbox_service=service).inject(DISK_PRESSURE, NS)

        assert not result.success
        assert "sandbox" in result.message


class TestKubernetesRollback:
    """ChaosMeshInjector 는 클러스터 접속이 필요하므로 핸들러만 갈아끼워 검증한다."""

    def _injector(self):
        injector = ChaosMeshInjector.__new__(ChaosMeshInjector)
        injector._active_chaos = {}
        return injector

    @pytest.mark.asyncio
    async def test_failed_apply_calls_the_matching_revert(self, monkeypatch):
        reverted = []

        def apply_handler(self, chaos_id, namespace):
            raise RuntimeError("두 번째 단계에서 실패")

        def revert_handler(self, chaos_id, namespace):
            reverted.append((chaos_id, namespace))

        monkeypatch.setattr(
            ChaosMeshInjector,
            "_CHAOS_HANDLERS",
            {"pod_failure": (apply_handler, revert_handler)},
        )

        result = await self._injector().inject("pod_failure", NS)

        assert not result.success
        assert [ns for _, ns in reverted] == [NS]

    @pytest.mark.asyncio
    async def test_failed_inject_is_not_recorded_as_active(self, monkeypatch):
        """실패한 주입을 활성으로 기록하면 없는 장애를 되돌리려 한다."""

        def apply_handler(self, chaos_id, namespace):
            raise RuntimeError("실패")

        monkeypatch.setattr(
            ChaosMeshInjector,
            "_CHAOS_HANDLERS",
            {"pod_failure": (apply_handler, lambda self, chaos_id, namespace: None)},
        )

        injector = self._injector()
        await injector.inject("pod_failure", NS)
        assert injector._active_chaos == {}

    @pytest.mark.asyncio
    async def test_rollback_failure_still_reports_failure(self, monkeypatch):
        def apply_handler(self, chaos_id, namespace):
            raise RuntimeError("주입 실패")

        def revert_handler(self, chaos_id, namespace):
            raise RuntimeError("복구도 실패")

        monkeypatch.setattr(
            ChaosMeshInjector,
            "_CHAOS_HANDLERS",
            {"pod_failure": (apply_handler, revert_handler)},
        )

        result = await self._injector().inject("pod_failure", NS)

        assert not result.success
        assert "주입 실패" in result.message
