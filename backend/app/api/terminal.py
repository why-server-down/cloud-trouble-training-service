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
from app.services.websocket_handler import (
    CLOSE_ENVIRONMENT_UNAVAILABLE,
    CLOSE_OWNER_MISMATCH,
    CLOSE_SESSION_NOT_FOUND,
    CLOSE_TOKEN_INVALID,
    WebSocketHandler,
)

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
    """터미널 WebSocket.

    실행에 필요한 값은 전부 서버가 정한다.
      user_id     <- JWT
      session     <- id + user_id + is_active
      namespace   <- session.namespace
      environment <- session.environment
      sandbox     <- SandboxService.reference_for(...)

    클라이언트가 보낸 namespace/pod 는 어느 단계에서도 쓰지 않는다.
    close code 를 클라이언트에 전달하려면 accept 이후에 close 해야 하므로,
    거절하는 경우에도 먼저 accept 한다.
    """
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=CLOSE_TOKEN_INVALID, reason="Missing token")
        return

    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=CLOSE_TOKEN_INVALID, reason="Invalid token")
        return

    raw_user_id = payload.get("sub")
    if not raw_user_id:
        await websocket.close(code=CLOSE_TOKEN_INVALID, reason="Invalid token payload")
        return

    try:
        user_id = UUID(str(raw_user_id))
        session_uuid = UUID(session_id)
    except ValueError:
        await websocket.close(code=CLOSE_SESSION_NOT_FOUND, reason="Session not found")
        return

    async for db in get_db():
        # 소유권 판정을 위해 먼저 id 로만 조회한다.
        # 없으면 4004, 있으나 내 것이 아니거나 비활성이면 4003 으로 구분한다.
        result = await db.execute(
            select(TerminalSession).where(TerminalSession.id == session_uuid)
        )
        session = result.scalar_one_or_none()

        if session is None:
            await websocket.close(code=CLOSE_SESSION_NOT_FOUND, reason="Session not found")
            return

        if session.user_id != user_id or not session.is_active:
            await websocket.close(
                code=CLOSE_OWNER_MISMATCH, reason="Session is not available for this user"
            )
            return

        try:
            environment = assert_implemented(session.environment)
        except ValueError:
            await websocket.close(
                code=CLOSE_ENVIRONMENT_UNAVAILABLE, reason="Environment is not available"
            )
            return

        sandbox_service = get_sandbox_service()
        try:
            sandbox = sandbox_service.reference_for(
                user_id=session.user_id,
                namespace=session.namespace,
                environment=environment,
            )
        except Exception:
            await websocket.close(code=CLOSE_SESSION_NOT_FOUND, reason="Sandbox not found")
            return

        await ws_handler.handle_connection(
            websocket=websocket,
            session=session,
            sandbox=sandbox,
            db=db,
        )
        return
