"""unique mission per environment and level

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-29 17:36:18.147130

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = "uq_missions_environment_level"


def _has_constraint(name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"), {"name": name})
        .scalar()
    )


def upgrade() -> None:
    """미션 시드의 stable key 를 DB 제약으로 못 박는다.

    시드는 (environment, level) 로 upsert 하므로 같은 환경에 같은 레벨이 둘 이상이면
    시드와 잠금 계산이 모두 깨진다.
    """
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT environment, level, COUNT(*) AS n FROM missions "
                "GROUP BY environment, level HAVING COUNT(*) > 1"
            )
        )
        .fetchall()
    )
    if duplicates:
        detail = ", ".join(f"{row[0]}/level {row[1]} x{row[2]}" for row in duplicates)
        raise RuntimeError(
            "같은 환경에 중복된 레벨의 미션이 있어 제약을 추가할 수 없습니다: "
            f"{detail}. 중복 행을 정리한 뒤 다시 실행하세요."
        )

    if not _has_constraint(CONSTRAINT_NAME):
        op.create_unique_constraint(CONSTRAINT_NAME, "missions", ["environment", "level"])


def downgrade() -> None:
    if _has_constraint(CONSTRAINT_NAME):
        op.drop_constraint(CONSTRAINT_NAME, "missions", type_="unique")
