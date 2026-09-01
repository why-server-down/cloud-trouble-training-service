"""터미널 실행 경로의 보안 계약 (BE-05, BE-06).

- 사용자 명령은 호스트 셸에서 실행되지 않는다.
- 실행 대상은 서버가 DB 세션에서 만든 SandboxRef 뿐이다.
- WebSocket 은 세션 소유권을 검증하고 원인별 close code 를 돌려준다.
"""
import ast
import asyncio
import pathlib
import uuid

import pytest

from app.services.command_executor import MockCommandExecutor, _truncate
from app.services.command_validator import CommandValidator
from app.services.sandbox_service import SandboxRef
from app.services.websocket_handler import (
    CLOSE_OWNER_MISMATCH,
    CLOSE_REPLACED,
    CLOSE_SESSION_NOT_FOUND,
    CLOSE_TOKEN_INVALID,
    WebSocketHandler,
)

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"
NAMESPACE = "user-test123"


def _sandbox(namespace: str = NAMESPACE) -> SandboxRef:
    return SandboxRef(
        id="abc123",
        namespace=namespace,
        pod_name="sandbox-abc123",
        container_name="toolbox",
        environment="kubernetes",
    )


class _FakeSession:
    def __init__(self, *, user_id=None, is_active=True, namespace=NAMESPACE):
        self.id = uuid.uuid4()
        self.user_id = user_id or uuid.uuid4()
        self.namespace = namespace
        self.environment = "kubernetes"
        self.is_active = is_active
        self.last_activity = None


class _FakeDB:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


class _FakeWebSocket:
    def __init__(self, incoming=None):
        self.accepted = False
        self.sent = []
        self.close_code = None
        self._incoming = list(incoming or [])

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=""):
        self.close_code = code

    async def send_json(self, data):
        self.sent.append(data)

    async def receive_json(self):
        if self._incoming:
            return self._incoming.pop(0)
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect(code=1000)


class TestNoHostShellExecution:
    """인수 조건: repository backend code 에서 host shell 실행 0건."""

    FORBIDDEN_CALLS = {"system", "popen", "create_subprocess_shell"}
    # 모듈별로 금지 이름이 다르다. `asyncio.run` 은 이벤트 루프 진입점이지 호스트
    # 프로세스 실행이 아니므로, 모듈을 구분하지 않으면 거짓 위반이 잡힌다.
    FORBIDDEN_BY_MODULE = {
        "subprocess": {"run", "call", "check_call", "check_output", "Popen"},
        "asyncio": {"create_subprocess_shell", "create_subprocess_exec"},
    }

    def _violations(self):
        found = []
        for path in APP_DIR.rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                # shell=True 키워드
                for keyword in node.keywords:
                    if (
                        keyword.arg == "shell"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                    ):
                        found.append(f"{path.name}:{node.lineno} shell=True")
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                if name in self.FORBIDDEN_CALLS:
                    found.append(f"{path.name}:{node.lineno} {name}()")
                if isinstance(func, ast.Attribute):
                    root = func.value
                    if isinstance(root, ast.Name):
                        forbidden = self.FORBIDDEN_BY_MODULE.get(root.id, set())
                        if name in forbidden:
                            found.append(f"{path.name}:{node.lineno} {root.id}.{name}()")
        return found

    def test_no_shell_execution_in_backend_code(self):
        assert self._violations() == []

    @pytest.mark.parametrize(
        "source",
        [
            "subprocess.run(['ls'])",
            "subprocess.Popen(['ls'])",
            "asyncio.create_subprocess_shell('ls')",
            "asyncio.create_subprocess_exec('ls')",
            "os.system('ls')",
            "run(['ls'], shell=True)",
        ],
    )
    def test_guard_catches_real_violations(self, source, tmp_path, monkeypatch):
        """가드가 좁아지다 아무것도 못 잡는 상태가 되지 않게 고정한다."""
        (tmp_path / "sample.py").write_text(source)
        import tests.test_terminal_security as module

        monkeypatch.setattr(module, "APP_DIR", tmp_path)
        assert self._violations() != []

    def test_guard_allows_event_loop_entry(self, tmp_path, monkeypatch):
        """`asyncio.run` 은 호스트 프로세스 실행이 아니다."""
        (tmp_path / "sample.py").write_text("asyncio.run(main())")
        import tests.test_terminal_security as module

        monkeypatch.setattr(module, "APP_DIR", tmp_path)
        assert self._violations() == []


