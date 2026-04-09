from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Mission, User
from app.schemas import ChatRequest, ChatResponse
from app.ai.tutor_service import get_tutor_service
from app.services.mission_service import MissionService
from app.services.service_factory import get_mission_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
async def chat_with_tutor(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI 튜터에게 질문 (소크라테스식 힌트 제공)
    - hint_level 0: 방향만 제시
    - hint_level 1: 확인할 리소스 지목
    - hint_level 2: 정확한 kubectl 명령어 제공
    - hint_level 3: 전체 해결 방법 제공
    """
    mission_service: MissionService = get_mission_service()
    attempt = await mission_service.get_active_attempt(db, current_user.id)

    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="진행 중인 미션이 없습니다. 미션을 시작한 후 질문해주세요.",
        )

    # 미션 정보 조회
    result = await db.execute(select(Mission).where(Mission.id == attempt.mission_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="미션을 찾을 수 없습니다")

    namespace = f"user-{current_user.id}"
    tutor = get_tutor_service()

    response_text = await tutor.get_hint(
        user_question=body.message,
        attempt_id=attempt.id,
        hint_level=body.hint_level,
        mission_name=mission.name,
        mission_level=mission.level,
        chaos_type=mission.chaos_type,
        namespace=namespace,
    )

    return ChatResponse(
        response=response_text,
        hint_level=body.hint_level,
        mission_name=mission.name,
    )
