from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import (
    MissionAttemptCreate,
    MissionAttemptResponse,
    MissionCompleteResponse,
    MissionResponse,
    MissionStatusResponse,
)
from app.services.service_factory import get_mission_service

router = APIRouter(prefix="/api/missions", tags=["missions"])


@router.get("/", response_model=list[MissionResponse])
async def list_missions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """미션 목록 조회 (잠금 상태 포함)"""
    service = get_mission_service()
    missions = await service.list_missions(db, current_user)
    return [
        MissionResponse(
            id=m["mission"].id,
            name=m["mission"].name,
            level=m["mission"].level,
            description=m["mission"].description,
            chaos_type=m["mission"].chaos_type,
            base_score=m["mission"].base_score,
            time_limit=m["mission"].time_limit,
            hint_penalty=m["mission"].hint_penalty,
            is_unlocked=m["is_unlocked"],
        )
        for m in missions
    ]


@router.post("/start", response_model=MissionAttemptResponse, status_code=status.HTTP_201_CREATED)
async def start_mission(
    body: MissionAttemptCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """미션 시작"""
    service = get_mission_service()
    try:
        attempt = await service.start_mission(db, current_user, body.mission_id)
        return attempt
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/status", response_model=MissionStatusResponse)
async def get_mission_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """진행 중인 미션 상태 조회"""
    service = get_mission_service()
    attempt = await service.get_active_attempt(db, current_user.id)
    if not attempt or attempt.attempt_type == "ai_scenario":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="진행 중인 미션이 없습니다"
        )
    try:
        status_data = await service.get_status(db, attempt.id)
        return MissionStatusResponse(**status_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/check", response_model=MissionCompleteResponse)
async def check_mission(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """미션 해결 여부 확인"""
    service = get_mission_service()
    attempt = await service.get_active_attempt(db, current_user.id)
    if not attempt or attempt.attempt_type == "ai_scenario":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="진행 중인 미션이 없습니다"
        )
    try:
        result = await service.check_and_complete(db, attempt.id)
        return MissionCompleteResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/abandon", response_model=MissionAttemptResponse)
async def abandon_mission(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """미션 포기 (0점 처리)"""
    service = get_mission_service()
    try:
        attempt = await service.abandon_mission(db, current_user.id)
        return attempt
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/hint", response_model=MissionAttemptResponse)
async def use_hint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """힌트 사용 (감점)"""
    service = get_mission_service()
    attempt = await service.get_active_attempt(db, current_user.id)
    if not attempt or attempt.attempt_type == "ai_scenario":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="진행 중인 미션이 없습니다"
        )
    try:
        attempt = await service.use_hint(db, attempt.id)
        return attempt
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/debug/resolve")
async def debug_resolve(
    current_user: User = Depends(get_current_user),
):
    """(Mock 전용) 수동으로 장애 해결 처리"""
    from app.core.config import settings

    if settings.VALIDATION_BACKEND != "mock":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    service = get_mission_service()
    namespace = f"user-{current_user.id}"
    service._validation.mark_resolved(namespace)
    return {"message": f"{namespace} 장애 해결 처리됨"}
