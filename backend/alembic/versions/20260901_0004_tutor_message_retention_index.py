"""tutor message retention index

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "ix_tutor_messages_created_at"


def _has_index(name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_class WHERE relname = :name"), {"name": name})
        .scalar()
    )


def upgrade() -> None:
    """보존 정책(BE-29)이 훑는 컬럼에 인덱스를 만든다.

    정리 작업은 `created_at < cutoff` 로 지울 행을 고른다. 인덱스가 없으면
    대화가 쌓일수록 매번 전체 스캔이 되고, 기동 시 정리가 그만큼 느려진다.

    이미 있으면 만들지 않는다. `AUTO_CREATE_SCHEMA=true` 로 create_all 이 먼저
    만든 DB 에서도 이 리비전이 그대로 적용돼야 한다.
    """
    if not _has_index(INDEX_NAME):
        op.create_index(INDEX_NAME, "tutor_messages", ["created_at"])


def downgrade() -> None:
    if _has_index(INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="tutor_messages")
