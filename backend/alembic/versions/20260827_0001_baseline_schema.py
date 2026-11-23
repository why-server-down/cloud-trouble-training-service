"""baseline schema

Revision ID: 0001
Revises: 
Create Date: 2026-08-27 13:35:18.953545

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """baseline 스키마를 만든다.

    이 프로젝트는 Alembic 도입 전까지 `Base.metadata.create_all` 과
    `ensure_schema_compatibility()` 의 수동 ALTER 로 스키마를 관리했다.
    그래서 리비전 이력이 없는 기존 로컬 DB 가 팀원마다 존재하고, 그 상태도
    제각각이다(예: environment 컬럼이 있는 DB 와 없는 DB).

    이 리비전은 두 경우를 모두 받아 같은 baseline 으로 수렴시킨다.
      - 빈 DB      : 전체 테이블을 새로 만든다.
      - 기존 DB    : 예전 ensure_schema_compatibility() 가 하던 idempotent 보정을
                     그대로 수행한다. 별도의 `alembic stamp` 절차가 필요 없다.

    주의: 테이블이 일부만 있는 DB 는 대상이 아니다. 그런 DB 는 재생성한다.
    """
    if "mission_attempts" in _existing_tables():
        _align_existing_schema()
    else:
        _create_all_tables()


def _align_existing_schema() -> None:
    """Alembic 이전에 만들어진 DB 를 baseline 상태로 맞춘다."""
    op.execute("""
        ALTER TABLE mission_attempts
        ADD COLUMN IF NOT EXISTS attempt_type VARCHAR(20) DEFAULT 'static_mission'
    """)
    op.execute("""
        UPDATE mission_attempts SET attempt_type = 'static_mission'
        WHERE attempt_type IS NULL
    """)
    op.execute("ALTER TABLE mission_attempts ALTER COLUMN attempt_type SET NOT NULL")
    op.execute("ALTER TABLE mission_attempts ADD COLUMN IF NOT EXISTS scenario_id UUID")
    op.execute("ALTER TABLE mission_attempts ADD COLUMN IF NOT EXISTS last_validation_result JSON")
    op.execute("ALTER TABLE mission_attempts ALTER COLUMN mission_id DROP NOT NULL")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'mission_attempts_scenario_id_fkey'
            ) THEN
                ALTER TABLE mission_attempts
                ADD CONSTRAINT mission_attempts_scenario_id_fkey
                FOREIGN KEY (scenario_id) REFERENCES generated_scenarios(id);
            END IF;
        END $$;
    """)
    # 캡스톤2 멀티 환경 컬럼
    for table in ("missions", "generated_scenarios", "terminal_sessions"):
        op.execute(f"""
            ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS environment VARCHAR(20) NOT NULL DEFAULT 'kubernetes'
        """)


def _create_all_tables() -> None:
    op.create_table('missions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('chaos_type', sa.String(length=50), nullable=False),
    sa.Column('environment', sa.String(length=20), server_default='kubernetes', nullable=False),
    sa.Column('base_score', sa.Integer(), nullable=False),
    sa.Column('time_limit', sa.Integer(), nullable=False),
    sa.Column('hint_penalty', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('generated_scenarios',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('difficulty', sa.String(length=20), nullable=False),
    sa.Column('environment', sa.String(length=20), server_default='kubernetes', nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('student_brief', sa.Text(), nullable=False),
    sa.Column('internal_summary', sa.Text(), nullable=False),
    sa.Column('fault_type', sa.String(length=50), nullable=False),
    sa.Column('scenario_json', sa.JSON(), nullable=False),
    sa.Column('chaos_plan_json', sa.JSON(), nullable=True),
    sa.Column('validation_json', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('safety_review', sa.JSON(), nullable=True),
    sa.Column('chaos_id', sa.String(length=100), nullable=True),
    sa.Column('base_score', sa.Integer(), nullable=False),
    sa.Column('time_limit', sa.Integer(), nullable=False),
    sa.Column('hint_penalty', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('terminal_sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('namespace', sa.String(length=100), nullable=False),
    sa.Column('environment', sa.String(length=20), server_default='kubernetes', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_activity', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('command_logs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('session_id', sa.UUID(), nullable=False),
    sa.Column('command', sa.Text(), nullable=False),
    sa.Column('output', sa.Text(), nullable=False),
    sa.Column('exit_code', sa.Integer(), nullable=False),
    sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('execution_time', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['terminal_sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mission_attempts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('mission_id', sa.UUID(), nullable=True),
    sa.Column('attempt_type', sa.String(length=20), nullable=False),
    sa.Column('scenario_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('final_score', sa.Integer(), nullable=True),
    sa.Column('hints_used', sa.Integer(), nullable=False),
    sa.Column('last_validation_result', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['mission_id'], ['missions.id'], ),
    sa.ForeignKeyConstraint(['scenario_id'], ['generated_scenarios.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('validation_rules',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('scenario_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('rule_type', sa.String(length=20), nullable=False),
    sa.Column('query', sa.Text(), nullable=False),
    sa.Column('stability_seconds', sa.Integer(), nullable=False),
    sa.Column('is_required', sa.Boolean(), nullable=False),
    sa.Column('guard_status', sa.String(length=20), nullable=False),
    sa.Column('guard_reason', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['scenario_id'], ['generated_scenarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tutor_messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('attempt_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('hint_level', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['attempt_id'], ['mission_attempts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('tutor_messages')
    op.drop_table('validation_rules')
    op.drop_table('mission_attempts')
    op.drop_table('command_logs')
    op.drop_table('terminal_sessions')
    op.drop_table('generated_scenarios')
    op.drop_table('users')
    op.drop_table('missions')
    # ### end Alembic commands ###
