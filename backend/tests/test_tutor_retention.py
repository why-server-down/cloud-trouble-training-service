"""튜터 대화 보존 정책 (BE-29).

인수 조건
  - 보존 기간이 지난 메시지가 삭제되고, 진행 중 attempt 의 메시지는 남는다
  - 반복 실행해도 안전하다
  - 삭제가 실패해도 호출한 경로에 영향을 주지 않는다
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models import MissionAttempt, TutorMessage
from app.services import retention_service
from app.services.retention_service import purge_expired_tutor_messages

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


class _Result:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _FakeDB:
    """실행된 statement 를 기록하고, 배치마다 지운 행 수를 돌려준다."""

    def __init__(self, rowcounts=(0,), error=None):
        self.statements = []
        self._rowcounts = list(rowcounts)
        self._error = error
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement):
        self.statements.append(statement)
        if self._error is not None:
            raise self._error
        return _Result(self._rowcounts.pop(0) if self._rowcounts else 0)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    def sql(self, index=0):
        return str(self.statements[index]).lower()

    def params(self, index=0):
        return self.statements[index].compile().params


class TestWhatGetsDeleted:
    @pytest.mark.asyncio
    async def test_only_messages_older_than_the_retention_window(self):
        db = _FakeDB(rowcounts=(3,))
        summary = await purge_expired_tutor_messages(db, now=NOW)

        assert summary["deleted"] == 3
        sql = db.sql()
        assert "delete from tutor_messages" in sql
        assert "created_at <" in sql

    @pytest.mark.asyncio
    async def test_in_progress_attempts_are_excluded(self):
        """진행 중 훈련의 대화가 사라지면 튜터가 앞의 문맥을 잃는다."""
        db = _FakeDB(rowcounts=(1,))
        await purge_expired_tutor_messages(db, now=NOW)

        sql = db.sql()
        assert "not in" in sql
        assert "mission_attempts" in sql
        assert "in_progress" in db.params().values()

    @pytest.mark.asyncio
    async def test_cutoff_uses_the_configured_window(self, monkeypatch):
        monkeypatch.setattr(settings, "TUTOR_MESSAGE_RETENTION_DAYS", 7)
        db = _FakeDB(rowcounts=(0,))
        summary = await purge_expired_tutor_messages(db, now=NOW)

        assert summary["retention_days"] == 7
        assert NOW - timedelta(days=7) in db.params().values()


class TestRepeatedRuns:
    @pytest.mark.asyncio
    async def test_nothing_to_delete_is_a_no_op(self):
        db = _FakeDB(rowcounts=(0,))
        summary = await purge_expired_tutor_messages(db, now=NOW)

        assert summary["deleted"] == 0
        assert len(db.statements) == 1  # 한 배치 확인하고 멈춘다

    @pytest.mark.asyncio
    async def test_deletes_in_batches_until_drained(self, monkeypatch):
        """한 트랜잭션이 테이블을 오래 잡지 않게 나눠 지운다."""
        monkeypatch.setattr(settings, "RETENTION_DELETE_BATCH", 2)
        db = _FakeDB(rowcounts=(2, 2, 1))
        summary = await purge_expired_tutor_messages(db, now=NOW)

        assert summary["deleted"] == 5
        assert len(db.statements) == 3
        assert db.commits == 3

    @pytest.mark.asyncio
    async def test_batch_loop_is_bounded(self, monkeypatch):
        """계속 가득 찬 배치가 돌아와도 기동이 막히지 않는다."""
        monkeypatch.setattr(settings, "RETENTION_DELETE_BATCH", 1)
        db = _FakeDB(rowcounts=[1] * 1000)
        summary = await purge_expired_tutor_messages(db, now=NOW)

        assert len(db.statements) == retention_service._MAX_BATCHES
        assert summary["deleted"] == retention_service._MAX_BATCHES


class TestFailureIsolation:
    @pytest.mark.asyncio
    async def test_failure_does_not_propagate(self):
        """정리 실패가 기동이나 요청 처리를 막으면 안 된다."""
        db = _FakeDB(error=RuntimeError("connection lost"))
        summary = await purge_expired_tutor_messages(db, now=NOW)

        assert summary["failed"] is True
        assert db.rollbacks == 1

    @pytest.mark.asyncio
    async def test_disabled_retention_touches_nothing(self, monkeypatch):
        monkeypatch.setattr(settings, "TUTOR_MESSAGE_RETENTION_DAYS", 0)
        db = _FakeDB(rowcounts=(5,))
        summary = await purge_expired_tutor_messages(db, now=NOW)

        assert summary["deleted"] == 0
        assert db.statements == []


class TestNoContentInObservability:
    def test_metric_labels_carry_no_message_content(self):
        from app.core.metrics import RETENTION_DELETIONS

        assert RETENTION_DELETIONS._labelnames == ("table",)


class TestModelDeclaresTheIndex:
    def test_created_at_is_indexed(self):
        """정리 작업이 훑는 컬럼이다. 인덱스가 없으면 매번 전체 스캔이 된다."""
        indexes = {index.name for index in TutorMessage.__table__.indexes}
        assert "ix_tutor_messages_created_at" in indexes

    def test_retention_todo_is_resolved(self):
        import inspect

        import app.models as models

        source = inspect.getsource(models)
        assert "TODO(phase7)" not in source


class TestStartupWiring:
    def test_startup_runs_retention(self):
        """별도 스케줄러를 만들지 않고 기동 경로에 얹는다."""
        import inspect

        import app.main as main

        source = inspect.getsource(main.lifespan)
        assert "purge_expired_tutor_messages" in source
        # 실패해도 기동을 막지 않아야 한다
        assert "startup retention failed" in source

    def test_attempt_model_is_the_exclusion_source(self):
        assert MissionAttempt.__tablename__ == "mission_attempts"
