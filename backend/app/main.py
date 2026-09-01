import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.environments import router as environments_router
from app.api.missions import router as missions_router
from app.api.scenarios import router as scenarios_router
from app.api.terminal import router as terminal_router
from app.core.config import settings
from app.core.database import (
    Base,
    async_session,
    engine,
    schema_needs_migration,
    stamp_head_if_schema_current,
)
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS
from app.services.reconciliation_service import reconcile_active_attempts
from app.services.seed_data import seed_missions
from app.services.qdrant_init import auto_ingest_if_empty

logger = logging.getLogger(__name__)

# Windows에서 subprocess 지원을 위한 이벤트 루프 설정
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 스키마 관리는 Alembic 이 담당한다(`alembic upgrade head`).
    # AUTO_CREATE_SCHEMA 는 로컬 개발/테스트에서 빈 DB 를 바로 쓰기 위한 편의 장치이며,
    # 배포 환경에서는 꺼두고 마이그레이션을 배포 단계에서 실행한다.
    if settings.AUTO_CREATE_SCHEMA:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # create_all 이 최신 스키마를 만든 경우에만 head 로 표시한다.
            # 이력을 남기지 않으면 이후 `alembic upgrade head` 가 이미 있는 컬럼을
            # 다시 추가하려다 실패한다.
            await conn.run_sync(stamp_head_if_schema_current)

    # 옛 스키마 위에서 조용히 깨지는 것을 막는다.
    # create_all 은 기존 테이블을 ALTER 하지 않으므로 Alembic 이전에 만들어진 DB 는
    # 여기서 걸러 명확한 안내와 함께 기동을 중단한다.
    async with engine.begin() as conn:
        outdated = await conn.run_sync(schema_needs_migration)
    if outdated:
        raise RuntimeError(
            "데이터베이스 스키마가 최신이 아닙니다. "
            "`cd backend && alembic upgrade head` 를 실행한 뒤 다시 시작하세요. "
            "(기존 로컬 DB 도 그대로 적용되며 데이터는 보존됩니다)"
        )

    async with async_session() as db:
        await seed_missions(db)
        # 재시작 전에 진행 중이던 attempt 를 실제 상태와 대조한다.
        # 시간 초과 정리가 사용자의 status 조회에만 의존하면, 돌아오지 않는
        # 사용자의 장애가 클러스터에 그대로 남는다.
        try:
            await reconcile_active_attempts(db)
        except Exception:
            logger.exception("startup reconciliation failed")
    await auto_ingest_if_empty()
    yield


app = FastAPI(
    title="AfterFail API",
    description="AI 기반 클라우드 장애 대응 훈련 플랫폼",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def record_http_metrics(request, call_next):
    started_at = time.perf_counter()
    response = await call_next(request)
    path = request.url.path
    HTTP_REQUESTS.labels(request.method, path, response.status_code).inc()
    HTTP_DURATION.labels(request.method, path).observe(time.perf_counter() - started_at)
    return response


app.include_router(auth_router)
app.include_router(terminal_router)
app.include_router(missions_router)
app.include_router(scenarios_router)
app.include_router(chat_router)
app.include_router(dashboard_router)
app.include_router(environments_router)
app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health_check():
    return {"status": "ok"}
