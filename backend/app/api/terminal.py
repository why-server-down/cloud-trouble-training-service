from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Response, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.environments import assert_implemented
from app.core.security import decode_access_token
from app.models import TerminalSession, User
from app.schemas import SessionCreate, SessionResponse
from app.services.sandbox_service import (
    SandboxNotReadyError,
    get_sandbox_service,
)
from app.services.websocket_handler import WebSocketHandler

router = APIRouter(tags=["terminal"])

ws_handler = WebSocketHandler()


@router.post("/api/terminal/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: SessionCreate = Body(default=SessionCreate()),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        environment = assert_implemented(request.environment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    namespace = f"user-{current_user.id}"
    result = await db.execute(
        select(TerminalSession)
        .where(
            TerminalSession.user_id == current_user.id,
            TerminalSession.environment == environment,
            TerminalSession.is_active.is_(True),
        )
        .order_by(TerminalSession.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()

    sandbox_service = get_sandbox_service()
    try:
        await sandbox_service.ensure(
            user_id=current_user.id,
            namespace=namespace,
            environment=environment,
        )
    except SandboxNotReadyError as exc:
        if existing is not None:
            existing.is_active = False
            await db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        if existing is not None:
            existing.is_active = False
            await db.commit()
        raise HTTPException(
            status_code=503,
            detail="훈련 샌드박스를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc

    if existing is not None:
        existing.last_activity = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing

    session = TerminalSession(
        user_id=current_user.id,
        namespace=namespace,
        environment=environment,
    )
    db.add(session)
    try:
        await db.commit()
        await db.refresh(session)
    except Exception:
        await db.rollback()
        sandbox = sandbox_service.reference_for(
            user_id=current_user.id,
            namespace=namespace,
            environment=environment,
        )
        await sandbox_service.cleanup(sandbox)
        raise
    return session


@router.delete(
    "/api/terminal/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TerminalSession).where(
            TerminalSession.id == session_id,
            TerminalSession.user_id == current_user.id,
            TerminalSession.is_active.is_(True),
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="활성 터미널 세션을 찾을 수 없습니다.")

    sandbox_service = get_sandbox_service()
    sandbox = sandbox_service.reference_for(
        user_id=current_user.id,
        namespace=session.namespace,
        environment=session.environment,
    )
    await sandbox_service.cleanup(sandbox)
    session.is_active = False
    session.last_activity = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.websocket("/ws/terminal/{session_id}")
async def terminal_websocket(
    websocket: WebSocket,
    session_id: str,
):
    # WebSocket에서는 Depends를 못쓰므로 직접 토큰 검증
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token payload")
        return

    namespace = f"user-{user_id}"

    async for db in get_db():
        # 세션 활동 시간 업데이트
        result = await db.execute(
            select(TerminalSession).where(TerminalSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.last_activity = datetime.now(timezone.utc)
            await db.commit()

        await ws_handler.handle_connection(
            websocket=websocket,
            user_id=user_id,
            session_id=session_id,
            namespace=namespace,
            db=db,
        )
