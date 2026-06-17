from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def ensure_schema_compatibility(conn: AsyncConnection):
    """Apply lightweight, idempotent schema fixes for existing local databases."""
    await conn.execute(text("""
        ALTER TABLE mission_attempts
        ADD COLUMN IF NOT EXISTS attempt_type VARCHAR(20) DEFAULT 'static_mission'
    """))
    await conn.execute(text("""
        UPDATE mission_attempts
        SET attempt_type = 'static_mission'
        WHERE attempt_type IS NULL
    """))
    await conn.execute(text("""
        ALTER TABLE mission_attempts
        ALTER COLUMN attempt_type SET NOT NULL
    """))
    await conn.execute(text("""
        ALTER TABLE mission_attempts
        ADD COLUMN IF NOT EXISTS scenario_id UUID
    """))
    await conn.execute(text("""
        ALTER TABLE mission_attempts
        ADD COLUMN IF NOT EXISTS last_validation_result JSON
    """))
    await conn.execute(text("""
        ALTER TABLE mission_attempts
        ALTER COLUMN mission_id DROP NOT NULL
    """))
    await conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'mission_attempts_scenario_id_fkey'
            ) THEN
                ALTER TABLE mission_attempts
                ADD CONSTRAINT mission_attempts_scenario_id_fkey
                FOREIGN KEY (scenario_id) REFERENCES generated_scenarios(id);
            END IF;
        END $$;
    """))
