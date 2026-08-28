import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app
from app.models import TerminalSession
from app.services.sandbox_service import SandboxRef


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, result=None):
        self.result = result
        self.added = []
        self.execute = AsyncMock(side_effect=lambda *args, **kwargs: _Result(self.result))
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    def add(self, value):
        self.added.append(value)

    async def refresh(self, value):
        if value.id is None:
            value.id = uuid.uuid4()
        if value.created_at is None:
            value.created_at = datetime.now(timezone.utc)
        if value.last_activity is None:
            value.last_activity = datetime.now(timezone.utc)
        if value.is_active is None:
            value.is_active = True


class _SandboxService:
    def __init__(self):
        self.ensure = AsyncMock()
        self.cleanup = AsyncMock()

    def reference_for(self, *, user_id, namespace, environment):
        return SandboxRef(
            id="stable-sandbox",
            namespace=namespace,
            pod_name="sandbox-stable-sandbox",
            container_name="toolbox",
            environment=environment,
        )


@pytest.fixture
def terminal_client(monkeypatch):
    user = _FakeUser()
    db = _FakeDb()
    sandbox = _SandboxService()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    import app.api.terminal as terminal_module

    monkeypatch.setattr(terminal_module, "get_sandbox_service", lambda: sandbox)
    transport = httpx.ASGITransport(app=app)
    yield httpx.AsyncClient(transport=transport, base_url="http://test"), user, db, sandbox
    app.dependency_overrides.clear()


class TestTerminalSessionApi:
    @pytest.mark.asyncio
    async def test_creates_kubernetes_session_with_real_environment(self, terminal_client):
        client, user, db, sandbox = terminal_client
        async with client:
            response = await client.post(
                "/api/terminal/sessions", json={"environment": "kubernetes"}
            )

        assert response.status_code == 201
        assert response.json()["environment"] == "kubernetes"
        assert db.added[0].user_id == user.id
        sandbox.ensure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bodyless_legacy_client_defaults_to_kubernetes(self, terminal_client):
        client, _, _, _ = terminal_client
        async with client:
            response = await client.post("/api/terminal/sessions")

        assert response.status_code == 201
        assert response.json()["environment"] == "kubernetes"

    @pytest.mark.asyncio
    async def test_reuses_active_session_in_same_environment(self, terminal_client):
        client, user, db, sandbox = terminal_client
        existing = TerminalSession(
            id=uuid.uuid4(),
            user_id=user.id,
            namespace=f"user-{user.id}",
            environment="kubernetes",
            created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
            is_active=True,
        )
        db.result = existing

        async with client:
            response = await client.post(
                "/api/terminal/sessions", json={"environment": "kubernetes"}
            )

        assert response.status_code == 201
        assert response.json()["id"] == str(existing.id)
        assert db.added == []
        sandbox.ensure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_preparing_environment_returns_concrete_400(self, terminal_client):
        client, _, db, sandbox = terminal_client
        async with client:
            response = await client.post(
                "/api/terminal/sessions", json={"environment": "docker"}
            )

        assert response.status_code == 400
        assert "준비 중" in response.json()["detail"]
        db.execute.assert_not_awaited()
        sandbox.ensure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deletes_owned_active_session_and_sandbox(self, terminal_client):
        client, user, db, sandbox = terminal_client
        existing = TerminalSession(
            id=uuid.uuid4(),
            user_id=user.id,
            namespace=f"user-{user.id}",
            environment="kubernetes",
            is_active=True,
        )
        db.result = existing

        async with client:
            response = await client.delete(
                f"/api/terminal/sessions/{existing.id}"
            )

        assert response.status_code == 204
        assert existing.is_active is False
        sandbox.cleanup.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_unknown_session_returns_404(self, terminal_client):
        client, _, _, sandbox = terminal_client
        async with client:
            response = await client.delete(f"/api/terminal/sessions/{uuid.uuid4()}")

        assert response.status_code == 404
        sandbox.cleanup.assert_not_awaited()
