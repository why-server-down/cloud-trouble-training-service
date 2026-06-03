import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Mission, MissionAttempt, User
from app.core.metrics import MISSION_COMPLETIONS
from app.services.chaos_injector import BaseChaosInjector
from app.services.scoring_service import ScoringService
from app.services.validation_service import BaseValidationService


class MissionService:
    def __init__(
        self,
        chaos_injector: BaseChaosInjector,
        validation_service: BaseValidationService,
        scoring_service: ScoringService,
    ):
        self._chaos = chaos_injector
        self._validation = validation_service
        self._scoring = scoring_service
        self._active_chaos_ids: dict[uuid.UUID, str] = {}

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
        return result.scalar_one_or_none()

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

        # 장애 주입
        namespace = f"user-{user.id}"
        chaos_result = await self._chaos.inject(mission.chaos_type, namespace)
        if not chaos_result.success:
            raise RuntimeError(f"장애 주입 실패: {chaos_result.message}")

        # 시도 기록 생성
        attempt = MissionAttempt(user_id=user.id, mission_id=mission.id)
        db.add(attempt)
        await db.commit()
        await db.refresh(attempt)

        self._active_chaos_ids[attempt.id] = chaos_result.chaos_id
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
            await self._cleanup_chaos(attempt.id)
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
        validation = await self._validation.check_resolution(mission.chaos_type, namespace)

        if validation.is_resolved:
            now = datetime.now(timezone.utc)
            attempt.status = "completed"
            attempt.end_time = now
            attempt.final_score = self._scoring.calculate_score(
                mission.base_score, attempt.start_time, now,
                attempt.hints_used, mission.hint_penalty,
            )
            MISSION_COMPLETIONS.labels(str(mission.level)).inc()
            await self._cleanup_chaos(attempt.id)
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
        await self._cleanup_chaos(attempt.id)
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

    async def _cleanup_chaos(self, attempt_id: uuid.UUID):
        chaos_id = self._active_chaos_ids.pop(attempt_id, None)
        if chaos_id:
            await self._chaos.revert(chaos_id)
