from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import (
    MissionAttemptResponse,
    ScenarioCheckResponse,
    ScenarioGenerateRequest,
    ScenarioResponse,
    ScenarioStatusResponse,
    UnlockStatusResponse,
)
from app.services.service_factory import get_scenario_service

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


@router.post("/start-random", response_model=ScenarioResponse)
async def start_random_scenario(
    body: ScenarioGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """난이도 선택 → AI 시나리오 생성 + 장애 주입 원스텝."""
    if body.difficulty not in ("beginner", "intermediate", "advanced", "expert"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효하지 않은 난이도입니다. beginner / intermediate / advanced / expert 중 선택하세요",
        )

    service = get_scenario_service()
    try:
        result = await service.start_random(
            db,
            current_user,
            body.difficulty,
            allow_demo_unlock=body.demo_unlock,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    scenario = result["scenario"]
    return ScenarioResponse(
        scenario_id=scenario.id,
        title=scenario.title,
        difficulty=scenario.difficulty,
        student_brief=scenario.student_brief,
        time_limit_seconds=scenario.time_limit,
        base_score=scenario.base_score,
        hint_penalty=scenario.hint_penalty,
        safety_status="accepted",
    )


@router.get("/status", response_model=ScenarioStatusResponse)
async def get_scenario_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 진행 중인 AI 시나리오 상태 조회."""
    service = get_scenario_service()
    try:
        result = await service.get_status(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    attempt = result["attempt"]
    scenario = result["scenario"]
    return ScenarioStatusResponse(
        scenario_id=scenario.id,
        attempt_id=attempt.id,
        title=scenario.title,
        difficulty=scenario.difficulty,
        student_brief=scenario.student_brief,
        elapsed_seconds=result["elapsed_seconds"],
        remaining_seconds=result["remaining_seconds"],
        current_score=result["current_score"],
        hints_used=attempt.hints_used,
        status=attempt.status,
    )


@router.post("/current/check", response_model=ScenarioCheckResponse)
async def check_scenario(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """진행 중인 AI 시나리오 완료 검증."""
    service = get_scenario_service()
    try:
        result = await service.check_and_complete(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return ScenarioCheckResponse(**result)


@router.post("/current/abandon")
async def abandon_scenario(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """진행 중인 AI 시나리오 포기."""
    service = get_scenario_service()
    try:
        return await service.abandon(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/current/hint", response_model=MissionAttemptResponse)
async def use_hint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI 시나리오 힌트 사용 (점수 감점)."""
    service = get_scenario_service()
    try:
        attempt = await service.use_hint(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return attempt


@router.post("/debug/resolve")
async def debug_resolve(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mock 전용: AI 시나리오 수동 해결 트리거."""
    service = get_scenario_service()
    try:
        return await service.debug_resolve(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/unlock-status", response_model=UnlockStatusResponse)
async def get_unlock_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI 문제 더 풀기 잠금 해제 상태 조회."""
    service = get_scenario_service()
    result = await service.check_unlock_status(db, current_user.id)
    return UnlockStatusResponse(**result)
