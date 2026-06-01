from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import TerminalSession, User
from app.schemas import SessionResponse
from app.services.k8s_setup import get_k8s_setup_service
from app.services.websocket_handler import WebSocketHandler

router = APIRouter(tags=["terminal"])

ws_handler = WebSocketHandler()


@router.post("/api/terminal/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    namespace = f"user-{current_user.id}"

    k8s = get_k8s_setup_service()
    await k8s.setup_user_namespace(namespace)

    session = TerminalSession(
        user_id=current_user.id,
        namespace=namespace,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


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
        from sqlalchemy import select
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
