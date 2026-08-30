from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services.analytics_service import analytics_service

router = APIRouter(prefix="/api", tags=["dashboard"])


# "all" 은 전체 합계를 뜻한다. 프론트가 환경 탭과 통합 대시보드를 같은
# 엔드포인트로 그릴 수 있도록 계약에 포함한다.
ALL_ENVIRONMENTS = "all"
EnvironmentFilter = Literal["all", "kubernetes", "docker", "linux"]


def _resolve(environment: EnvironmentFilter) -> str | None:
    return None if environment == ALL_ENVIRONMENTS else environment


@router.get("/dashboard/stats")
async def get_dashboard_stats(
    environment: EnvironmentFilter = ALL_ENVIRONMENTS,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 통계. `environment=all` 이면 전체 합계와 환경별 분해를 함께 준다."""
    return await analytics_service.get_dashboard_stats(
        db, current_user, _resolve(environment)
    )


@router.get("/dashboard/learning-curve")
async def get_learning_curve(
    environment: EnvironmentFilter = ALL_ENVIRONMENTS,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.get_learning_curve(
        db, current_user.id, _resolve(environment)
    )


@router.get("/leaderboard")
async def get_leaderboard(
    limit: int = Query(default=100, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.get_leaderboard(db, current_user.id, limit)


@router.get("/achievements")
async def get_achievements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.get_achievements(db, current_user.id)
