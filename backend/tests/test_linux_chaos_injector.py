"""Linux 환경 장애 주입 (BE-17).

장애 워크로드를 exec 으로 직접 띄우지 않는다. exec 세션이 끝나면 containerd 가
프로세스 그룹째 정리하기 때문이다. injector 는 신호 파일만 만들고 샌드박스의
PID 1 인 supervisor 가 워크로드를 띄운다.
"""
import pathlib

import pytest

from app.core import environments
from app.core.config import settings
from app.services.chaos_injector import BaseChaosInjector
from app.services.command_validator import CommandValidator
from app.services.linux_chaos_injector import (
    CPU_SATURATION,
    DISK_PRESSURE,
    PROCESS_FLOOD,
    LinuxChaosInjector,
)
from app.services.sandbox_service import SandboxRef, SandboxService

NS = "user-abc"
WORKDIR = settings.SANDBOX_LINUX_WORKDIR

# 각 장애를 사용자가 되돌리는 명령. 명령 정책 통과 여부를 여기서 고정한다.
USER_RECOVERY = {
    DISK_PRESSURE: f"rm {WORKDIR}/afterfail-fill.dat",
    CPU_SATURATION: "pkill -f afterfail-cpuburn",
    PROCESS_FLOOD: "pkill -f afterfail-worker",
}


class _FakeSandboxService:
    def __init__(self, output=""):
        self.calls = []
        self.output = output
        self.fail_on = None

    def reference_for(self, *, user_id, namespace, environment):
        return SandboxRef(
            id="s1", namespace=namespace, pod_name="sandbox-s1",
            container_name="shell", environment=environment,
        )

    def exec_in_sandbox(self, sandbox, argv):
        self.calls.append(argv)
        if self.fail_on and argv[: len(self.fail_on)] == self.fail_on:
            raise RuntimeError("boom")
        return self.output


def _injector(output=""):
    fake = _FakeSandboxService(output)
    return LinuxChaosInjector(sandbox_service=fake), fake


def _flat(calls):
    return " | ".join(" ".join(c) for c in calls)


class TestOnlyRecoverableFaultsAreRegistered:
    def test_every_fault_has_a_user_recovery_command(self):
        injector, _ = _injector()
        assert set(injector.supported_chaos_types()) == set(USER_RECOVERY)

    @pytest.mark.parametrize("chaos_type,command", sorted(USER_RECOVERY.items()))
    def test_recovery_command_passes_command_policy(self, chaos_type, command):
        """복구 명령이 BE-16 정책을 통과하지 못하면 그 장애는 등록될 수 없다."""
        result = CommandValidator().validate_delete(
            command, NS, confirmed=True, environment=environments.LINUX
        )
        assert result.is_valid, f"{chaos_type}: {result.error}"

    def test_zombie_fault_is_not_registered(self):
        """busybox sh 가 자식을 곧바로 회수해 좀비가 유지되지 않는다(실측).

        관측되지 않는 장애는 훈련이 될 수 없어 CPU 포화로 대체했다.
        """
        injector, _ = _injector()
        assert not any("zombie" in t for t in injector.supported_chaos_types())


class TestInjectRaisesSignalOnly:
    @pytest.mark.asyncio
    async def test_writes_signal_file(self):
        injector, fake = _injector()
        result = await injector.inject(DISK_PRESSURE, NS)
        assert result.success
        assert f"{WORKDIR}/.signals/disk_pressure" in _flat(fake.calls)

    @pytest.mark.asyncio
    async def test_clears_previous_done_marker(self):
        """이전 실행 표시를 지워야 재주입이 동작한다."""
        injector, fake = _injector()
        await injector.inject(PROCESS_FLOOD, NS)
        assert ".done" in _flat(fake.calls)

    @pytest.mark.asyncio
    async def test_does_not_spawn_workload_directly(self):
        """exec 으로 띄운 백그라운드 프로세스는 살아남지 않는다."""
        injector, fake = _injector()
        await injector.inject(CPU_SATURATION, NS)
        flat = _flat(fake.calls)
        assert "setsid" not in flat and "nohup" not in flat

    @pytest.mark.asyncio
    async def test_chaos_id_encodes_type_for_restart_recovery(self):
        injector, _ = _injector()
        result = await injector.inject(PROCESS_FLOOD, NS)
        assert BaseChaosInjector.chaos_type_from_id(result.chaos_id) == PROCESS_FLOOD

    @pytest.mark.asyncio
    async def test_snapshot_is_recorded(self):
        injector, _ = _injector(output="7")
        result = await injector.inject(PROCESS_FLOOD, NS)
        assert result.metadata["snapshot"]["processes"] == "7"

    @pytest.mark.asyncio
    async def test_unknown_type_fails_without_touching_sandbox(self):
        injector, fake = _injector()
        result = await injector.inject("linux_unknown", NS)
        assert not result.success
        assert fake.calls == []


