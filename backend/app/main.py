import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
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
    # wildcard 와 allow_credentials 를 함께 쓰면 브라우저가 자격 증명을 아무 origin 에나
    # 보낸다. 허용 목록을 설정으로 받는다.
    allow_origins=settings.cors_origin_list,
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
    """프로세스가 살아 있는지만 본다. 의존 서비스를 확인하지 않는다.

    여기서 DB 를 확인하면 DB 가 잠깐 흔들릴 때 오케스트레이터가 살아 있는 프로세스를
    죽여 복구를 더 어렵게 만든다.
    """
    return {"status": "ok"}


@app.get("/ready")
async def readiness_check(response: Response):
    """요청을 받을 준비가 됐는지. 의존 서비스 상태를 함께 알린다.

    하나라도 준비되지 않으면 503 을 준다. 개별 상태를 함께 돌려주므로 어떤 의존이
    문제인지 바로 알 수 있다.
    """
    checks = {
        "database": await _check_database(),
        "kubernetes": await _check_kubernetes(),
        "qdrant": await _check_qdrant(),
    }
    ready = all(state["ok"] for state in checks.values() if state["required"])
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ready": ready, "checks": checks}


async def _check_database() -> dict:
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ok": True, "required": True}
    except Exception as exc:
        return {"ok": False, "required": True, "error": type(exc).__name__}


async def _check_kubernetes() -> dict:
    """샌드박스를 만들려면 필요하다. mock 백엔드에서는 없어도 된다."""
    required = settings.TERMINAL_BACKEND != "mock"
    try:
        from kubernetes import client, config as k8s_config

        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()
        await asyncio.get_running_loop().run_in_executor(
            None, client.VersionApi().get_code
        )
        return {"ok": True, "required": required}
    except Exception as exc:
        return {"ok": False, "required": required, "error": type(exc).__name__}


async def _check_qdrant() -> dict:
    """RAG 검색에 쓴다. mock AI 백엔드에서는 없어도 동작한다."""
    required = settings.AI_BACKEND != "mock"
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{settings.QDRANT_URL}/readyz")
        return {"ok": res.status_code < 400, "required": required}
    except Exception as exc:
        return {"ok": False, "required": required, "error": type(exc).__name__}
