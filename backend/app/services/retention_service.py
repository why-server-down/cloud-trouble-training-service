"""보존 기간이 지난 데이터를 지운다 (BE-29).

튜터 대화에는 사용자가 친 명령, 장애 상황, 힌트가 그대로 남는다. 훈련이 끝난 뒤에도
무기한 보관할 이유가 없다.

**진행 중인 attempt 의 대화는 기간이 지나도 지우지 않는다.** 훈련 도중 대화가
사라지면 튜터가 앞의 문맥을 잃는다.

별도 스케줄러를 두지 않는다. 서버 기동 시 BE-22 의 reconciliation 과 같은 자리에서
한 번 돌고, 오래 떠 있는 배포에서는 이 모듈을 주기 작업으로 실행한다.

    python -m app.services.retention_service
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import RETENTION_DELETIONS
from app.models import MissionAttempt, TutorMessage

logger = logging.getLogger(__name__)

# 배치 삭제가 끝나지 않는 상황(시계 오류, 무한 재삽입)에서 기동이 막히지 않게 한다.
_MAX_BATCHES = 100


async def purge_expired_tutor_messages(
    db: AsyncSession, *, now: datetime | None = None
) -> dict:
    """보존 기간이 지난 튜터 대화를 지운다.

    반복 실행해도 안전하다(지울 것이 없으면 아무것도 하지 않는다).
    예외를 밖으로 던지지 않는다 — 기동 경로와 요청 경로 어디에서 불러도
    정리 실패가 본래 작업을 막으면 안 된다.
    """
    days = settings.TUTOR_MESSAGE_RETENTION_DAYS
    if days <= 0:
        return {"deleted": 0, "skipped": "retention disabled"}

    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    batch = max(1, settings.RETENTION_DELETE_BATCH)
    deleted = 0

    try:
        for _ in range(_MAX_BATCHES):
            removed = await _delete_batch(db, cutoff, batch)
            deleted += removed
            if removed < batch:
                break
        else:
            logger.warning(
                "tutor message retention stopped at the batch limit",
                extra={"deleted": deleted, "batches": _MAX_BATCHES},
            )
    except Exception:
        await db.rollback()
        # 메시지 본문은 남기지 않는다. 남기면 지운 의미가 없다.
        logger.exception("tutor message retention failed", extra={"deleted": deleted})
        return {"deleted": deleted, "failed": True}

    if deleted:
        RETENTION_DELETIONS.labels("tutor_messages").inc(deleted)
        logger.info(
            "tutor messages purged",
            extra={"deleted": deleted, "retention_days": days},
        )
    return {"deleted": deleted, "retention_days": days}


async def _delete_batch(db: AsyncSession, cutoff: datetime, batch: int) -> int:
    """한 배치만 지운다. 한 트랜잭션이 테이블을 오래 잡지 않게 나눈다."""
    in_progress = select(MissionAttempt.id).where(MissionAttempt.status == "in_progress")
    doomed = (
        select(TutorMessage.id)
        .where(
            TutorMessage.created_at < cutoff,
            TutorMessage.attempt_id.notin_(in_progress),
        )
        .limit(batch)
    )
    result = await db.execute(
        delete(TutorMessage)
        .where(TutorMessage.id.in_(doomed))
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return result.rowcount or 0


async def _main() -> None:
    """주기 실행용 진입점. 배포에서는 CronJob 으로 부른다."""
    logging.basicConfig(level=logging.INFO)
    from app.core.database import async_session

    async with async_session() as db:
        summary = await purge_expired_tutor_messages(db)
    logger.info("retention run finished", extra=summary)


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
