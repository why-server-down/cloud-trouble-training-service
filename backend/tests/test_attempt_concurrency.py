"""사용자당 진행 중 attempt 1개 제약 (BE-24).

앞선 조회(get_active_attempt)는 동시 요청 두 개를 모두 통과시킬 수 있다.
실제 방어선은 DB partial unique index 이고, 서비스는 그 IntegrityError 를
"이미 진행 중" 으로 번역하면서 **이미 주입한 장애를 되돌려야** 한다.
되돌리지 않으면 아무도 시작하지 않은 장애가 네임스페이스에 남는다.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Index
from sqlalchemy.exc import IntegrityError

from app.models import MissionAttempt
from app.services.chaos_injector import ChaosResult
from app.services.mission_service import MissionService


class _Injector:
    environment = "kubernetes"

    def __init__(self):
        self.inject = AsyncMock(
            return_value=ChaosResult(success=True, chaos_id="pod-failure-abc", message="ok")
        )
        self.revert = AsyncMock(return_value=True)

    def supported_chaos_types(self):
        return frozenset({"pod_failure"})


class _Mission:
    def __init__(self):
        self.id = uuid.uuid4()
        self.level = 1
        self.environment = "kubernetes"
        self.chaos_type = "pod_failure"


class _User:
    def __init__(self):
        self.id = uuid.uuid4()


class _Db:
    """조회는 통과시키고 commit 에서만 제약이 걸리는 DB."""

    def __init__(self, mission, *, commit_error=None):
        self._mission = mission
        self._commit_error = commit_error
        self.added = []
        self.rollbacks = 0
        self.commits = 0

    async def execute(self, stmt):
        mission = self._mission

        class R:
            def scalar_one_or_none(self):
                # 진행 중 attempt 조회는 None, 미션 조회는 mission
                return mission if "missions" in str(stmt).lower() else None

            def scalars(self):
                return self

            def all(self):
                return []

        return R()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1
        if self._commit_error is not None:
            raise self._commit_error

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        pass


def _service(injector):
    return MissionService(
        injector_for=lambda environment: injector,
        validation_for=lambda environment: None,
        scoring_service=None,
    )


def _integrity_error():
    return IntegrityError("INSERT", {}, Exception("uq_mission_attempts_user_in_progress"))


class TestUniqueIndexDeclaration:
    def test_partial_unique_index_exists_on_the_model(self):
        """마이그레이션만이 아니라 모델에도 있어야 create_all 경로가 같아진다."""
        indexes = {
            arg.name: arg
            for arg in MissionAttempt.__table_args__
            if isinstance(arg, Index)
        }
        index = indexes.get("uq_mission_attempts_user_in_progress")
        assert index is not None
        assert index.unique
        assert "in_progress" in str(index.dialect_options["postgresql"]["where"])


class TestSecondConcurrentStart:
    @pytest.mark.asyncio
    async def test_integrity_error_becomes_a_user_facing_message(self):
        injector = _Injector()
        mission = _Mission()
        db = _Db(mission, commit_error=_integrity_error())

        with pytest.raises(ValueError, match="이미 진행 중인 미션"):
            await _service(injector).start_mission(db, _User(), mission.id)

    @pytest.mark.asyncio
    async def test_losing_request_reverts_its_own_chaos(self):
        """진 쪽이 주입한 장애를 되돌리지 않으면 고아 장애가 남는다."""
        injector = _Injector()
        mission = _Mission()
        db = _Db(mission, commit_error=_integrity_error())

        with pytest.raises(ValueError):
            await _service(injector).start_mission(db, _User(), mission.id)

        assert db.rollbacks == 1
        injector.revert.assert_awaited_once()
        assert injector.revert.await_args.args[0] == "pod-failure-abc"

    @pytest.mark.asyncio
    async def test_any_commit_failure_also_reverts(self):
        """제약 위반이 아닌 실패도 장애를 남기면 안 된다."""
        injector = _Injector()
        mission = _Mission()
        db = _Db(mission, commit_error=RuntimeError("connection lost"))

        with pytest.raises(RuntimeError):
            await _service(injector).start_mission(db, _User(), mission.id)

        injector.revert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_successful_start_does_not_revert(self):
        injector = _Injector()
        mission = _Mission()
        db = _Db(mission)

        attempt = await _service(injector).start_mission(db, _User(), mission.id)

        injector.revert.assert_not_awaited()
        assert attempt.chaos_id == "pod-failure-abc"
        assert attempt.environment == "kubernetes"
