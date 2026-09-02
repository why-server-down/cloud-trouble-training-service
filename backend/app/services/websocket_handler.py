"""터미널 WebSocket 연결 처리.

실행 대상은 서버가 DB 세션에서 만든 SandboxRef 뿐이다. 클라이언트가 보낸
namespace/pod 는 신뢰하지 않으며, 프로토콜 메시지에서도 읽지 않는다.
"""
import asyncio
import time
import logging
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import (
    COMMAND_DURATION,
    COMMAND_EXECUTIONS,
    command_category,
)
from app.models import CommandLog, TerminalSession
from app.services.command_executor import BaseCommandExecutor, create_command_executor
from app.services.command_validator import CommandValidator
from app.services.sandbox_service import SandboxRef

logger = logging.getLogger(__name__)

# WebSocket close code
CLOSE_REPLACED = 4000  # 같은 세션에 새 연결이 들어와 이전 연결을 종료
CLOSE_TOKEN_INVALID = 4001
CLOSE_OWNER_MISMATCH = 4003
CLOSE_SESSION_NOT_FOUND = 4004
CLOSE_ENVIRONMENT_UNAVAILABLE = 4010


class WebSocketHandler:
    def __init__(self, executor: BaseCommandExecutor | None = None):
        self.active_connections: dict[str, WebSocket] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.command_validator = CommandValidator()
        self._executor = executor

    @property
    def command_executor(self) -> BaseCommandExecutor:
        # 설정에 따라 한 번만 만든다. 클러스터 접속이 필요하므로 지연 생성한다.
        if self._executor is None:
            self._executor = create_command_executor()
        return self._executor

    async def handle_connection(
        self,
        websocket: WebSocket,
        *,
        session: TerminalSession,
        sandbox: SandboxRef,
        db: AsyncSession,
    ):
        session_id = str(session.id)

        # accept 는 호출자(엔드포인트)가 이미 했다. 여기서 다시 부르면
        # ASGI 상태 기계가 accept 를 두 번 받아 RuntimeError 로 연결이 끊긴다.

        # 실행 대상(sandbox)과 검증 기준(session)이 어긋나면 한 환경의 정책으로
        # 통과한 명령이 다른 환경에서 실행된다. 엔드포인트가 session 에서
        # sandbox 를 만들지만, 여기서도 한 번 더 확인한다.
        if sandbox.environment != session.environment or sandbox.namespace != session.namespace:
            logger.error(
                "sandbox does not match session",
                extra={
                    "session_id": session_id,
                    "session_environment": session.environment,
                    "sandbox_environment": sandbox.environment,
                },
            )
            await websocket.close(
                code=CLOSE_ENVIRONMENT_UNAVAILABLE, reason="Sandbox does not match the session"
            )
            return

        # 같은 세션에 이미 연결이 있으면 이전 연결을 정리한다.
        previous = self.active_connections.get(session_id)
        if previous is not None:
            try:
                await previous.close(code=CLOSE_REPLACED, reason="Replaced by a new connection")
            except Exception:
                pass

        self.active_connections[session_id] = websocket
        self._locks.setdefault(session_id, asyncio.Lock())

        await self._touch_session(db, session)
        logger.info(
            "terminal connected",
            extra={"session_id": session_id, "environment": session.environment},
        )

        await self._send_output(
            websocket,
            # 첫 줄의 "Connected to namespace:" 는 프론트가 연결 성립 판정에 쓰므로
            # 문구를 바꾸지 않는다(useTerminalWebSocket).
            f"Connected to namespace: {session.namespace}\n"
            f"Environment: {session.environment}\n"
            f"{self.command_validator.usage_hint(session.environment)}\n\n",
        )

        try:
            while True:
                data = await websocket.receive_json()
                if data.get("type") != "command":
                    continue
                await self._handle_command(
                    websocket=websocket,
                    command=data.get("command", ""),
                    session=session,
                    sandbox=sandbox,
                    db=db,
                    confirmed=bool(data.get("confirmed", False)),
                )
        except WebSocketDisconnect:
            logger.info("terminal disconnected", extra={"session_id": session_id})
        finally:
            # 내가 등록한 연결일 때만 정리한다(교체된 뒤 늦게 도착한 종료 처리 방지).
            if self.active_connections.get(session_id) is websocket:
                self.active_connections.pop(session_id, None)
                self._locks.pop(session_id, None)

    async def _handle_command(
        self,
        websocket: WebSocket,
        command: str,
        session: TerminalSession,
        sandbox: SandboxRef,
        db: AsyncSession,
        confirmed: bool = False,
    ):
        command = command.strip()
        if not command:
            return

        session_id = str(session.id)
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        if lock.locked():
            await self._send_error(websocket, "이전 명령이 아직 실행 중입니다.")
            return

        async with lock:
            argv = command.split()
            if len(argv) >= 2 and argv[1] == "delete" and confirmed:
                validation = self.command_validator.validate_delete(
                    command, session.namespace, confirmed=True, environment=session.environment
                )
            else:
                validation = self.command_validator.validate_command(
                    command, session.namespace, environment=session.environment
                )

            if not validation.is_valid:
                if validation.requires_confirmation:
                    await self._send_confirmation(websocket, command, validation.error)
                else:
                    await self._send_error(websocket, validation.error)
                return

            started = time.perf_counter()
            result = await self.command_executor.execute(validation.argv, sandbox)
            COMMAND_DURATION.labels(session.environment).observe(
                time.perf_counter() - started
            )
            COMMAND_EXECUTIONS.labels(
                session.environment,
                # 원문이 아니라 저카디널리티 범주만 label 로 쓴다.
                command_category(validation.argv),
                "ok" if result.exit_code == 0 else "error",
            ).inc()

            # 명령 원문·출력 본문은 info 로그에 남기지 않는다.
            logger.info(
                "command executed",
                extra={
                    "session_id": session_id,
                    "environment": session.environment,
                    "exit_code": result.exit_code,
                    "duration_ms": round(result.execution_time),
                },
            )

            await self._send_output(
                websocket, result.output, result.exit_code, result.execution_time
            )

            db.add(
                CommandLog(
                    session_id=session.id,
                    command=command,
                    output=result.output[: settings.COMMAND_LOG_LIMIT_BYTES],
                    exit_code=result.exit_code,
                    executed_at=datetime.now(timezone.utc),
                    execution_time=result.execution_time,
                )
            )
            session.last_activity = datetime.now(timezone.utc)
            await db.commit()

    @staticmethod
    async def _touch_session(db: AsyncSession, session: TerminalSession):
        session.last_activity = datetime.now(timezone.utc)
        await db.commit()

    async def _send_output(
        self,
        websocket: WebSocket,
        data: str,
        exit_code: int = 0,
        execution_time: float = 0.0,
    ):
        # 터미널 출력을 위해 \n을 \r\n으로 변환
        await websocket.send_json({
            "type": "output",
            "data": data.replace("\n", "\r\n"),
            "exit_code": exit_code,
            "execution_time": execution_time,
        })

    async def _send_error(self, websocket: WebSocket, message: str):
        await websocket.send_json({"type": "error", "message": message})

    async def _send_confirmation(self, websocket: WebSocket, command: str, message: str):
        await websocket.send_json({
            "type": "confirm",
            "message": message,
            "command": command,
        })
