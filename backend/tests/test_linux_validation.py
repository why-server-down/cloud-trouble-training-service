"""Linux 환경 해결 검증 (BE-18).

명령 출력을 그대로 비교하지 않고 숫자로 뽑아 임계값과 비교한다.
정답이 API 메시지로 새지 않는지도 고정한다.
"""
import pytest

from app.core import environments
from app.core.config import settings
from app.services.linux_chaos_injector import (
    CPU_SATURATION,
    DISK_PRESSURE,
    PROCESS_FLOOD,
)
from app.services.linux_validation_service import LinuxValidationService
from app.services.sandbox_service import SandboxRef
from app.services.validation_service import RETRY_MESSAGE

NS = "user-abc"


class _FakeSandboxService:
    def __init__(self, output="", fail=False):
        self.output = output
        self.fail = fail
        self.calls = []

    def reference_for(self, *, user_id, namespace, environment):
        return SandboxRef(
            id="s1", namespace=namespace, pod_name="sandbox-s1",
            container_name="shell", environment=environment,
        )

    def exec_in_sandbox(self, sandbox, argv):
        self.calls.append((sandbox.namespace, argv))
        if self.fail:
            raise RuntimeError("boom")
        return self.output


def _service(output="", fail=False):
    fake = _FakeSandboxService(output, fail)
    return LinuxValidationService(sandbox_service=fake), fake


class TestDiskPressure:
    @pytest.mark.asyncio
    async def test_resolved_when_space_is_freed(self):
        service, _ = _service("0%")
        result = await service.check_resolution(DISK_PRESSURE, NS)
        assert result.is_resolved
        assert result.details["workdir_used_percent"] == 0

    @pytest.mark.asyncio
    async def test_not_resolved_while_full(self):
        service, _ = _service("88%")
        assert not (await service.check_resolution(DISK_PRESSURE, NS)).is_resolved

    @pytest.mark.asyncio
    async def test_partial_cleanup_is_enough(self):
        """정확히 0% 를 요구하면 훈련이 아니라 청소가 된다."""
        service, _ = _service("5%")
        assert (await service.check_resolution(DISK_PRESSURE, NS)).is_resolved


class TestProcessWorkloads:
    @pytest.mark.asyncio
    async def test_process_flood_resolved_when_cleared(self):
        service, _ = _service("0")
        result = await service.check_resolution(PROCESS_FLOOD, NS)
        assert result.is_resolved
        assert result.details["worker_processes"] == 0

    @pytest.mark.asyncio
    async def test_process_flood_not_resolved_while_running(self):
        service, _ = _service("120")
        assert not (await service.check_resolution(PROCESS_FLOOD, NS)).is_resolved

    @pytest.mark.asyncio
    async def test_cpu_saturation_resolved_when_cleared(self):
        service, _ = _service("0")
        assert (await service.check_resolution(CPU_SATURATION, NS)).is_resolved

    @pytest.mark.asyncio
    async def test_cpu_saturation_not_resolved_while_burning(self):
        service, _ = _service("2")
        assert not (await service.check_resolution(CPU_SATURATION, NS)).is_resolved


class TestSelfExcludingPattern:
    """grep 이 자기 명령줄을 세면 복구해도 영영 통과하지 못한다(실측)."""

    def test_pattern_wraps_first_character(self):
        assert LinuxValidationService._self_excluding_pattern("afterfail-worker") == (
            "[a]fterfail-worker"
        )

    @pytest.mark.asyncio
    async def test_count_query_uses_the_pattern(self):
        service, fake = _service("0")
        await service.check_resolution(PROCESS_FLOOD, NS)
        _, argv = fake.calls[0]
        assert "[a]fterfail-worker" in " ".join(argv)


class TestLatencyIsMeasured:
    @pytest.mark.asyncio
    async def test_duration_is_reported(self):
        """계획서의 300ms 목표를 확인할 수 있어야 한다."""
        service, _ = _service("0")
        result = await service.check_resolution(PROCESS_FLOOD, NS)
        assert "duration_ms" in result.details
        assert result.details["duration_ms"] >= 0


class TestIsolationAndFailure:
    @pytest.mark.asyncio
    async def test_checks_only_the_given_namespace(self):
        service, fake = _service("0")
        await service.check_resolution(PROCESS_FLOOD, "user-1")
        await service.check_resolution(PROCESS_FLOOD, "user-2")
        assert [ns for ns, _ in fake.calls] == ["user-1", "user-2"]

    @pytest.mark.asyncio
    async def test_exec_failure_becomes_retry(self):
        service, _ = _service(fail=True)
        result = await service.check_resolution(DISK_PRESSURE, NS)
        assert not result.is_resolved
        assert result.message == RETRY_MESSAGE

    @pytest.mark.asyncio
    async def test_unknown_chaos_type_becomes_retry(self):
        service, fake = _service("0")
        result = await service.check_resolution("linux_unknown", NS)
        assert not result.is_resolved
        assert fake.calls == []

    @pytest.mark.asyncio
    async def test_message_does_not_leak_the_answer(self):
        service, _ = _service("120")
        result = await service.check_resolution(PROCESS_FLOOD, NS)
        for leak in ("pkill", "afterfail", "rm ", "/tmp"):
            assert leak not in result.message


class TestEnvironmentActivation:
    def test_linux_is_implemented(self):
        assert environments.is_implemented(environments.LINUX)

    def test_all_required_environments_are_open(self):
        """캡스톤2 필수 환경 3종이 모두 열렸다."""
        assert set(environments.IMPLEMENTED_ENVIRONMENTS) == set(
            environments.SUPPORTED_ENVIRONMENTS
        )

    def test_linux_advertises_what_it_provides(self):
        """capabilities 는 구현과 함께 갱신해야 한다.

        2026-09-02: ai_scenario·tutor·observability 가 모두 붙어
        (static_mission, terminal) 표기가 낡았다. 각 capability 의 배선 확인은
        test_environment_contract.py 가 담당한다.
        """
        items = {item["id"]: item for item in environments.availability()}
        linux = items[environments.LINUX]
        assert linux["status"] == "available"
        assert "static_mission" in linux["capabilities"]
        assert "terminal" in linux["capabilities"]

    def test_linux_missions_are_seeded(self):
        from app.services.seed_data import MISSIONS

        linux = [m for m in MISSIONS if m["environment"] == environments.LINUX]
        assert sorted(m["level"] for m in linux) == [1, 2, 3]

    def test_every_linux_mission_has_an_injector_and_validator(self):
        from app.services.linux_chaos_injector import LinuxChaosInjector
        from app.services.seed_data import MISSIONS

        supported = LinuxChaosInjector.__new__(LinuxChaosInjector).supported_chaos_types()
        for mission in MISSIONS:
            if mission["environment"] != environments.LINUX:
                continue
            assert mission["chaos_type"] in supported
            assert mission["chaos_type"] in LinuxValidationService._CHECKS
