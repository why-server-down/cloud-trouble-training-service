"""서버 시작 시 진행 중이던 상태를 실제와 대조해 정리한다.

왜 필요한가: 시간 초과 정리가 지금까지 **사용자가 status 를 조회할 때만** 일어났다.
사용자가 브라우저를 닫고 돌아오지 않으면 주입된 장애가 클러스터에 그대로 남는다.
서버가 재시작되면 그 사실조차 아무도 모른다.

BE-08 에서 chaos_id 를 DB 에 저장하도록 바꿨기 때문에, 이제 프로세스 메모리 없이도
정리할 수 있다.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import environments
from app.models import GeneratedScenario, Mission, MissionAttempt

logger = logging.getLogger(__name__)

# 미션/시나리오 정의를 찾지 못했을 때 쓰는 보수적인 상한.
_FALLBACK_TIME_LIMIT_SECONDS = 3600


async def reconcile_active_attempts(db: AsyncSession, injector_for=None) -> dict:
    """진행 중 attempt 를 훑어 시간 초과된 것을 정리한다.

    하나가 실패해도 나머지는 계속 처리한다. 기동 경로이므로 여기서 예외가 나가면
    서버가 뜨지 않는다.
    """
    if injector_for is None:
        from app.services.service_factory import create_chaos_injector

        injector_for = create_chaos_injector

    result = await db.execute(
        select(MissionAttempt)
        .options(selectinload(MissionAttempt.mission))
        .where(MissionAttempt.status == "in_progress")
    )
    attempts = list(result.scalars().all())

    summary = {"checked": len(attempts), "expired": 0, "cleaned": 0, "failed": 0}
    if not attempts:
        return summary

    now = datetime.now(timezone.utc)
    for attempt in attempts:
        try:
            limit = await _time_limit_for(db, attempt)
            elapsed = (now - _aware(attempt.start_time)).total_seconds()
            if elapsed < limit:
                continue

            summary["expired"] += 1
            attempt.status = "failed"
            attempt.end_time = now
            if await _cleanup_chaos(attempt, injector_for):
                summary["cleaned"] += 1
        except Exception:
            summary["failed"] += 1
            logger.exception(
                "attempt reconciliation failed", extra={"attempt_id": str(attempt.id)}
            )

    await db.commit()
    if summary["expired"]:
        logger.info("reconciled expired attempts", extra=summary)
    return summary


async def _cleanup_chaos(attempt: MissionAttempt, injector_for) -> bool:
    """DB 에 남은 chaos_id 로 되돌린다. 실패해도 attempt 는 종료 처리한다."""
    if not attempt.chaos_id:
        return False
    if not environments.is_implemented(attempt.environment):
        logger.warning(
            "skip cleanup for unimplemented environment",
            extra={"environment": attempt.environment},
        )
        return False

    try:
        injector = injector_for(attempt.environment)
        reverted = await injector.revert(attempt.chaos_id, f"user-{attempt.user_id}")
    except Exception:
        logger.exception(
            "chaos cleanup failed during reconciliation",
            extra={"chaos_id": attempt.chaos_id},
        )
        return False

    if reverted:
        # 되돌린 뒤 비워야 다음 정리에서 같은 작업을 반복하지 않는다.
        attempt.chaos_id = None
    return bool(reverted)


async def _time_limit_for(db: AsyncSession, attempt: MissionAttempt) -> int:
    if attempt.attempt_type == "ai_scenario" and attempt.scenario_id:
        result = await db.execute(
            select(GeneratedScenario.time_limit).where(
                GeneratedScenario.id == attempt.scenario_id
            )
        )
        return result.scalar_one_or_none() or _FALLBACK_TIME_LIMIT_SECONDS

    if attempt.mission is not None:
        return attempt.mission.time_limit

    if attempt.mission_id:
        result = await db.execute(
            select(Mission.time_limit).where(Mission.id == attempt.mission_id)
        )
        return result.scalar_one_or_none() or _FALLBACK_TIME_LIMIT_SECONDS

    return _FALLBACK_TIME_LIMIT_SECONDS


def _aware(value: datetime) -> datetime:
    """naive datetime 이 섞여도 비교가 깨지지 않게 한다."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
