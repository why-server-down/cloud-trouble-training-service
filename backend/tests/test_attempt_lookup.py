"""끝난 시도 조회 API (BE-30).

시간 초과로 정리된 시도는 `/api/missions/status` 가 404 를 주므로 결과 화면이
서버 점수를 볼 수 없었다. attempt id 로 내 시도를 직접 읽는다.

가짜 DB 는 쿼리의 WHERE 조건을 그대로 적용한다. 그래서 라우터가 user_id 조건을
빠뜨리면 남의 시도가 실제로 새어 나가고 테스트가 잡는다.
"""
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app


class _User:
    def __init__(self):
        self.id = uuid.uuid4()


class _Attempt:
    def __init__(self, user_id, *, attempt_type="static_mission", **fields):
        start = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
        self.id = uuid.uuid4()
        self.user_id = user_id
        self.attempt_type = attempt_type
        self.mission_id = uuid.uuid4() if attempt_type == "static_mission" else None
        self.scenario_id = uuid.uuid4() if attempt_type == "ai_scenario" else None
        self.environment = "kubernetes"
        self.status = "failed"
        self.start_time = start
        self.end_time = start + timedelta(minutes=10)
        self.final_score = 10
        self.hints_used = 2
        self.__dict__.update(fields)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        assert len(self._rows) <= 1
        return self._rows[0] if self._rows else None


class _WhereDB:
    """`select(...).where(col == value, ...)` 의 조건만 적용하는 가짜 세션."""

    def __init__(self, rows):
        self.rows = rows
        self.writes = 0

    async def execute(self, statement):
        criteria = [(c.left.key, c.right.value) for c in statement._where_criteria]
        assert criteria, "조건 없는 조회는 남의 시도를 읽는다"
        return _Result(
            [r for r in self.rows if all(getattr(r, k) == v for k, v in criteria)]
        )

    async def commit(self):
        self.writes += 1

    def add(self, obj):
        self.writes += 1


@pytest.fixture
def me():
    return _User()


@pytest.fixture
def db():
    return _WhereDB([])


@pytest.fixture
def client(me, db):
    app.dependency_overrides[get_current_user] = lambda: me
    app.dependency_overrides[get_db] = lambda: db
    transport = httpx.ASGITransport(app=app)
    yield httpx.AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


class TestGetAttempt:
    @pytest.mark.asyncio
    async def test_timed_out_static_attempt_returns_outcome(self, client, me, db):
        attempt = _Attempt(me.id, status="failed", final_score=10, hints_used=2)
        db.rows.append(attempt)

        async with client:
            response = await client.get(f"/api/attempts/{attempt.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(attempt.id)
        assert body["status"] == "failed"
        assert body["final_score"] == 10
        assert body["hints_used"] == 2
        assert body["attempt_type"] == "static_mission"
        assert datetime.fromisoformat(body["start_time"]) == attempt.start_time
        assert datetime.fromisoformat(body["end_time"]) == attempt.end_time
        # 조회만 한다
        assert db.writes == 0

    @pytest.mark.asyncio
    async def test_ai_scenario_attempt_is_readable(self, client, me, db):
        attempt = _Attempt(
            me.id, attempt_type="ai_scenario", status="completed", final_score=85
        )
        db.rows.append(attempt)

        async with client:
            body = (await client.get(f"/api/attempts/{attempt.id}")).json()

        assert body["attempt_type"] == "ai_scenario"
        assert body["scenario_id"] == str(attempt.scenario_id)
        assert body["mission_id"] is None
        assert body["final_score"] == 85

    @pytest.mark.asyncio
    async def test_other_users_attempt_is_404(self, client, me, db):
        other = _Attempt(uuid.uuid4(), status="completed", final_score=100)
        db.rows.append(other)

        async with client:
            response = await client.get(f"/api/attempts/{other.id}")

        assert response.status_code == 404
        assert "final_score" not in response.text

    @pytest.mark.asyncio
    async def test_unknown_id_is_404(self, client):
        async with client:
            response = await client.get(f"/api/attempts/{uuid.uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_malformed_id_is_422(self, client):
        async with client:
            response = await client.get("/api/attempts/not-a-uuid")
        assert response.status_code == 422
