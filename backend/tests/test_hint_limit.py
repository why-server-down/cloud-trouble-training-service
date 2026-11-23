"""힌트 상한 (FE-31 후속).

힌트는 튜터 답의 구체성 단계라 3단계가 끝이다. 예전에는 그 뒤로도 살 수 있어 튜터는 그대로인데
점수만 깎였다. 두 경로(정적 미션, AI 시나리오) 모두 3번째 구매까지만 받는다.
"""
import uuid

import pytest

from app.services.mission_service import MissionService
from app.services.scenario_service import ScenarioService
from app.services.scoring_service import HINT_LIMIT_MESSAGE, MAX_HINT_LEVEL, ScoringService


class _Attempt:
    def __init__(self, hints_used, attempt_type="static_mission"):
        self.id = uuid.uuid4()
        self.status = "in_progress"
        self.attempt_type = attempt_type
        self.hints_used = hints_used


class _Result:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _DB:
    def __init__(self, attempt):
        self.attempt = attempt
        self.commits = 0

    async def execute(self, _statement):
        return _Result(self.attempt)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _row):
        pass


def _mission_service():
    return MissionService(injector_for=None, validation_for=None, scoring_service=ScoringService())


@pytest.mark.asyncio
async def test_mission_hint_stops_at_max_level():
    attempt = _Attempt(MAX_HINT_LEVEL - 1)
    db = _DB(attempt)
    service = _mission_service()

    await service.use_hint(db, attempt.id)
    assert attempt.hints_used == MAX_HINT_LEVEL

    with pytest.raises(ValueError, match=HINT_LIMIT_MESSAGE):
        await service.use_hint(db, attempt.id)
    assert attempt.hints_used == MAX_HINT_LEVEL
    assert db.commits == 1


@pytest.mark.asyncio
async def test_scenario_hint_stops_at_max_level():
    attempt = _Attempt(MAX_HINT_LEVEL, attempt_type="ai_scenario")
    db = _DB(attempt)
    service = ScenarioService(injector_for=None, scoring_service=ScoringService(), validation_rule_service=None)

    async def active(_db, _user_id):
        return attempt

    service._get_active_attempt = active

    with pytest.raises(ValueError, match=HINT_LIMIT_MESSAGE):
        await service.use_hint(db, uuid.uuid4())
    assert attempt.hints_used == MAX_HINT_LEVEL
    assert db.commits == 0
