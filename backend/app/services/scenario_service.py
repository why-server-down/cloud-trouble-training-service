"""
ScenarioService - AI 시나리오 생성/시작/완료 오케스트레이터.
기존 MissionService와 분리: /api/scenarios/* 전용.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GeneratedScenario, Mission, MissionAttempt, User
from app.ai.scenario_agent import ScenarioGenerationInput, get_scenario_agent
from app.services.chaos_injector import BaseChaosInjector
from app.services.chaos_plan import ChaosPlanCompiler, FAULT_TYPE_TO_CHAOS_TYPE
from app.services.scoring_service import ScoringService
from app.services.validation_rule_service import ValidationRuleService
from app.core.config import settings
from app.core.environments import DEFAULT_ENVIRONMENT

ALLOWED_FAULT_TYPES = [
    "image_pull_error",
    "pod_failure",
    "crash_loop",
    "oom_killed",
    "memory_stress",
    "service_selector_mismatch",
    "service_misconfig",
    "network_latency",
    "probe_failure",
    "configmap_misconfig",
    "liveness_probe_failure",
    "init_container_failure",
    "node_selector_mismatch",
    "compound_probe_cascade",
    "compound_crash_service",
    "wrong_image_registry",
    "secret_ref_missing",
    "pvc_unbound",
    "cpu_throttle",
]


class ScenarioService:

    def __init__(
        self,
        chaos_injector: BaseChaosInjector,
        scoring_service: ScoringService,
        validation_rule_service: ValidationRuleService,
    ):
        self._chaos = chaos_injector
        self._scoring = scoring_service
        self._vrs = validation_rule_service
        self._compiler = ChaosPlanCompiler()
        self._active_chaos_ids: dict[uuid.UUID, str] = {}  # attempt_id -> chaos_id

    async def check_unlock_status(self, db: AsyncSession, user_id: uuid.UUID) -> dict:
        """AI 모드 잠금 해제 상태 반환."""
        result = await db.execute(select(Mission).order_by(Mission.level))
        missions = result.scalars().all()
        total = len(missions)

        if total == 0:
            return {"unlocked": settings.DEMO_UNLOCK_AI_SCENARIOS, "completed_static": 0, "total_static": 0}

        completed_result = await db.execute(
            select(Mission.id)
            .join(MissionAttempt, MissionAttempt.mission_id == Mission.id)
            .where(
                and_(
                    MissionAttempt.user_id == user_id,
                    MissionAttempt.status == "completed",
                    MissionAttempt.attempt_type == "static_mission",
                )
            )
        )
        completed_ids = set(completed_result.scalars().all())
        completed_count = sum(1 for m in missions if m.id in completed_ids)
        unlocked = settings.DEMO_UNLOCK_AI_SCENARIOS or completed_count >= total

        return {"unlocked": unlocked, "completed_static": completed_count, "total_static": total}

    async def _assert_unlocked(self, db: AsyncSession, user_id: uuid.UUID, allow_demo_unlock: bool = False):
        status = await self.check_unlock_status(db, user_id)
        if not status["unlocked"] and not allow_demo_unlock:
            raise ValueError(
                f"기본 미션을 모두 완료해야 AI 문제 더 풀기를 이용할 수 있습니다 "
                f"({status['completed_static']}/{status['total_static']} 완료)"
            )

    async def _get_active_attempt(self, db: AsyncSession, user_id: uuid.UUID) -> MissionAttempt | None:
        result = await db.execute(
            select(MissionAttempt).where(
                and_(MissionAttempt.user_id == user_id, MissionAttempt.status == "in_progress")
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
                await self._chaos.revert(scenario.chaos_id)
                scenario.chaos_id = None

        await db.commit()
        await db.refresh(attempt)
        return True

    async def _get_recent_fault_types(self, db: AsyncSession, user_id: uuid.UUID, limit: int = 5) -> list[str]:
        result = await db.execute(
            select(GeneratedScenario.fault_type)
            .join(MissionAttempt, MissionAttempt.scenario_id == GeneratedScenario.id)
            .where(
                and_(
                    MissionAttempt.user_id == user_id,
                    MissionAttempt.status.in_(["completed", "abandoned"]),
                    MissionAttempt.attempt_type == "ai_scenario",
                )
            )
            .order_by(MissionAttempt.start_time.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def start_random(
        self,
        db: AsyncSession,
        user: User,
        difficulty: str,
        environment: str = DEFAULT_ENVIRONMENT,
        allow_demo_unlock: bool = False,
    ) -> dict:
        """난이도 선택 → AI 시나리오 생성 + 장애 주입 + attempt 생성 원스텝."""
        await self._assert_unlocked(db, user.id, allow_demo_unlock=allow_demo_unlock)

        active = await self._get_active_attempt(db, user.id)
        if active:
            raise ValueError("이미 진행 중인 미션이 있습니다. 완료하거나 포기한 후 다시 시작하세요")

        # 생성 컨텍스트
        recent_faults = await self._get_recent_fault_types(db, user.id)
        namespace = f"user-{user.id}"

        gen_input = ScenarioGenerationInput(
            difficulty=difficulty,
            namespace=namespace,
            recent_fault_types=recent_faults,
            allowed_fault_types=ALLOWED_FAULT_TYPES,
        )

        # AI 시나리오 생성
        agent = get_scenario_agent()
        candidates = agent.generate(gen_input)
        valid = [c for c in candidates if not c.rejected]
        if not valid:
            raise RuntimeError("시나리오 생성에 실패했습니다. 잠시 후 다시 시도해 주세요")

        best = max(valid, key=lambda c: c.score)
        scenario_json = best.scenario

        # ChaosPlan 컴파일
        try:
            plan = self._compiler.compile(scenario_json, namespace)
        except Exception as e:
            raise RuntimeError(f"장애 계획 컴파일 실패: {e}")

        # GeneratedScenario 저장
        scoring = scenario_json.get("scoring", {})
        scenario = GeneratedScenario(
            user_id=user.id,
            difficulty=difficulty,
            environment=environment,
            title=scenario_json.get("title", "AI 생성 시나리오"),
            student_brief=scenario_json.get("student_brief", ""),
            internal_summary=scenario_json.get("internal_summary", ""),
            fault_type=scenario_json.get("fault", {}).get("type", "unknown"),
            scenario_json=scenario_json,
            chaos_plan_json=plan.to_dict(),
            validation_json=scenario_json.get("validation"),
            status="generated",
            base_score=scoring.get("base_score", 100),
            time_limit=scoring.get("time_limit_seconds", 1200),
            hint_penalty=scoring.get("hint_penalty", 7),
        )
        db.add(scenario)
        await db.flush()  # scenario.id 확보

        # ValidationRule 저장
        validation_json = scenario_json.get("validation", {"rules": []})
        await self._vrs.guard_and_store(
            scenario_id=scenario.id,
            validation_json=validation_json,
            namespace=namespace,
            db=db,
        )

        # 장애 주입 (fault_type → chaos_type 매핑 후 기존 inject() 사용)
        chaos_type = FAULT_TYPE_TO_CHAOS_TYPE.get(plan.fault_type, "pod_failure")
        chaos_result = await self._chaos.inject(chaos_type, namespace)
        if not chaos_result.success:
            raise RuntimeError(f"장애 주입 실패: {chaos_result.message}")

        scenario.status = "running"
        scenario.chaos_id = chaos_result.chaos_id

        # MissionAttempt 생성
        attempt = MissionAttempt(
            user_id=user.id,
            attempt_type="ai_scenario",
            scenario_id=scenario.id,
        )
        db.add(attempt)
        await db.commit()
        await db.refresh(attempt)
        await db.refresh(scenario)

        self._active_chaos_ids[attempt.id] = chaos_result.chaos_id

        return {"scenario": scenario, "attempt": attempt}

    async def get_status(self, db: AsyncSession, user_id: uuid.UUID) -> dict:
        """진행 중인 AI 시나리오 상태 조회."""
        attempt = await self._get_active_attempt(db, user_id)
        if not attempt or attempt.attempt_type != "ai_scenario":
            raise ValueError("진행 중인 AI 시나리오가 없습니다")

        result = await db.execute(
            select(GeneratedScenario).where(GeneratedScenario.id == attempt.scenario_id)
        )
        scenario = result.scalar_one_or_none()
        if not scenario:
            raise ValueError("시나리오를 찾을 수 없습니다")

        now = datetime.now(timezone.utc)
        elapsed = int((now - attempt.start_time).total_seconds())
        remaining = max(0, scenario.time_limit - elapsed)
        current_score = self._scoring.calculate_current_score(
            scenario.base_score, attempt.start_time, attempt.hints_used, scenario.hint_penalty
        )

        if remaining == 0 and attempt.status == "in_progress":
            attempt.status = "failed"
            attempt.end_time = now
            attempt.final_score = self._scoring.MIN_SCORE
            scenario.status = "failed"
            await self._cleanup_chaos(attempt.id)
            await db.commit()

        return {
            "attempt": attempt,
            "scenario": scenario,
            "elapsed_seconds": elapsed,
            "remaining_seconds": remaining,
            "current_score": current_score,
        }

    async def check_and_complete(self, db: AsyncSession, user_id: uuid.UUID) -> dict:
        """AI 시나리오 완료 검증."""
        attempt = await self._get_active_attempt(db, user_id)
        if not attempt or attempt.attempt_type != "ai_scenario":
            raise ValueError("진행 중인 AI 시나리오가 없습니다")

        result = await db.execute(
            select(GeneratedScenario).where(GeneratedScenario.id == attempt.scenario_id)
        )
        scenario = result.scalar_one_or_none()
        if not scenario:
            raise ValueError("시나리오를 찾을 수 없습니다")

        namespace = f"user-{user_id}"
        resolved, rule_results = await self._vrs.check_rules(
            scenario_id=scenario.id,
            namespace=namespace,
            db=db,
            use_mock=(settings.VALIDATION_BACKEND == "mock"),
        )

        # mock 룰만 있거나 accepted 룰이 없으면 K8s 직접 검증 fallback
        # (실제 K8s 상태도 False면 fallback도 False → 안전)
        if not resolved and settings.VALIDATION_BACKEND != "mock":
            resolved = await self._vrs.k8s_check_by_fault_type(
                fault_type=scenario.fault_type,
                namespace=namespace,
            )

        # AI 판정: mechanical check 후에도 미해결 시 LLM이 K8s 상태 전체를 보고 재판정
        ai_judgment = None
        if not resolved and settings.VALIDATION_BACKEND != "mock" and settings.AI_BACKEND in ("openai", "gemini"):
            from app.ai.validation_agent import get_validation_agent
            agent = get_validation_agent()
            ai_judgment = await agent.judge(
                scenario_context={
                    "title": scenario.title,
                    "fault_type": scenario.fault_type,
                    "student_brief": scenario.student_brief,
                    "internal_summary": scenario.internal_summary,
                    "namespace": namespace,
                },
                namespace=namespace,
            )
            if ai_judgment.confidence >= 0.7:
                resolved = ai_judgment.resolved

        attempt.last_validation_result = {
            "resolved": resolved,
            "rules": [{"name": r.name, "passed": r.passed, "error": r.error} for r in rule_results],
            "ai_judgment": {
                "resolved": ai_judgment.resolved,
                "reason": ai_judgment.reason,
                "confidence": ai_judgment.confidence,
            } if ai_judgment else None,
        }

        if resolved:
            now = datetime.now(timezone.utc)
            attempt.status = "completed"
            attempt.end_time = now
            attempt.final_score = self._scoring.calculate_score(
                scenario.base_score, attempt.start_time, now,
                attempt.hints_used, scenario.hint_penalty,
            )
            scenario.status = "completed"
            await self._cleanup_chaos(attempt.id)
            await db.commit()
            await db.refresh(attempt)
            return {
                "resolved": True,
                "message": f"시나리오를 완료했습니다! 최종 점수: {attempt.final_score}점",
                "score": attempt.final_score,
            }

        await db.commit()
        return {
            "resolved": False,
            "message": "아직 정상화 조건을 만족하지 못했습니다. 서비스 상태와 Pod 상태를 다시 확인해 주세요.",
            "score": None,
        }

    async def abandon(self, db: AsyncSession, user_id: uuid.UUID) -> dict:
        """AI 시나리오 포기."""
        attempt = await self._get_active_attempt(db, user_id)
        if not attempt or attempt.attempt_type != "ai_scenario":
            raise ValueError("진행 중인 AI 시나리오가 없습니다")

        result = await db.execute(
            select(GeneratedScenario).where(GeneratedScenario.id == attempt.scenario_id)
        )
        scenario = result.scalar_one_or_none()

        attempt.status = "abandoned"
        attempt.end_time = datetime.now(timezone.utc)
        attempt.final_score = 0
        if scenario:
            scenario.status = "failed"

        await self._cleanup_chaos(attempt.id)
        await db.commit()
        return {"message": "AI 시나리오를 포기했습니다"}

    async def use_hint(self, db: AsyncSession, user_id: uuid.UUID) -> MissionAttempt:
        """AI 시나리오 힌트 사용."""
        attempt = await self._get_active_attempt(db, user_id)
        if not attempt or attempt.attempt_type != "ai_scenario":
            raise ValueError("진행 중인 AI 시나리오가 없습니다")

        attempt.hints_used += 1
        await db.commit()
        await db.refresh(attempt)
        return attempt

    async def debug_resolve(self, db: AsyncSession, user_id: uuid.UUID) -> dict:
        """Mock 전용: 수동 해결 트리거."""
        attempt = await self._get_active_attempt(db, user_id)
        if not attempt or attempt.attempt_type != "ai_scenario":
            raise ValueError("진행 중인 AI 시나리오가 없습니다")

        namespace = f"user-{user_id}"
        self._vrs.mark_resolved(attempt.scenario_id, namespace)
        return {"message": "[Mock] AI 시나리오 해결 상태로 설정했습니다. /api/scenarios/current/check로 확인하세요"}

    async def _cleanup_chaos(self, attempt_id: uuid.UUID):
        chaos_id = self._active_chaos_ids.pop(attempt_id, None)
        if chaos_id:
            await self._chaos.revert(chaos_id)
