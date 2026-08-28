import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GeneratedScenario, Mission, MissionAttempt, User
from app.core.metrics import MISSION_COMPLETIONS
from app.services.chaos_injector import BaseChaosInjector
from app.services.scoring_service import ScoringService
from app.services.validation_service import BaseValidationService


def namespace_for(user_id: uuid.UUID) -> str:
    return f"user-{user_id}"


class MissionService:
    """미션 오케스트레이터.

    환경별 인스턴스를 따로 두지 않는다. 서비스는 상태를 갖지 않고, attempt 의
    environment 로 그때그때 injector/validator 를 조회한다.
    """

    def __init__(
        self,
        *,
        injector_for: Callable[[str], BaseChaosInjector],
        validation_for: Callable[[str], BaseValidationService],
        scoring_service: ScoringService,
    ):
        self._injector_for = injector_for
        self._validation_for = validation_for
        self._scoring = scoring_service

    async def list_missions(self, db: AsyncSession, user: User) -> list[dict]:
        result = await db.execute(select(Mission).order_by(Mission.level))
        missions = result.scalars().all()

        # 유저가 완료한 미션의 레벨 목록
        completed_result = await db.execute(
            select(Mission.level).join(MissionAttempt).where(
                and_(
                    MissionAttempt.user_id == user.id,
                    MissionAttempt.status == "completed",
                )
            )
        )
        completed_levels = set(completed_result.scalars().all())

        mission_list = []
        for m in missions:
            is_unlocked = m.level == 1 or (m.level - 1) in completed_levels
            mission_list.append({"mission": m, "is_unlocked": is_unlocked})
        return mission_list

    async def get_active_attempt(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> MissionAttempt | None:
        result = await db.execute(
            select(MissionAttempt).where(
                and_(
                    MissionAttempt.user_id == user_id,
                    MissionAttempt.status == "in_progress",
                )
            )
        )
        attempt = result.scalar_one_or_none()
        if not attempt:
            return None

        if await self._expire_attempt_if_timed_out(db, attempt):
            return None

        return attempt

    async def _expire_attempt_if_timed_out(
        self, db: AsyncSession, attempt: MissionAttempt
    ) -> bool:
        if attempt.status != "in_progress":
            return False

        now = datetime.now(timezone.utc)
        time_limit: int | None = None
        scenario: GeneratedScenario | None = None

        if attempt.attempt_type == "ai_scenario":
            if not attempt.scenario_id:
                return False
            result = await db.execute(
                select(GeneratedScenario).where(GeneratedScenario.id == attempt.scenario_id)
            )
            scenario = result.scalar_one_or_none()
            time_limit = scenario.time_limit if scenario else None
        else:
            if not attempt.mission_id:
                return False
            result = await db.execute(select(Mission).where(Mission.id == attempt.mission_id))
            mission = result.scalar_one_or_none()
            time_limit = mission.time_limit if mission else None

        if time_limit is None:
            return False

        elapsed = int((now - attempt.start_time).total_seconds())
        if elapsed < time_limit:
            return False

        attempt.status = "failed"
        attempt.end_time = now
        attempt.final_score = self._scoring.MIN_SCORE
        if scenario:
            scenario.status = "failed"
            if scenario.chaos_id:
                injector = self._injector_for(scenario.environment)
                await injector.revert(scenario.chaos_id, namespace_for(attempt.user_id))
                scenario.chaos_id = None
        else:
            await self._cleanup_chaos(attempt)

        await db.commit()
        await db.refresh(attempt)
        return True

    async def start_mission(
        self, db: AsyncSession, user: User, mission_id: uuid.UUID
    ) -> MissionAttempt:
        # 이미 진행 중인 미션 체크
        active = await self.get_active_attempt(db, user.id)
        if active:
            raise ValueError("이미 진행 중인 미션이 있습니다")

        # 미션 조회
        result = await db.execute(select(Mission).where(Mission.id == mission_id))
        mission = result.scalar_one_or_none()
        if not mission:
            raise ValueError("미션을 찾을 수 없습니다")

        # 순차 잠금 해제 체크
        if mission.level > 1:
            prev_completed = await db.execute(
                select(MissionAttempt.id)
                .join(Mission)
                .where(
                    and_(
                        MissionAttempt.user_id == user.id,
                        MissionAttempt.status == "completed",
                        Mission.level == mission.level - 1,
                    )
                )
                .limit(1)
            )
            if not prev_completed.scalar_one_or_none():
                raise ValueError("이전 레벨을 먼저 완료해야 합니다")

        # 미션이 속한 환경의 주입기를 고른다. 미구현 환경이면 여기서 실패한다.
        injector = self._injector_for(mission.environment)

        namespace = namespace_for(user.id)
        chaos_result = await injector.inject(mission.chaos_type, namespace)
        if not chaos_result.success:
            raise RuntimeError(f"장애 주입 실패: {chaos_result.message}")

        # chaos_id 를 DB 에 저장한다. 프로세스 메모리에만 두면 서버가 재시작됐을 때
        # 주입된 장애를 되돌릴 방법이 없다.
        attempt = MissionAttempt(
            user_id=user.id,
            mission_id=mission.id,
            environment=mission.environment,
            chaos_id=chaos_result.chaos_id,
        )
        db.add(attempt)
        try:
            await db.commit()
            await db.refresh(attempt)
        except Exception:
            # 기록에 실패하면 주입된 장애가 고아가 되므로 즉시 되돌린다.
            await db.rollback()
            await injector.revert(chaos_result.chaos_id, namespace)
            raise
        return attempt

    async def get_status(self, db: AsyncSession, attempt_id: uuid.UUID) -> dict:
        result = await db.execute(
            select(MissionAttempt).where(MissionAttempt.id == attempt_id)
        )
        attempt = result.scalar_one_or_none()
        if not attempt:
            raise ValueError("시도 기록을 찾을 수 없습니다")

        mission_result = await db.execute(
            select(Mission).where(Mission.id == attempt.mission_id)
        )
        mission = mission_result.scalar_one_or_none()
        if not mission:
            raise ValueError("미션 정보를 찾을 수 없습니다 (AI 시나리오 attempt는 /api/scenarios/status를 사용하세요)")

        now = datetime.now(timezone.utc)
        elapsed = int((now - attempt.start_time).total_seconds())
        remaining = max(0, mission.time_limit - elapsed)

        current_score = self._scoring.calculate_current_score(
            mission.base_score, attempt.start_time, attempt.hints_used, mission.hint_penalty
        )

        # 시간 초과 시 자동 실패
        if remaining == 0 and attempt.status == "in_progress":
            attempt.status = "failed"
            attempt.end_time = now
            attempt.final_score = self._scoring.MIN_SCORE
            await self._cleanup_chaos(attempt)
            await db.commit()
            await db.refresh(attempt)

        return {
            "attempt": attempt,
            "elapsed_seconds": elapsed,
            "remaining_seconds": remaining,
            "current_score": current_score,
        }

    async def check_and_complete(self, db: AsyncSession, attempt_id: uuid.UUID) -> dict:
        result = await db.execute(
            select(MissionAttempt).where(MissionAttempt.id == attempt_id)
        )
        attempt = result.scalar_one_or_none()
        if not attempt or attempt.status != "in_progress":
            raise ValueError("진행 중인 시도가 없습니다")

        mission_result = await db.execute(
            select(Mission).where(Mission.id == attempt.mission_id)
        )
        mission = mission_result.scalar_one_or_none()

        namespace = f"user-{attempt.user_id}"
        validation = await self._validation_for(attempt.environment).check_resolution(mission.chaos_type, namespace)

        if validation.is_resolved:
            now = datetime.now(timezone.utc)
            attempt.status = "completed"
            attempt.end_time = now
            attempt.final_score = self._scoring.calculate_score(
                mission.base_score, attempt.start_time, now,
                attempt.hints_used, mission.hint_penalty,
            )
            MISSION_COMPLETIONS.labels(str(mission.level)).inc()
            await self._cleanup_chaos(attempt)
            await db.commit()
            await db.refresh(attempt)
            return {"attempt": attempt, "message": f"미션 완료! 점수: {attempt.final_score}점"}

        return {"attempt": attempt, "message": validation.message}

    async def abandon_mission(self, db: AsyncSession, user_id: uuid.UUID) -> MissionAttempt:
        attempt = await self.get_active_attempt(db, user_id)
        if not attempt:
            raise ValueError("진행 중인 미션이 없습니다")

        attempt.status = "abandoned"
        attempt.end_time = datetime.now(timezone.utc)
        attempt.final_score = 0
        await self._cleanup_chaos(attempt)
        await db.commit()
        await db.refresh(attempt)
        return attempt

    async def use_hint(self, db: AsyncSession, attempt_id: uuid.UUID) -> MissionAttempt:
        result = await db.execute(
            select(MissionAttempt).where(MissionAttempt.id == attempt_id)
        )
        attempt = result.scalar_one_or_none()
        if not attempt or attempt.status != "in_progress":
            raise ValueError("진행 중인 시도가 없습니다")

        attempt.hints_used += 1
        await db.commit()
        await db.refresh(attempt)
        return attempt

    async def _cleanup_chaos(self, attempt: MissionAttempt) -> None:
        """DB 에 저장된 chaos_id 로 되돌린다.

        서버가 재시작돼 프로세스 메모리가 비어 있어도 동작해야 한다.
        """
        if not attempt.chaos_id:
            return
        injector = self._injector_for(attempt.environment)
        await injector.revert(attempt.chaos_id, namespace_for(attempt.user_id))
        attempt.chaos_id = None
