from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

BACKEND_DIR = Path(__file__).resolve().parents[2]

# 0002 가 도입한 컬럼. 스키마가 최신인지 판정하는 기준으로 쓴다.
_HEAD_ATTEMPT_COLUMNS = {"environment", "chaos_id", "sandbox_id"}


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


def _alembic_head() -> str | None:
    """마이그레이션 스크립트가 가리키는 head 리비전."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:
        return None


def stamp_head_if_schema_current(connection: Connection) -> None:
    """create_all 로 만들어진 스키마에 Alembic 이력을 남긴다.

    `create_all` 은 항상 최신 모델대로 테이블을 만들지만 `alembic_version` 은
    남기지 않는다. 그 상태로 나중에 `alembic upgrade head` 를 돌리면 이미 있는
    컬럼을 다시 추가하려다 DuplicateColumnError 로 실패한다.

    그래서 create_all 직후, **스키마가 실제로 head 상태일 때만** head 로 표시한다.

    - 빈 DB → create_all 이 최신 스키마를 만든 상태 → stamp (이후 upgrade 는 no-op)
    - 기존 옛 DB → create_all 은 기존 테이블을 ALTER 하지 않아 스키마가 옛 상태다.
      여기서 stamp 하면 거짓이 되어 보정이 영영 적용되지 않으므로 **stamp 하지 않는다.**
      이 DB 는 `alembic upgrade head` 가 0001 의 보정 경로로 맞춘다.
    """
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())

    if "alembic_version" in tables:
        return
    if "mission_attempts" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("mission_attempts")}
    if not _HEAD_ATTEMPT_COLUMNS <= columns:
        # 옛 스키마다. 마이그레이션이 보정해야 하므로 이력을 남기지 않는다.
        return

    head = _alembic_head()
    if head is None:
        return

    connection.execute(text(
        "CREATE TABLE IF NOT EXISTS alembic_version ("
        " version_num VARCHAR(32) NOT NULL,"
        " CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    ))
    connection.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
        {"version": head},
    )


def schema_needs_migration(connection: Connection) -> bool:
    """스키마가 최신이 아니어서 `alembic upgrade head` 가 필요한 상태인가."""
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    if "mission_attempts" not in tables:
        return True
    columns = {column["name"] for column in inspector.get_columns("mission_attempts")}
    return not _HEAD_ATTEMPT_COLUMNS <= columns