class TestArgvValidation:
    """validator 는 문자열이 아니라 argv 를 내놓는다."""

    @pytest.fixture
    def validator(self):
        return CommandValidator()

    def test_result_is_argv_list(self, validator):
        result = validator.validate_command("kubectl get pods", NAMESPACE)
        assert result.is_valid
        assert isinstance(result.argv, list)
        assert result.argv[0] == "kubectl"
        assert "-n" in result.argv and NAMESPACE in result.argv

    @pytest.mark.parametrize(
        "command",
        [
            "kubectl get pods | grep error",
            "kubectl get pods > out.txt",
            "kubectl get pods < in.txt",
            "kubectl get pods && rm -rf /",
            "kubectl get pods; ls",
            "kubectl get pods `whoami`",
            "kubectl get pods $(whoami)",
            "kubectl get pods\nkubectl delete pod x",
            "kubectl get pods\rkubectl delete pod x",
        ],
    )
    def test_shell_metacharacters_rejected(self, validator, command):
        result = validator.validate_command(command, NAMESPACE)
        assert not result.is_valid
        assert result.argv == []

    def test_unbalanced_quotes_rejected(self, validator):
        result = validator.validate_command('kubectl patch deployment -p "{', NAMESPACE)
        assert not result.is_valid

    def test_quoted_argument_stays_single_token(self, validator):
        result = validator.validate_command(
            'kubectl patch deployment/nginx -p \'{"spec": {}}\'', NAMESPACE
        )
        assert result.is_valid
        assert '{"spec": {}}' in result.argv

    def test_foreign_namespace_rejected(self, validator):
        for command in (
            "kubectl get pods -n kube-system",
            "kubectl get pods --namespace=default",
            "kubectl get pods --namespace kube-system",
        ):
            assert not validator.validate_command(command, NAMESPACE).is_valid


class TestOutputLimit:
    def test_output_is_truncated(self):
        from app.core.config import settings

        oversized = "x" * (settings.COMMAND_OUTPUT_LIMIT_BYTES + 100)
        output, truncated = _truncate(oversized)
        assert truncated
        assert len(output.encode()) < len(oversized.encode())

    def test_small_output_is_untouched(self):
        output, truncated = _truncate("ok")
        assert output == "ok"
        assert not truncated


