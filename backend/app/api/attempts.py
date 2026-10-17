import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import MissionAttempt, User
from app.schemas import MissionAttemptResponse

router = APIRouter(prefix="/api/attempts", tags=["attempts"])


@router.get("/{attempt_id}", response_model=MissionAttemptResponse)
async def get_attempt(
    attempt_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """끝난 시도까지 포함한 내 시도 하나 (BE-30).

    시간 초과로 정리된 시도는 `/api/missions/status` 가 404 를 주므로, 결과 화면은
    시작 때 받은 attempt id 로 이 API 를 불러 서버 점수를 읽는다.
    고정 미션·AI 시나리오 공통이며 조회만 한다 (만료 처리를 여기서 하지 않는다).
    남의 시도는 없는 것과 같은 404 로 돌려준다.
    """
    result = await db.execute(
        select(MissionAttempt).where(
            MissionAttempt.id == attempt_id,
            MissionAttempt.user_id == current_user.id,
        )
    )
    attempt = result.scalar_one_or_none()
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="시도를 찾을 수 없습니다")
    return attempt
