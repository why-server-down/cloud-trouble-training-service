from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core import environments
from app.models import User
from app.schemas import EnvironmentListResponse

router = APIRouter(prefix="/api/environments", tags=["environments"])


@router.get("", response_model=EnvironmentListResponse)
async def list_environments(current_user: User = Depends(get_current_user)):
    """훈련 환경 가용 상태 목록.

    source of truth 는 `core/environments.py` 다. 프론트는 이 응답으로 환경 탭을
    그리며, label·설명 같은 표시 문구는 프론트가 담당한다.

    - `available` : 실제로 세션 생성·장애 주입·검증이 가능한 환경
    - `preparing` : 계약상 존재하지만 아직 구현되지 않은 환경 (선택 시 400)
    """
    return EnvironmentListResponse(items=environments.availability())
