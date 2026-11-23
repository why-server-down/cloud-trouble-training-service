"""attempt environment and chaos state

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-27 13:35:30.061055

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 이 리비전 시점의 허용 환경 값. core/environments.py 를 import 하지 않고 리터럴로
# 박제한다. 나중에 목록이 바뀌어도 과거 마이그레이션의 의미가 달라지면 안 된다.
ENVIRONMENTS = "'kubernetes', 'docker', 'linux'"
ATTEMPT_TYPES = "'static_mission', 'ai_scenario'"

ENVIRONMENT_TABLES = ("missions", "generated_scenarios", "terminal_sessions", "mission_attempts")


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _has_constraint(name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": name},
        )
        .scalar()
    )


def _has_index(name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
            {"name": name},
        )
        .scalar()
    )


def upgrade() -> None:
    """이 리비전은 idempotent 하다.

    Alembic 도입 전 `create_all` 로 만들어진 DB 는 이력(alembic_version) 없이도
    최신 컬럼·제약을 이미 갖고 있을 수 있다. 그런 DB 에 이 리비전이 적용될 때
    중복 생성으로 실패하지 않도록 각 단계에서 존재 여부를 먼저 확인한다.
    """
    # 1) attempt 가 환경과 장애/샌드박스 식별자를 직접 갖는다.
    #    이전에는 mission/scenario 를 join 해야 환경을 알 수 있었고, chaos id 는
    #    프로세스 메모리에만 있어 서버 재시작 후 정리가 불가능했다.
    attempt_columns = _columns('mission_attempts')
    if 'environment' not in attempt_columns:
        op.add_column(
            'mission_attempts',
            sa.Column('environment', sa.String(length=20), server_default='kubernetes', nullable=False),
        )
    if 'chaos_id' not in attempt_columns:
        op.add_column('mission_attempts', sa.Column('chaos_id', sa.String(length=100), nullable=True))
    if 'sandbox_id' not in attempt_columns:
        op.add_column('mission_attempts', sa.Column('sandbox_id', sa.String(length=100), nullable=True))

    # 2) 기존 행의 environment 를 참조 대상에서 backfill 한다.
    #    (server_default 로 이미 'kubernetes' 가 채워져 있으므로 값이 다른 것만 갱신된다)
    op.execute("""
        UPDATE mission_attempts a
        SET environment = m.environment
        FROM missions m
        WHERE a.mission_id = m.id
    """)
    op.execute("""
        UPDATE mission_attempts a
        SET environment = s.environment
        FROM generated_scenarios s
        WHERE a.scenario_id = s.id
    """)

    # 3) partial unique index 를 걸기 전에 기존 중복을 정리한다.
    #    애플리케이션은 이미 사용자당 in_progress 1개를 전제(scalar_one_or_none)하므로
    #    중복은 그 자체로 깨진 상태다. 가장 최근 것만 남기고 나머지는 포기 처리한다.
    op.execute("""
        UPDATE mission_attempts
        SET status = 'abandoned',
            end_time = COALESCE(end_time, now())
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY start_time DESC) AS rn
                FROM mission_attempts
                WHERE status = 'in_progress'
            ) ranked
            WHERE ranked.rn > 1
        )
    """)

    # 4) 허용 값 제약. 애플리케이션 검증만으로는 잘못된 값이 DB 에 남는 것을 못 막는다.
    for table in ENVIRONMENT_TABLES:
        name = f"ck_{table}_environment"
        if not _has_constraint(name):
            op.create_check_constraint(name, table, f"environment IN ({ENVIRONMENTS})")

    if not _has_constraint("ck_mission_attempts_attempt_type"):
        op.create_check_constraint(
            "ck_mission_attempts_attempt_type",
            "mission_attempts",
            f"attempt_type IN ({ATTEMPT_TYPES})",
        )

    # attempt_type 과 실제 FK 조합이 어긋난 행을 막는다.
    if not _has_constraint("ck_mission_attempts_type_refs"):
        op.create_check_constraint(
            "ck_mission_attempts_type_refs",
            "mission_attempts",
            "(attempt_type = 'static_mission'"
            " AND mission_id IS NOT NULL AND scenario_id IS NULL)"
            " OR (attempt_type = 'ai_scenario'"
            " AND scenario_id IS NOT NULL AND mission_id IS NULL)",
        )

    # 5) 사용자당 진행 중 attempt 는 최대 1개.
    if not _has_index('uq_mission_attempts_user_in_progress'):
        op.create_index(
            'uq_mission_attempts_user_in_progress',
            'mission_attempts',
            ['user_id'],
            unique=True,
            postgresql_where=sa.text("status = 'in_progress'"),
        )


def downgrade() -> None:
    """스키마는 되돌린다.

    단 upgrade 중 수행한 데이터 보정(중복 in_progress 를 abandoned 로 정리)은
    되돌리지 않는다. 어떤 행이 원래 in_progress 였는지 기록해 두지 않기 때문이며,
    되돌리더라도 다시 깨진 상태로 만들 뿐이다.
    """
    op.drop_index(
        'uq_mission_attempts_user_in_progress',
        table_name='mission_attempts',
        postgresql_where=sa.text("status = 'in_progress'"),
    )
    op.drop_constraint("ck_mission_attempts_type_refs", "mission_attempts", type_="check")
    op.drop_constraint("ck_mission_attempts_attempt_type", "mission_attempts", type_="check")
    for table in ENVIRONMENT_TABLES:
        op.drop_constraint(f"ck_{table}_environment", table, type_="check")
    op.drop_column('mission_attempts', 'sandbox_id')
    op.drop_column('mission_attempts', 'chaos_id')
    op.drop_column('mission_attempts', 'environment')
