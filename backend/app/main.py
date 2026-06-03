import asyncio
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.missions import router as missions_router
from app.api.scenarios import router as scenarios_router
from app.api.terminal import router as terminal_router
from app.core.database import Base, async_session, engine
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS
from app.services.seed_data import seed_missions

# Windows에서 subprocess 지원을 위한 이벤트 루프 설정
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as db:
        await seed_missions(db)
    yield


app = FastAPI(
    title="K8s Survival Camp API",
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
app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health_check():
    return {"status": "ok"}
