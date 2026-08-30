"""환경별 분석 (BE-21).

인수 조건
  - 환경별 집계와 all 합계가 일치한다
  - abandoned/failed 를 completed MTTR 에 포함하지 않는다
  - 동일 AI scenario attempt 가 mission_id None key 로 모두 합쳐지지 않는다
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core import environments
from app.core.config import settings
from app.services.analytics_service import AnalyticsService


class _Attempt:
    def __init__(
        self,
        environment=environments.KUBERNETES,
        *,
        score=100,
        seconds=600,
        hints=0,
        attempt_type="static_mission",
        mission_id=None,
        scenario_id=None,
        status="completed",
    ):
        self.id = uuid.uuid4()
        self.environment = environment
        self.final_score = score
        self.hints_used = hints
        self.attempt_type = attempt_type
        self.mission_id = mission_id
        self.scenario_id = scenario_id
        self.status = status
        self.start_time = datetime.now(timezone.utc)
        self.end_time = self.start_time + timedelta(seconds=seconds)
        self.mission = None


@pytest.fixture
def service():
    return AnalyticsService()


class TestCurveKeySeparatesAiScenarios:
    """AI 시나리오는 mission_id 가 전부 None 이다.

    그 값을 키로 쓰면 서로 다른 시나리오가 같은 과제를 반복한 것처럼 집계된다.
    """

    def test_different_scenarios_get_different_keys(self, service):
        a = _Attempt(attempt_type="ai_scenario", scenario_id=uuid.uuid4())
        b = _Attempt(attempt_type="ai_scenario", scenario_id=uuid.uuid4())
        assert service._curve_key(a) != service._curve_key(b)

    def test_same_scenario_shares_a_key(self, service):
        scenario_id = uuid.uuid4()
        a = _Attempt(attempt_type="ai_scenario", scenario_id=scenario_id)
        b = _Attempt(attempt_type="ai_scenario", scenario_id=scenario_id)
        assert service._curve_key(a) == service._curve_key(b)

    def test_static_missions_still_group_by_mission(self, service):
        mission_id = uuid.uuid4()
        a = _Attempt(mission_id=mission_id)
        b = _Attempt(mission_id=mission_id)
        assert service._curve_key(a) == service._curve_key(b)

    def test_mission_and_scenario_keys_do_not_collide(self, service):
        shared = uuid.uuid4()
        mission = _Attempt(mission_id=shared)
        scenario = _Attempt(attempt_type="ai_scenario", scenario_id=shared)
        assert service._curve_key(mission) != service._curve_key(scenario)


class TestEnvironmentStats:
    def test_empty_environment_reports_null_competency(self, service):
        """시도가 없는 것과 해봤는데 못한 것을 구분할 수 있어야 한다."""
        stats = service._environment_stats([])
        assert stats["completed"] == 0
        assert stats["competency"] is None

    def test_aggregates_average_score_and_mttr(self, service):
        stats = service._environment_stats(
            [_Attempt(score=80, seconds=300), _Attempt(score=100, seconds=900)]
        )
        assert stats["completed"] == 2
        assert stats["average_score"] == 90
        assert stats["average_mttr"] == 600

    def test_hints_are_summed(self, service):
        stats = service._environment_stats([_Attempt(hints=2), _Attempt(hints=3)])
        assert stats["hints_used"] == 5


class TestCompetency:
    def test_perfect_run_scores_high(self, service):
        """만점·즉시 복구·힌트 없음이면 100 에 가까워야 한다."""
        assert service._competency(100, 0, 0) == 100

    def test_slow_recovery_lowers_score(self, service):
        fast = service._competency(100, 0, 0)
        slow = service._competency(100, settings.TARGET_MTTR_SECONDS * 2, 0)
        assert slow < fast

    def test_hints_lower_score(self, service):
        assert service._competency(100, 0, 3) < service._competency(100, 0, 0)

    def test_components_are_clamped(self, service):
        """아주 느려도 음수가 되지 않는다."""
        value = service._competency(0, settings.TARGET_MTTR_SECONDS * 100, 100)
        assert 0 <= value <= 100


class TestAggregationConsistency:
    """환경별 집계와 all 합계가 어긋나면 대시보드가 서로 다른 숫자를 보여준다."""

    def test_completed_counts_add_up(self, service):
        attempts = [
            _Attempt(environments.KUBERNETES),
            _Attempt(environments.KUBERNETES),
            _Attempt(environments.DOCKER),
            _Attempt(environments.LINUX),
        ]
        per_env = {
            env: service._environment_stats([a for a in attempts if a.environment == env])
            for env in environments.SUPPORTED_ENVIRONMENTS
        }
        assert sum(s["completed"] for s in per_env.values()) == len(attempts)

    def test_hints_add_up(self, service):
        attempts = [
            _Attempt(environments.KUBERNETES, hints=1),
            _Attempt(environments.DOCKER, hints=2),
            _Attempt(environments.LINUX, hints=3),
        ]
        per_env = {
            env: service._environment_stats([a for a in attempts if a.environment == env])
            for env in environments.SUPPORTED_ENVIRONMENTS
        }
        assert sum(s["hints_used"] for s in per_env.values()) == 6


class TestOnlyCompletedAttemptsCount:
    def test_query_filters_status_and_environment(self, service):
        """abandoned/failed 를 MTTR 에 넣으면 시간 지표가 복구 능력을 나타내지 못한다."""
        import inspect

        source = inspect.getsource(service._completed_attempts)
        assert 'MissionAttempt.status == "completed"' in source
        assert "MissionAttempt.environment == environment" in source


class TestApiContract:
    def test_stats_endpoint_accepts_all_and_each_environment(self):
        from app.api.dashboard import EnvironmentFilter
        from typing import get_args

        allowed = set(get_args(EnvironmentFilter))
        assert "all" in allowed
        assert set(environments.SUPPORTED_ENVIRONMENTS) <= allowed

    def test_all_resolves_to_no_filter(self):
        from app.api.dashboard import _resolve

        assert _resolve("all") is None
        assert _resolve("docker") == "docker"
