"""create_all 과 Alembic 이 함께 있을 때의 스키마 부트스트랩 판정 검증.

`create_all` 은 최신 모델대로 테이블을 만들지만 alembic_version 을 남기지 않는다.
이력 없이 최신 스키마만 있는 DB 에 `alembic upgrade head` 를 돌리면 이미 있는
컬럼을 다시 추가하려다 실패했다. 그 회귀를 막는다.

여기서는 판정 로직만 본다(SQLite 로 충분). 실제 PostgreSQL upgrade 경로는
integration 성격이라 별도로 수동 검증한다.
"""
import sqlalchemy as sa

from app.core.database import (
    _alembic_head,
    schema_needs_migration,
    stamp_head_if_schema_current,
)

HEAD_COLUMNS = ("environment", "chaos_id", "sandbox_id")


def _make_attempts_table(connection, *, columns: tuple[str, ...]):
    cols = ", ".join(f"{name} VARCHAR(20)" for name in columns)
    suffix = f", {cols}" if cols else ""
    connection.execute(sa.text(f"CREATE TABLE mission_attempts (id VARCHAR(36){suffix})"))


class TestAlembicHead:
    def test_head_is_resolvable(self):
        """마이그레이션 스크립트에서 head 리비전을 읽을 수 있다."""
        assert _alembic_head() is not None


class TestSchemaNeedsMigration:
    def test_empty_database_needs_migration(self):
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            assert schema_needs_migration(conn) is True

    def test_outdated_schema_needs_migration(self):
        """BE-02 이전 스키마(환경 컬럼 없음)는 마이그레이션이 필요하다."""
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            _make_attempts_table(conn, columns=())
            assert schema_needs_migration(conn) is True

    def test_partially_migrated_schema_needs_migration(self):
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            _make_attempts_table(conn, columns=("environment",))
            assert schema_needs_migration(conn) is True

    def test_current_schema_does_not_need_migration(self):
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            _make_attempts_table(conn, columns=HEAD_COLUMNS)
            assert schema_needs_migration(conn) is False


class TestStampHeadIfSchemaCurrent:
    def test_stamps_when_create_all_produced_current_schema(self):
        """create_all 이 최신 스키마를 만든 경우에만 head 로 표시한다."""
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            _make_attempts_table(conn, columns=HEAD_COLUMNS)
            stamp_head_if_schema_current(conn)

            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
            assert version == _alembic_head()

    def test_does_not_stamp_outdated_schema(self):
        """옛 DB 에 거짓 이력을 남기면 보정이 영영 적용되지 않는다."""
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            _make_attempts_table(conn, columns=())
            stamp_head_if_schema_current(conn)

            tables = set(sa.inspect(conn).get_table_names())
            assert "alembic_version" not in tables

    def test_does_not_touch_existing_version_history(self):
        """이미 이력이 있으면 건드리지 않는다."""
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            _make_attempts_table(conn, columns=HEAD_COLUMNS)
            conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0001')"))

            stamp_head_if_schema_current(conn)

            versions = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all()
            assert versions == ["0001"]

    def test_skips_when_tables_are_absent(self):
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            stamp_head_if_schema_current(conn)
            assert "alembic_version" not in set(sa.inspect(conn).get_table_names())
