"""미션 목록·잠금·시드가 환경별로 분리되는지 검증 (BE-09).

환경을 섞으면 Kubernetes level 4 를 깬 사용자가 Docker level 2 를 건너뛰고
시작할 수 있다.
"""
import uuid

import pytest

from app.core import environments
from app.services.mission_service import MissionService
from app.services.validation_service import MockValidationService


class _FakeMission:
    def __init__(self, level: int, environment: str):
        self.id = uuid.uuid4()
        self.name = f"{environment} L{level}"
        self.level = level
        self.description = "d"
        self.chaos_type = "pod_failure"
        self.environment = environment
        self.base_score = 100
        self.time_limit = 600
        self.hint_penalty = 5


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _CapturingDB:
    """실행된 SQL 을 기록하고 미리 정한 결과를 돌려준다."""

    def __init__(self, missions, completed_levels):
        self.missions = missions
        self.completed_levels = completed_levels
        self.sql = []

    async def execute(self, statement):
        rendered = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.sql.append(rendered)
        # 완료 레벨 조회는 mission_attempts 를 join 한다
        if "mission_attempts" in rendered:
            return _Result(list(self.completed_levels))
        return _Result(list(self.missions))


def _service():
    return MissionService(
        injector_for=lambda env: None,
        validation_for=lambda env: MockValidationService(environment=env),
        scoring_service=object(),
    )


class _User:
    id = uuid.uuid4()


class TestListMissionsIsScopedToEnvironment:
    @pytest.mark.asyncio
    async def test_query_filters_by_environment(self):
        db = _CapturingDB([_FakeMission(1, "docker")], [])
        await _service().list_missions(db, _User(), "docker")

        assert all("environment" in sql for sql in db.sql), (
            "미션 조회와 완료 레벨 조회 모두 environment 로 걸러야 한다"
        )
        assert any("'docker'" in sql for sql in db.sql)

    @pytest.mark.asyncio
    async def test_completed_levels_query_is_scoped(self):
        db = _CapturingDB([_FakeMission(2, "docker")], [])
        await _service().list_missions(db, _User(), "docker")

        attempt_sql = [s for s in db.sql if "mission_attempts" in s]
        assert attempt_sql, "완료 레벨을 조회해야 한다"
        assert "'docker'" in attempt_sql[0], (
            "다른 환경의 완료 기록이 잠금 해제에 쓰이면 안 된다"
        )


class TestUnlockDoesNotLeakAcrossEnvironments:
    @pytest.mark.asyncio
    async def test_level_1_is_always_unlocked(self):
        db = _CapturingDB([_FakeMission(1, "docker")], [])
        result = await _service().list_missions(db, _User(), "docker")
        assert result[0]["is_unlocked"] is True

    @pytest.mark.asyncio
    async def test_level_2_locked_without_same_environment_completion(self):
        """Kubernetes level 1 을 깼어도 Docker level 2 는 잠겨 있어야 한다.

        완료 레벨 조회가 environment 로 걸러지므로 다른 환경 기록은 결과에 없다.
        """
        db = _CapturingDB([_FakeMission(2, "docker")], [])  # docker 완료 기록 없음
        result = await _service().list_missions(db, _User(), "docker")
        assert result[0]["is_unlocked"] is False

    @pytest.mark.asyncio
    async def test_level_2_unlocked_with_same_environment_completion(self):
        db = _CapturingDB([_FakeMission(2, "docker")], [1])  # docker level 1 완료
        result = await _service().list_missions(db, _User(), "docker")
        assert result[0]["is_unlocked"] is True


class TestSeedUsesStableKey:
    def test_every_seed_declares_environment(self):
        from app.services.seed_data import MISSIONS

        assert all("environment" in m for m in MISSIONS)
        assert all(
            environments.is_supported(m["environment"]) for m in MISSIONS
        )

    def test_seed_key_is_unique(self):
        """(environment, level) 이 stable key 이므로 시드 안에서 중복이 없어야 한다."""
        from app.services.seed_data import MISSIONS

        keys = [(m["environment"], m["level"]) for m in MISSIONS]
        assert len(keys) == len(set(keys))

    def test_kubernetes_seed_is_preserved(self):
        """기존 Kubernetes 미션 4개는 그대로 유지한다."""
        from app.services.seed_data import MISSIONS

        k8s = [m for m in MISSIONS if m["environment"] == environments.KUBERNETES]
        assert sorted(m["level"] for m in k8s) == [1, 2, 3, 4]
        assert [m["chaos_type"] for m in sorted(k8s, key=lambda m: m["level"])] == [
            "pod_failure",
            "memory_stress",
            "service_misconfig",
            "network_latency",
        ]


class TestMissionModelConstraint:
    def test_unique_constraint_exists(self):
        from app.models import Mission

        names = {
            getattr(arg, "name", None) for arg in Mission.__table_args__
        }
        assert "uq_missions_environment_level" in names
