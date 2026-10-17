"""AI 모드 잠금 해제는 이 배포에서 열린 환경의 미션만 센다 (BE-31).

docker 를 닫은 배포에서 Docker 미션까지 세면 아무도 AI 모드를 열 수 없다.
"""
import uuid

import pytest

from app.core import environments
from app.core.config import settings
from app.services.scenario_service import ScenarioService
from app.services.seed_data import MISSIONS


class _Mission:
    def __init__(self, seed):
        self.id = uuid.uuid4()
        self.environment = seed["environment"]
        self.level = seed["level"]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    """미션 조회에는 쿼리의 environment 조건을 그대로 적용한다."""

    def __init__(self, missions, completed_ids):
        self.missions = missions
        self.completed_ids = completed_ids

    async def execute(self, statement):
        if "mission_attempts" in str(statement):
            return _Result(list(self.completed_ids))
        (criterion,) = statement._where_criteria  # 조건이 없으면 여기서 실패
        allowed = criterion.right.value
        return _Result([m for m in self.missions if m.environment in allowed])


def _service():
    return ScenarioService(
        injector_for=lambda env: None,
        scoring_service=object(),
        validation_rule_service=object(),
    )


@pytest.fixture
def missions():
    return [_Mission(seed) for seed in MISSIONS]


@pytest.fixture
def docker_closed(monkeypatch):
    monkeypatch.setattr(environments, "ENABLED_ENVIRONMENTS", ("kubernetes", "linux"))
    monkeypatch.setattr(settings, "DEMO_UNLOCK_AI_SCENARIOS", False)


def _ids(missions, *envs):
    return {m.id for m in missions if m.environment in envs}


class TestUnlockCountsOnlyEnabledEnvironments:
    @pytest.mark.asyncio
    async def test_total_excludes_closed_environment(self, docker_closed, missions):
        # Docker 미션만 깬 기록은 세지 않는다
        db = _DB(missions, _ids(missions, "docker"))
        status = await _service().check_unlock_status(db, uuid.uuid4())

        enabled = len(_ids(missions, "kubernetes", "linux"))
        assert enabled < len(missions)
        assert status == {"unlocked": False, "completed_static": 0, "total_static": enabled}

    @pytest.mark.asyncio
    async def test_completing_every_enabled_mission_unlocks(self, docker_closed, missions):
        db = _DB(missions, _ids(missions, "kubernetes", "linux"))
        status = await _service().check_unlock_status(db, uuid.uuid4())

        assert status["unlocked"] is True
        assert status["completed_static"] == status["total_static"]

    @pytest.mark.asyncio
    async def test_demo_unlock_still_opens(self, docker_closed, missions, monkeypatch):
        monkeypatch.setattr(settings, "DEMO_UNLOCK_AI_SCENARIOS", True)
        status = await _service().check_unlock_status(_DB(missions, set()), uuid.uuid4())
        assert status["unlocked"] is True
