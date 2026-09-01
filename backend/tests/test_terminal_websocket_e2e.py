"""터미널 WebSocket 의 실제 ASGI 경로 계약 (BE-24).

기존 WebSocket 테스트는 전부 가짜 WebSocket 객체를 썼다. 가짜는 `accept()` 가
그냥 플래그만 세우므로 **ASGI 상태 기계를 위반해도 통과한다.** 실제로
`accept()` 를 두 번 부르면 Starlette 가 RuntimeError 를 내고 연결이 끊기는데,
가짜 기반 테스트로는 이것을 잡을 수 없었다(2026-09-01 확인).

그래서 이 파일만 TestClient 로 진짜 핸드셰이크를 한다.
"""
import asyncio
import json
import uuid

import pytest

from app.main import app
from app.services.command_executor import MockCommandExecutor
from app.services.sandbox_service import SandboxRef
from app.services.websocket_handler import (
    CLOSE_ENVIRONMENT_UNAVAILABLE,
    CLOSE_OWNER_MISMATCH,
    CLOSE_TOKEN_INVALID,
)

NAMESPACE = "user-e2e"


class _Session:
    def __init__(self, user_id, *, environment="kubernetes", namespace=NAMESPACE):
        self.id = uuid.uuid4()
        self.user_id = user_id
        self.namespace = namespace
        self.environment = environment
        self.is_active = True
        self.last_activity = None


class _Db:
    def __init__(self, session):
        self._session = session
        self.added = []

    async def execute(self, stmt):
        session = self._session

        class R:
            def scalar_one_or_none(self):
                return session

        return R()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass


class _SandboxService:
    """엔드포인트가 세션에서 만드는 실행 대상. 환경/네임스페이스를 바꿔 끼울 수 있다."""

    def __init__(self, *, environment=None, namespace=None):
        self._environment = environment
        self._namespace = namespace

    def reference_for(self, *, user_id, namespace, environment):
        return SandboxRef(
            id="e2e",
            namespace=self._namespace or namespace,
            pod_name="sandbox-e2e",
            container_name="toolbox",
            environment=self._environment or environment,
        )


class _WebSocketDriver:
    """ASGI 앱을 직접 호출하는 최소 WebSocket 클라이언트.

    Starlette 의 `WebSocket` 객체가 그대로 쓰이므로 accept/send/close 순서를
    어기면 실제 배포와 똑같이 RuntimeError 가 난다.
    """

    def __init__(self, session_id, token="valid"):
        query = f"token={token}".encode() if token else b""
        self.scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": f"/ws/terminal/{session_id}",
            "raw_path": f"/ws/terminal/{session_id}".encode(),
            "query_string": query,
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "subprotocols": [],
        }
        self._inbox = None
        self.outbox = []

    async def _receive(self):
        return await self._inbox.get()

    async def _send(self, message):
        self.outbox.append(message)

    def run(self, commands=()):
        async def main():
            self._inbox = asyncio.Queue()
            await self._inbox.put({"type": "websocket.connect"})
            for command in commands:
                await self._inbox.put(
                    {"type": "websocket.receive", "text": json.dumps(command)}
                )
            await self._inbox.put({"type": "websocket.disconnect", "code": 1000})
            await app(self.scope, self._receive, self._send)

        asyncio.run(main())
        return self

    @property
    def accepts(self):
        return [m for m in self.outbox if m["type"] == "websocket.accept"]

    @property
    def messages(self):
        return [
            json.loads(m["text"])
            for m in self.outbox
            if m["type"] == "websocket.send" and "text" in m
        ]

    @property
    def close_code(self):
        closes = [m for m in self.outbox if m["type"] == "websocket.close"]
        return closes[-1].get("code") if closes else None


@pytest.fixture
def wired(monkeypatch):
    """실제 라우트를 태우되 DB·토큰·샌드박스·실행기만 대체한다."""
    import app.api.terminal as terminal

    user_id = uuid.uuid4()
    session = _Session(user_id)
    db = _Db(session)

    async def fake_get_db():
        yield db

    monkeypatch.setattr(terminal, "get_db", fake_get_db)
    monkeypatch.setattr(terminal, "decode_access_token", lambda token: {"sub": str(user_id)})
    monkeypatch.setattr(terminal.ws_handler, "_executor", MockCommandExecutor())

    def use_sandbox(**kwargs):
        monkeypatch.setattr(terminal, "get_sandbox_service", lambda: _SandboxService(**kwargs))

    use_sandbox()
    return {
        "session": session,
        "db": db,
        "user_id": user_id,
        "use_sandbox": use_sandbox,
    }


class TestRealHandshake:
    def test_connection_is_accepted_once_and_serves_a_command(self, wired):
        """회귀: 엔드포인트와 핸들러가 각각 accept 하면 여기서 RuntimeError 로 끊긴다."""
        session = wired["session"]
        driver = _WebSocketDriver(session.id).run(
            [{"type": "command", "command": "kubectl get pods"}]
        )

        assert len(driver.accepts) == 1
        assert driver.close_code is None

        banner, result = driver.messages
        assert session.namespace in banner["data"]
        assert result["type"] == "output"
        assert result["exit_code"] == 0

        # 명령 로그가 세션에 남는다
        assert [log.session_id for log in wired["db"].added] == [session.id]

    def test_rejected_command_does_not_close_the_connection(self, wired):
        driver = _WebSocketDriver(wired["session"].id).run(
            [
                {"type": "command", "command": "kubectl get pods | grep x"},
                {"type": "command", "command": "kubectl get pods"},
            ]
        )

        _, rejected, accepted = driver.messages
        assert rejected["type"] == "error"
        assert accepted["type"] == "output"
        # 거절된 명령은 기록하지 않는다
        assert len(wired["db"].added) == 1


class TestRejection:
    def test_missing_token_closes_4001(self, wired):
        driver = _WebSocketDriver(wired["session"].id, token=None).run()
        assert driver.close_code == CLOSE_TOKEN_INVALID

    def test_other_users_session_closes_4003(self, wired, monkeypatch):
        import app.api.terminal as terminal

        monkeypatch.setattr(
            terminal, "decode_access_token", lambda token: {"sub": str(uuid.uuid4())}
        )
        driver = _WebSocketDriver(wired["session"].id).run()
        assert driver.close_code == CLOSE_OWNER_MISMATCH

    def test_sandbox_environment_mismatch_closes_4010(self, wired):
        """세션은 kubernetes 인데 실행 대상이 docker 면 명령을 실행하지 않는다.

        환경이 어긋나면 kubernetes 정책으로 통과한 argv 가 docker 샌드박스에서
        실행된다. 정책 검증과 실행 대상은 반드시 같은 환경이어야 한다.
        """
        wired["use_sandbox"](environment="docker")
        driver = _WebSocketDriver(wired["session"].id).run(
            [{"type": "command", "command": "kubectl get pods"}]
        )
        assert driver.close_code == CLOSE_ENVIRONMENT_UNAVAILABLE
        assert wired["db"].added == []

    def test_sandbox_namespace_mismatch_closes_4010(self, wired):
        """네임스페이스가 어긋나면 `-n` 으로 주입된 대상과 실행 위치가 달라진다."""
        wired["use_sandbox"](namespace="user-someone-else")
        driver = _WebSocketDriver(wired["session"].id).run(
            [{"type": "command", "command": "kubectl get pods"}]
        )
        assert driver.close_code == CLOSE_ENVIRONMENT_UNAVAILABLE
        assert wired["db"].added == []
