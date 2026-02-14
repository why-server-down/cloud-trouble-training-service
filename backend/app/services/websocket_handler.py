from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CommandLog
from app.services.command_executor import CommandExecutor
from app.services.command_validator import CommandValidator


class WebSocketHandler:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.command_validator = CommandValidator()
        self.command_executor = CommandExecutor()

    async def handle_connection(
        self,
        websocket: WebSocket,
        user_id: str,
        session_id: str,
        namespace: str,
        db: AsyncSession,
    ):
        await websocket.accept()
        self.active_connections[session_id] = websocket

        await self._send_output(
            websocket,
            f"Connected to namespace: {namespace}\n"
            f"Type 'kubectl' commands to interact with your cluster.\n\n",
        )

        try:
            while True:
                data = await websocket.receive_json()
                print(f"📥 Received WebSocket message: {data}")

                if data.get("type") == "command":
                    await self._handle_command(
                        websocket=websocket,
                        command=data.get("command", ""),
                        namespace=namespace,
                        session_id=session_id,
                        db=db,
                        confirmed=data.get("confirmed", False),
                    )

        except WebSocketDisconnect:
            self.active_connections.pop(session_id, None)

    async def _handle_command(
        self,
        websocket: WebSocket,
        command: str,
        namespace: str,
        session_id: str,
        db: AsyncSession,
        confirmed: bool = False,
    ):
        command = command.strip()
        if not command:
            return

        print(f"🔍 Received command: {command}")

        # Validate
        parts = command.split()
        if len(parts) >= 2 and parts[1] == "delete" and confirmed:
            validation = self.command_validator.validate_delete(command, namespace, confirmed=True)
        else:
            validation = self.command_validator.validate_command(command, namespace)

        print(f"🔍 Validation result: is_valid={validation.is_valid}, error={validation.error}")

        if not validation.is_valid:
            if validation.requires_confirmation:
                await self._send_confirmation(websocket, command, validation.error)
            else:
                await self._send_error(websocket, validation.error)
            return

        print(f"🔍 Executing command: {validation.command}")

        # Execute
        result = await self.command_executor.execute(validation.command)
        
        print(f"🔍 Execution result: exit_code={result.exit_code}, output={result.output[:100]}")

        # Send output
        await self._send_output(
            websocket,
            result.output,
            result.exit_code,
            result.execution_time,
        )

        # Log
        log = CommandLog(
            session_id=session_id,
            command=command,
            output=result.output[:5000],  # truncate large outputs
            exit_code=result.exit_code,
            executed_at=datetime.now(timezone.utc),
            execution_time=result.execution_time,
        )
        db.add(log)
        await db.commit()

    async def _send_output(
        self,
        websocket: WebSocket,
        data: str,
        exit_code: int = 0,
        execution_time: float = 0.0,
    ):
        # 터미널 출력을 위해 \n을 \r\n으로 변환
        formatted_data = data.replace('\n', '\r\n')
        
        await websocket.send_json({
            "type": "output",
            "data": formatted_data,
            "exit_code": exit_code,
            "execution_time": execution_time,
        })

    async def _send_error(self, websocket: WebSocket, message: str):
        await websocket.send_json({
            "type": "error",
            "message": message,
        })

    async def _send_confirmation(self, websocket: WebSocket, command: str, message: str):
        await websocket.send_json({
            "type": "confirm",
            "message": message,
            "command": command,
        })