class TestWebSocketOwnership:
    """인수 조건: 소유자 아님 4003 / 없는 세션 4004 / 토큰 무효 4001."""

    def _run(self, coro):
        return asyncio.run(coro)

    def _call(self, monkeypatch, *, session, token_user_id, session_id=None):
        import app.api.terminal as terminal

        ws = _FakeWebSocket()
        db = _FakeDB()

        async def fake_get_db():
            yield db

        async def fake_execute(stmt):
            class R:
                def scalar_one_or_none(self_inner):
                    return session

            return R()

        db.execute = fake_execute
        monkeypatch.setattr(terminal, "get_db", fake_get_db)
        monkeypatch.setattr(
            terminal, "decode_access_token", lambda t: {"sub": str(token_user_id)}
        )

        ws.query_params = {"token": "valid"}
        target = str(session_id or (session.id if session else uuid.uuid4()))
        self._run(terminal.terminal_websocket(ws, target))
        return ws

    def test_missing_token_closes_4001(self, monkeypatch):
        import app.api.terminal as terminal

        ws = _FakeWebSocket()
        ws.query_params = {}
        self._run(terminal.terminal_websocket(ws, str(uuid.uuid4())))
        assert ws.accepted  # close code 를 전달하려면 accept 가 선행돼야 한다
        assert ws.close_code == CLOSE_TOKEN_INVALID

    def test_unknown_session_closes_4004(self, monkeypatch):
        ws = self._call(monkeypatch, session=None, token_user_id=uuid.uuid4())
        assert ws.close_code == CLOSE_SESSION_NOT_FOUND

    def test_other_users_session_closes_4003(self, monkeypatch):
        """사용자 A 의 토큰으로 사용자 B 의 세션에 연결하면 거절된다."""
        victim = _FakeSession()
        attacker_id = uuid.uuid4()
        ws = self._call(monkeypatch, session=victim, token_user_id=attacker_id)
        assert ws.close_code == CLOSE_OWNER_MISMATCH

    def test_inactive_session_closes_4003(self, monkeypatch):
        owner_id = uuid.uuid4()
        session = _FakeSession(user_id=owner_id, is_active=False)
        ws = self._call(monkeypatch, session=session, token_user_id=owner_id)
        assert ws.close_code == CLOSE_OWNER_MISMATCH

    def test_malformed_session_id_closes_4004(self, monkeypatch):
        import app.api.terminal as terminal

        ws = _FakeWebSocket()
        ws.query_params = {"token": "valid"}
        monkeypatch.setattr(
            terminal, "decode_access_token", lambda t: {"sub": str(uuid.uuid4())}
        )
        self._run(terminal.terminal_websocket(ws, "not-a-uuid"))
        assert ws.close_code == CLOSE_SESSION_NOT_FOUND


class TestCommandLogging:
    def test_log_is_written_to_the_owning_session(self):
        session = _FakeSession()
        db = _FakeDB()
        handler = WebSocketHandler(executor=MockCommandExecutor())
        ws = _FakeWebSocket()

        asyncio.run(
            handler._handle_command(
                websocket=ws,
                command="kubectl get pods",
                session=session,
                sandbox=_sandbox(),
                db=db,
            )
        )

        assert len(db.added) == 1
        assert db.added[0].session_id == session.id
        assert session.last_activity is not None

    def test_rejected_command_is_not_logged(self):
        session = _FakeSession()
        db = _FakeDB()
        handler = WebSocketHandler(executor=MockCommandExecutor())
        ws = _FakeWebSocket()

        asyncio.run(
            handler._handle_command(
                websocket=ws,
                command="kubectl get pods | grep x",
                session=session,
                sandbox=_sandbox(),
                db=db,
            )
        )

        assert db.added == []
        assert ws.sent[-1]["type"] == "error"


class TestConcurrencyLimit:
    def test_second_command_is_rejected_while_one_runs(self):
        """한 세션에서 동시에 실행되는 명령은 1개로 제한한다."""
        session = _FakeSession()
        handler = WebSocketHandler(executor=MockCommandExecutor())
        ws = _FakeWebSocket()

        async def scenario():
            lock = handler._locks.setdefault(str(session.id), asyncio.Lock())
            await lock.acquire()
            try:
                await handler._handle_command(
                    websocket=ws,
                    command="kubectl get pods",
                    session=session,
                    sandbox=_sandbox(),
                    db=_FakeDB(),
                )
            finally:
                lock.release()

        asyncio.run(scenario())
        assert ws.sent[-1]["type"] == "error"
        assert "실행 중" in ws.sent[-1]["message"]


class TestDuplicateConnection:
    def test_new_connection_replaces_previous_with_4000(self):
        session = _FakeSession()
        handler = WebSocketHandler(executor=MockCommandExecutor())
        previous = _FakeWebSocket()
        handler.active_connections[str(session.id)] = previous

        current = _FakeWebSocket()
        asyncio.run(
            handler.handle_connection(
                websocket=current, session=session, sandbox=_sandbox(), db=_FakeDB()
            )
        )

        assert previous.close_code == CLOSE_REPLACED
        # 연결 종료 후 registry 와 lock 이 정리된다
        assert str(session.id) not in handler.active_connections
        assert str(session.id) not in handler._locks
