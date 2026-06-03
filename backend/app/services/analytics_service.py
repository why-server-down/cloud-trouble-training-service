import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import MissionAttempt, User


TIER_DEFINITIONS = [
    {"name": "Bronze", "min_score": 0, "max_score": 200, "color": "#cd7f32"},
    {"name": "Silver", "min_score": 201, "max_score": 500, "color": "#c0c0c0"},
    {"name": "Gold", "min_score": 501, "max_score": 1000, "color": "#ffd700"},
    {"name": "Platinum", "min_score": 1001, "max_score": 2000, "color": "#e5e4e2"},
    {"name": "DevOps Master", "min_score": 2001, "max_score": None, "color": "#b9f2ff"},
]

SKILL_CATEGORIES = {
    "troubleshooting": {"pod_failure", "memory_stress"},
    "resource": {"memory_stress"},
    "network": {"service_misconfig", "network_latency"},
    "ops": {"pod_failure", "service_misconfig", "network_latency"},
}

ACHIEVEMENTS = [
    {
        "id": "first-recovery",
        "name": "First Recovery",
        "description": "Complete your first mission.",
        "points_bonus": 0,
        "is_hidden": False,
    },
    {
        "id": "environmentalist",
        "name": "Environmentalist",
        "description": "Complete a mission without using a hint.",
        "points_bonus": 50,
        "is_hidden": False,
    },
    {
        "id": "speed-runner",
        "name": "Speed Runner",
        "description": "Complete a mission within five minutes.",
        "points_bonus": 30,
        "is_hidden": False,
    },
    {
        "id": "persistent-resolver",
        "name": "Persistent Resolver",
        "description": "Complete a mission after ten or more attempts.",
        "points_bonus": 100,
        "is_hidden": True,
    },
]


def calculate_tier(total_score: int) -> dict:
    for index, tier in enumerate(TIER_DEFINITIONS):
        max_score = tier["max_score"]
        if max_score is None or total_score <= max_score:
            next_tier = TIER_DEFINITIONS[index + 1]["name"] if index + 1 < len(TIER_DEFINITIONS) else None
            if max_score is None:
                progress = 100.0
            else:
                span = max_score - tier["min_score"] + 1
                progress = min(100.0, max(0.0, ((total_score - tier["min_score"]) / span) * 100))
            return {**tier, "progress": round(progress, 1), "next_tier": next_tier}
    return TIER_DEFINITIONS[-1]


class AnalyticsService:
    async def _completed_attempts(self, db: AsyncSession, user_id: uuid.UUID) -> list[MissionAttempt]:
        result = await db.execute(
            select(MissionAttempt)
            .options(selectinload(MissionAttempt.mission))
            .where(
                MissionAttempt.user_id == user_id,
                MissionAttempt.status == "completed",
            )
            .order_by(MissionAttempt.end_time)
        )
        return list(result.scalars().all())

    async def get_dashboard_stats(self, db: AsyncSession, user: User) -> dict:
        completed = await self._completed_attempts(db, user.id)
        total_score = sum(attempt.final_score or 0 for attempt in completed)
        total_time = sum(self._completion_seconds(attempt) for attempt in completed)
        hints_used = sum(attempt.hints_used for attempt in completed)
        return {
            "username": user.username,
            "total_score": total_score,
            "missions_completed": len(completed),
            "total_time_spent": total_time,
            "hints_used": hints_used,
            "current_tier": calculate_tier(total_score),
            "skill_scores": self._calculate_skill_scores(completed),
        }

    async def get_learning_curve(self, db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
        completed = await self._completed_attempts(db, user_id)
        attempts_by_mission: dict[uuid.UUID, int] = defaultdict(int)
        curve = []
        for attempt in completed:
            attempts_by_mission[attempt.mission_id] += 1
            if attempt.attempt_type == "ai_scenario":
                name = f"AI 시나리오 ({attempt.scenario_id and str(attempt.scenario_id)[:8]})"
            else:
                name = attempt.mission.name if attempt.mission else "알 수 없음"
            curve.append(
                {
                    "attempt_id": str(attempt.id),
                    "mission_id": str(attempt.mission_id),
                    "mission_name": name,
                    "attempt_number": attempts_by_mission[attempt.mission_id],
                    "completion_time": self._completion_seconds(attempt),
                    "score": attempt.final_score or 0,
                    "hints_used": attempt.hints_used,
                    "completed_at": attempt.end_time,
                }
            )
        return curve

    async def get_leaderboard(self, db: AsyncSession, current_user_id: uuid.UUID, limit: int = 100) -> list[dict]:
        score = func.coalesce(func.sum(MissionAttempt.final_score), 0)
        completed = func.count(MissionAttempt.id)
        result = await db.execute(
            select(User.id, User.username, score.label("total_score"), completed.label("missions_completed"))
            .outerjoin(
                MissionAttempt,
                (MissionAttempt.user_id == User.id) & (MissionAttempt.status == "completed"),
            )
            .group_by(User.id)
            .order_by(score.desc(), completed.desc(), User.username)
            .limit(limit)
        )
        return [
            {
                "rank": rank,
                "user_id": str(row.id),
                "username": row.username,
                "total_score": int(row.total_score),
                "missions_completed": int(row.missions_completed),
                "is_current_user": row.id == current_user_id,
            }
            for rank, row in enumerate(result.all(), start=1)
        ]

    async def get_achievements(self, db: AsyncSession, user_id: uuid.UUID) -> dict:
        completed = await self._completed_attempts(db, user_id)
        attempt_counts_result = await db.execute(
            select(MissionAttempt.mission_id, func.count(MissionAttempt.id))
            .where(MissionAttempt.user_id == user_id)
            .group_by(MissionAttempt.mission_id)
        )
        attempt_counts = dict(attempt_counts_result.all())
        unlocked_ids = set()
        if completed:
            unlocked_ids.add("first-recovery")
        if any(attempt.hints_used == 0 for attempt in completed):
            unlocked_ids.add("environmentalist")
        if any(self._completion_seconds(attempt) <= 300 for attempt in completed):
            unlocked_ids.add("speed-runner")
        if any(attempt_counts.get(attempt.mission_id, 0) >= 10 for attempt in completed):
            unlocked_ids.add("persistent-resolver")

        items = [
            {
                **achievement,
                "unlocked": achievement["id"] in unlocked_ids,
                "name": achievement["name"] if achievement["id"] in unlocked_ids or not achievement["is_hidden"] else "Hidden achievement",
                "description": achievement["description"] if achievement["id"] in unlocked_ids or not achievement["is_hidden"] else "Keep investigating to reveal this achievement.",
            }
            for achievement in ACHIEVEMENTS
        ]
        return {
            "unlocked": len(unlocked_ids),
            "total": len(items),
            "progress": round((len(unlocked_ids) / len(items)) * 100, 1),
            "items": items,
        }

    @staticmethod
    def _completion_seconds(attempt: MissionAttempt) -> int:
        if not attempt.end_time:
            return 0
        return max(0, int((attempt.end_time - attempt.start_time).total_seconds()))

    def _calculate_skill_scores(self, completed: list[MissionAttempt]) -> dict[str, float]:
        scores = {}
        for skill, chaos_types in SKILL_CATEGORIES.items():
            relevant = [attempt.final_score or 0 for attempt in completed if attempt.mission and attempt.mission.chaos_type in chaos_types]
            confidence = min(len(relevant) / 3, 1.0)
            scores[skill] = round((sum(relevant) / len(relevant)) * confidence, 1) if relevant else 0.0
        return scores


analytics_service = AnalyticsService()
