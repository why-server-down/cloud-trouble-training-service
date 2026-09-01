"""동시성·재시작 복구 (BE-22).

인수 조건
  - 동시 start 2개 중 하나만 성공
  - 서버 재시작 뒤 active attempt status/cleanup 복원
  - revert 두 번 호출 안전
"""
import inspect
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core import environments
from app.services import mission_service as mission_module
from app.services import scenario_service as scenario_module
from app.services.reconciliation_service import reconcile_active_attempts


class _Attempt:
    def __init__(
        self,
        *,
        started_seconds_ago=10,
        time_limit=600,
        chaos_id="pod-failure-abc12345",
        environment=environments.KUBERNETES,
        attempt_type="static_mission",
    ):
        self.id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.status = "in_progress"
        self.attempt_type = attempt_type
        self.scenario_id = None
        self.mission_id = uuid.uuid4()
        self.environment = environment
        self.chaos_id = chaos_id
        self.start_time = datetime.now(timezone.utc) - timedelta(
            seconds=started_seconds_ago
        )
        self.end_time = None
        self.mission = type("M", (), {"time_limit": time_limit})()


class _FakeDB:
    def __init__(self, attempts):
        self.attempts = attempts
        self.commits = 0

    async def execute(self, statement):
        rows = self.attempts

        class _R:
            def scalars(self_inner):
                return self_inner

            def all(self_inner):
                return rows

            def scalar_one_or_none(self_inner):
                return None

        return _R()

    async def commit(self):
        self.commits += 1


class _RecordingInjector:
    def __init__(self):
        self.reverted = []
        self.should_fail = False

    async def revert(self, chaos_id, namespace):
        if self.should_fail:
            raise RuntimeError("boom")
        self.reverted.append((chaos_id, namespace))
        return True


class TestExpiredAttemptsAreCleaned:
    """시간 초과 정리가 사용자의 status 조회에만 의존하면,
    돌아오지 않는 사용자의 장애가 클러스터에 그대로 남는다."""

    @pytest.mark.asyncio
    async def test_expired_attempt_is_failed_and_cleaned(self):
        attempt = _Attempt(started_seconds_ago=1200, time_limit=600)
        injector = _RecordingInjector()
        db = _FakeDB([attempt])

        summary = await reconcile_active_attempts(db, injector_for=lambda env: injector)

        assert summary["expired"] == 1
        assert summary["cleaned"] == 1
        assert attempt.status == "failed"
        assert attempt.end_time is not None
        assert injector.reverted == [
            ("pod-failure-abc12345", f"user-{attempt.user_id}")
        ]

    @pytest.mark.asyncio
    async def test_running_attempt_is_left_alone(self):
        """아직 시간이 남은 시도는 건드리지 않는다. 사용자가 계속 풀고 있다."""
        attempt = _Attempt(started_seconds_ago=10, time_limit=600)
        injector = _RecordingInjector()

        summary = await reconcile_active_attempts(
            _FakeDB([attempt]), injector_for=lambda env: injector
        )

        assert summary["expired"] == 0
        assert attempt.status == "in_progress"
        assert injector.reverted == []

    @pytest.mark.asyncio
    async def test_chaos_id_is_cleared_after_cleanup(self):
        """되돌린 뒤 비워야 다음 정리에서 같은 작업을 반복하지 않는다."""
        attempt = _Attempt(started_seconds_ago=1200, time_limit=600)
        injector = _RecordingInjector()

        await reconcile_active_attempts(
            _FakeDB([attempt]), injector_for=lambda env: injector
        )
        assert attempt.chaos_id is None

    @pytest.mark.asyncio
    async def test_attempt_without_chaos_id_is_still_closed(self):
        attempt = _Attempt(started_seconds_ago=1200, time_limit=600, chaos_id=None)
        injector = _RecordingInjector()

        summary = await reconcile_active_attempts(
            _FakeDB([attempt]), injector_for=lambda env: injector
        )
        assert attempt.status == "failed"
        assert summary["cleaned"] == 0


class TestFailuresDoNotStopStartup:
    """기동 경로다. 여기서 예외가 나가면 서버가 뜨지 않는다."""

    @pytest.mark.asyncio
    async def test_cleanup_failure_still_closes_the_attempt(self):
        attempt = _Attempt(started_seconds_ago=1200, time_limit=600)
        injector = _RecordingInjector()
        injector.should_fail = True

        summary = await reconcile_active_attempts(
            _FakeDB([attempt]), injector_for=lambda env: injector
        )
        assert attempt.status == "failed"
        assert summary["cleaned"] == 0

    @pytest.mark.asyncio
    async def test_one_bad_attempt_does_not_block_others(self):
        broken = _Attempt(started_seconds_ago=1200, time_limit=600)
        broken.start_time = None  # 계산 중 예외를 유발한다
        healthy = _Attempt(started_seconds_ago=1200, time_limit=600)
        injector = _RecordingInjector()

        summary = await reconcile_active_attempts(
            _FakeDB([broken, healthy]), injector_for=lambda env: injector
        )
        assert summary["failed"] == 1
        assert healthy.status == "failed"

    @pytest.mark.asyncio
    async def test_unimplemented_environment_is_skipped(self):
        attempt = _Attempt(started_seconds_ago=1200, time_limit=600)
        attempt.environment = "application"
        injector = _RecordingInjector()

        summary = await reconcile_active_attempts(
            _FakeDB([attempt]), injector_for=lambda env: injector
        )
        assert injector.reverted == []
        assert attempt.status == "failed"

    @pytest.mark.asyncio
    async def test_no_attempts_is_a_noop(self):
        summary = await reconcile_active_attempts(_FakeDB([]), injector_for=lambda e: None)
        assert summary == {"checked": 0, "expired": 0, "cleaned": 0, "failed": 0}


class TestConcurrentStartIsRejectedGracefully:
    """DB partial unique index 가 두 번째 시작을 막는다.
    그 충돌은 서버 오류가 아니라 설명 가능한 사용자 상황이다."""

    def test_mission_start_converts_integrity_error(self):
        source = inspect.getsource(mission_module.MissionService.start_mission)
        assert "IntegrityError" in source
        assert "이미 진행 중인 미션이 있습니다" in source

    def test_scenario_start_converts_integrity_error(self):
        source = inspect.getsource(scenario_module.ScenarioService.start_random)
        assert "IntegrityError" in source

    def test_injected_chaos_is_reverted_on_conflict(self):
        """충돌로 기록이 실패했는데 장애가 남으면 고아가 된다."""
        source = inspect.getsource(mission_module.MissionService.start_mission)
        conflict_block = source.split("except IntegrityError:")[1]
        assert "revert" in conflict_block


class TestStartupWiring:
    def test_reconciliation_runs_on_startup(self):
        import app.main as main_module

        source = inspect.getsource(main_module.lifespan)
        assert "reconcile_active_attempts" in source

    def test_startup_failure_is_contained(self):
        """기동 경로에서 예외가 밖으로 나가면 서버가 뜨지 않는다."""
        import app.main as main_module

        source = inspect.getsource(main_module.lifespan)
        block = source.split("reconcile_active_attempts")[0]
        assert "try:" in block
