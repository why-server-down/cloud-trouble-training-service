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
from app.services.chaos_plan import FAULT_TYPE_TO_CHAOS_TYPE
from app.services.service_factory import get_mission_service

router = APIRouter(prefix="/api/chat", tags=["chat"])

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
    """AI 튜터에게 질문 (소크라테스식 힌트).

    정적 미션과 AI 시나리오 attempt 모두 지원.
    - hint_level 0: 방향만 제시
    - hint_level 1: 확인할 리소스 지목
    - hint_level 2: 정확한 kubectl 명령어 제공
    - hint_level 3: 전체 해결 방법 제공
    """
    retry_after = _rate_limiter.check(str(current_user.id))
    if retry_after is not None:
        # 언제 다시 시도할 수 있는지 함께 알린다. 프론트가 화면에 표시할 수 있어야 한다.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"요청이 너무 잦습니다. {retry_after}초 후 다시 시도해 주세요.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
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
    # 힌트 단계는 서버가 강제한다. 프론트가 /hint 로 올린 attempt.hints_used 를 넘는
    # 단계를 요청해도(DevTools 로 hint_level=3) 감점 없이 정답을 받지 못하게 한다.
    hint_level = min(body.hint_level, attempt.hints_used)
    tutor_result = await tutor.get_hint(
        user_question=body.message,
        attempt_id=attempt.id,
        hint_level=hint_level,
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
            hint_level=hint_level,
            environment=attempt.environment,
        )

    return ChatResponse(
        response=tutor_result.message,
        hint_level=hint_level,
        # 튜터가 실제로 어느 환경을 보고 답했는지 그대로 전달한다.
        environment=tutor_result.environment,
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
    # 튜터에는 실제로 주입된 장애를 넘긴다. 주입 계획과 같은 표를 쓴다 — 예전에는 이 파일에 따로 둔
    # 표가 probe_failure·crash_loop 를 pod_failure(이미지 문제)로, cpu_throttle 을 network_latency 로
    # 묶어 튜터가 다른 장애를 기준으로 답했다. 표에 없는 이름(docker_*·linux_*)은 주입기 이름 그대로다.
    chaos_type = FAULT_TYPE_TO_CHAOS_TYPE.get(scenario.fault_type, scenario.fault_type)
    return scenario.title, difficulty_level, chaos_type
