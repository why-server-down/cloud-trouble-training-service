from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimiter
from app.models import GeneratedScenario, Mission, MissionAttempt, User
from app.schemas import ChatRequest, ChatResponse, TutorResult
from app.ai.tutor_service import get_tutor_service
from app.services.service_factory import get_mission_service

router = APIRouter(prefix="/api/chat", tags=["chat"])

# AI fault_type → 튜터 mock 응답에 사용할 chaos_type 매핑
_FAULT_TO_CHAOS: dict[str, str] = {
    "image_pull_error":          "pod_failure",
    "pod_failure":               "pod_failure",
    "crash_loop":                "pod_failure",
    "probe_failure":             "pod_failure",
    "configmap_misconfig":       "pod_failure",
    "liveness_probe_failure":    "pod_failure",
    "init_container_failure":    "pod_failure",
    "node_selector_mismatch":    "pod_failure",
    "wrong_image_registry":      "pod_failure",
    "secret_ref_missing":        "pod_failure",
    "pvc_unbound":               "pod_failure",
    "oom_killed":                "memory_stress",
    "memory_stress":             "memory_stress",
    "service_selector_mismatch": "service_misconfig",
    "service_misconfig":         "service_misconfig",
    "compound_crash_service":    "service_misconfig",
    "network_latency":           "network_latency",
    "compound_probe_cascade":    "network_latency",
    "cpu_throttle":              "network_latency",
}


# 사용자당 호출 빈도 제한. chat 은 호출마다 LLM 비용이 나가므로,
# 제한이 없으면 한 사용자가 반복 요청만으로 전체 예산을 소진할 수 있다.
_rate_limiter = RateLimiter(settings.CHAT_RATE_LIMIT_PER_MINUTE)


@router.post("/", response_model=ChatResponse)
async def chat_with_tutor(
    body: ChatRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    retry_after = _rate_limiter.check(str(current_user.id))
    if retry_after is not None:
        # 언제 다시 시도할 수 있는지 함께 알린다. 프론트가 화면에 표시할 수 있어야 한다.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"요청이 너무 잦습니다. {retry_after}초 후 다시 시도해 주세요.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    """
    AI 튜터에게 질문 (소크라테스식 힌트).
    정적 미션과 AI 시나리오 attempt 모두 지원.
    - hint_level 0: 방향만 제시
    - hint_level 1: 확인할 리소스 지목
    - hint_level 2: 정확한 kubectl 명령어 제공
    - hint_level 3: 전체 해결 방법 제공
    """
    mission_service = get_mission_service()
    attempt = await mission_service.get_active_attempt(db, current_user.id)

    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="진행 중인 미션이 없습니다. 미션을 시작한 후 질문해주세요.",
        )

    namespace = f"user-{current_user.id}"
    tutor = get_tutor_service()

    # attempt 타입에 따라 미션 정보 조회 방식 분기
    if attempt.attempt_type == "ai_scenario":
        mission_name, mission_level, chaos_type = await _get_scenario_info(db, attempt)
    else:
        mission_name, mission_level, chaos_type = await _get_mission_info(db, attempt)

    scenario_id = attempt.scenario_id if attempt.attempt_type == "ai_scenario" else None
    tutor_result = await tutor.get_hint(
        user_question=body.message,
        attempt_id=attempt.id,
        hint_level=body.hint_level,
        mission_name=mission_name,
        mission_level=mission_level,
        chaos_type=chaos_type,
        namespace=namespace,
        db=db,
        scenario_id=scenario_id,
    )

    # AI-11 이전 adapter나 테스트 double의 문자열 반환도 한동안 호환한다.
    if isinstance(tutor_result, str):
        tutor_result = TutorResult(
            message=tutor_result,
            hint_level=body.hint_level,
            environment=attempt.environment,
        )

    return ChatResponse(
        response=tutor_result.message,
        hint_level=body.hint_level,
        mission_name=mission_name,
        sources=[source.model_dump(exclude_none=True) for source in tutor_result.sources],
        observations_used=tutor_result.observations_used,
        token_usage=tutor_result.token_usage,
        fallback_used=tutor_result.fallback_used,
    )


async def _get_mission_info(db, attempt: MissionAttempt) -> tuple[str, int, str]:
    """정적 미션 attempt → (name, level, chaos_type)."""
    result = await db.execute(select(Mission).where(Mission.id == attempt.mission_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="미션을 찾을 수 없습니다")
    return mission.name, mission.level, mission.chaos_type


async def _get_scenario_info(db, attempt: MissionAttempt) -> tuple[str, int, str]:
    """AI 시나리오 attempt → (title, difficulty_level, chaos_type)."""
    result = await db.execute(
        select(GeneratedScenario).where(GeneratedScenario.id == attempt.scenario_id)
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="시나리오를 찾을 수 없습니다")

    # difficulty → 튜터 레벨 매핑
    difficulty_level = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}.get(
        scenario.difficulty, 2
    )
    chaos_type = _FAULT_TO_CHAOS.get(scenario.fault_type, "pod_failure")
    return scenario.title, difficulty_level, chaos_type