class TestRevertCleansUp:
    @pytest.mark.asyncio
    async def test_disk_pressure_removes_fill_file(self):
        injector, fake = _injector()
        assert await injector.revert("linux-disk-pressure-abc12345", NS) is True
        assert "afterfail-fill.dat" in _flat(fake.calls)

    @pytest.mark.asyncio
    async def test_process_faults_kill_workloads(self):
        injector, fake = _injector()
        await injector.revert("linux-process-flood-abc12345", NS)
        assert "pkill" in _flat(fake.calls)

    @pytest.mark.asyncio
    async def test_pkill_pattern_does_not_match_itself(self):
        """pkill -f afterfail- 는 자기 명령줄과도 매치돼 스스로를 먼저 죽인다.

        그러면 정리가 중단되고 워크로드가 남는다(실측).
        """
        injector, fake = _injector()
        await injector.revert("linux-process-flood-abc12345", NS)
        pkill = [c for c in fake.calls if "pkill" in " ".join(c)][0]
        assert "[a]fterfail-" in " ".join(pkill)

    @pytest.mark.asyncio
    async def test_signal_is_cleared_so_it_can_be_reused(self):
        injector, fake = _injector()
        await injector.revert("linux-cpu-saturation-abc12345", NS)
        flat = _flat(fake.calls)
        assert ".signals/cpu_saturation" in flat and ".done" in flat

    @pytest.mark.asyncio
    async def test_unknown_chaos_id_returns_false(self):
        injector, _ = _injector()
        assert await injector.revert("bad", NS) is False

    @pytest.mark.asyncio
    async def test_failure_is_reported_for_retry(self):
        injector, fake = _injector()
        fake.fail_on = ["rm", "-f"]
        assert await injector.revert("linux-disk-pressure-abc12345", NS) is False


class TestSafetyLimits:
    """계획서 안전 기준: 호스트를 위협하지 않는다."""

    def test_disk_fill_stays_within_tmpfs_limit(self):
        injector, _ = _injector()
        limit_mb = int(settings.SANDBOX_LINUX_WORKDIR_SIZE.rstrip("Mi"))
        assert injector.DISK_FILL_MB < limit_mb

    def test_process_count_is_bounded_below_pid_limit(self):
        """PID 고갈로 샌드박스가 마비되면 복구도 못 한다."""
        injector, _ = _injector()
        assert injector.FLOOD_PROCESS_COUNT < settings.SANDBOX_LINUX_PID_LIMIT

    def test_cpu_workers_are_bounded(self):
        injector, _ = _injector()
        assert 0 < injector.CPU_BURN_WORKERS <= 4

    def test_workload_directory_is_size_limited_tmpfs(self):
        """호스트 디스크를 채우지 않는다."""
        assert settings.SANDBOX_LINUX_WORKDIR_SIZE.endswith("Mi")


class TestSupervisorScript:
    def _script(self):
        return (
            pathlib.Path(SandboxService._supervisor_script.__module__ and __file__).parent.parent
            / "app" / "services" / "sandbox_assets" / "linux_supervisor.sh"
        ).read_text()

    def test_handles_every_registered_signal(self):
        script = self._script()
        for signal in ("disk_pressure", "cpu_saturation", "process_flood"):
            assert f"handle_signal {signal}" in script

    def test_does_not_restart_workload_after_user_cleanup(self):
        """사용자가 워크로드를 정리하면 다시 띄우지 않는다. 아니면 복구가 불가능하다."""
        assert ".done" in self._script()

    def test_workloads_have_a_duration(self):
        """모든 워크로드에 종료 시점이 있어야 한다."""
        assert "86400" in self._script()
