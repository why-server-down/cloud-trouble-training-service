"""환경별 RuntimeContext 수집 (BE-19).

AI 계층이 환경별로 분기하지 않아도 되도록 **출력 스키마를 고정**한다.
정답이 아니라 관측값만 넘기고, 민감정보는 지운다.
"""
import uuid

import pytest

from app.core import environments
from app.services.runtime_context import RuntimeContextCollector
from app.services.runtime_redaction import redact, redact_text

NS = "user-abc"


class _FakeDB:
    async def execute(self, statement):
        class _R:
            def scalars(self_inner):
                return self_inner

            def all(self_inner):
                return []

            def scalar_one_or_none(self_inner):
                return None

        return _R()


@pytest.fixture
def collector(monkeypatch):
    service = RuntimeContextCollector()

    async def no_commands(user_id, db):
        return []

    monkeypatch.setattr(service, "_collect_recent_commands", no_commands)
    return service


class TestCommonSchema:
    """환경이 달라도 같은 스키마가 나와야 한다."""

    REQUIRED_KEYS = {
        "environment", "scope", "mission",
        "recent_user_commands", "observations", "metrics", "logs", "collection_status",
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("environment", list(environments.SUPPORTED_ENVIRONMENTS))
    async def test_same_keys_for_every_environment(self, collector, monkeypatch, environment):
        async def no_observations(env, namespace, sandbox):
            return {}

        monkeypatch.setattr(collector, "_collect_observations", no_observations)
        context = await collector.collect(
            user_id=uuid.uuid4(), namespace=NS, db=_FakeDB(), environment=environment
        )
        assert self.REQUIRED_KEYS <= set(context)
        assert context["environment"] == environment
        assert context["collection_status"]["state"] == "unavailable"

    @pytest.mark.asyncio
    async def test_scope_carries_namespace_and_sandbox(self, collector, monkeypatch):
        async def no_observations(env, namespace, sandbox):
            return {}

        monkeypatch.setattr(collector, "_collect_observations", no_observations)

        class _Sandbox:
            id = "sb-1"

        context = await collector.collect(
            user_id=uuid.uuid4(), namespace=NS, db=_FakeDB(),
            environment=environments.DOCKER, sandbox=_Sandbox(),
        )
        assert context["scope"] == {"namespace": NS, "sandbox_id": "sb-1"}

    @pytest.mark.asyncio
    async def test_keeps_legacy_keys_for_existing_tutor(self, collector, monkeypatch):
        """AI 소유 경로를 한 PR 에서 못 바꾸므로 기존 키를 함께 남긴다."""
        async def k8s_observations(env, namespace, sandbox):
            return {"kubernetes_state": {"pods": []}}

        monkeypatch.setattr(collector, "_collect_observations", k8s_observations)
        context = await collector.collect(
            user_id=uuid.uuid4(), namespace=NS, db=_FakeDB()
        )
        assert context["namespace"] == NS
        assert context["kubernetes_state"] == {"pods": []}


class TestObserverRegistry:
    def test_every_supported_environment_has_an_observer(self):
        assert set(RuntimeContextCollector._OBSERVERS) == set(
            environments.SUPPORTED_ENVIRONMENTS
        )

    @pytest.mark.asyncio
    async def test_unknown_environment_returns_empty(self, collector):
        result = await collector._collect_observations("application", NS, None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_docker_collects_full_observation_contract(self, collector, monkeypatch):
        class _Service:
            def reference_for(self, **kwargs):
                return type("S", (), {"id": "s1"})()

            def exec_in_sandbox(self, sandbox, argv):
                return "training-app running" if argv[1] == "ps" else "summary"

        monkeypatch.setattr(
            "app.services.sandbox_service.get_sandbox_service", lambda: _Service()
        )
        result = await collector._observe_docker(NS, None)
        assert set(collector._EXPECTED_OBSERVATIONS[environments.DOCKER]) <= set(result)
        assert result["logs"] == "summary"

    @pytest.mark.asyncio
    async def test_linux_declares_every_required_probe(self, collector, monkeypatch):
        class _Service:
            def reference_for(self, **kwargs):
                return type("S", (), {"id": "s1"})()

            def exec_in_sandbox(self, sandbox, argv):
                return "summary"

        monkeypatch.setattr(
            "app.services.sandbox_service.get_sandbox_service", lambda: _Service()
        )
        result = await collector._observe_linux(NS, None)
        assert set(collector._EXPECTED_OBSERVATIONS[environments.LINUX]) == set(result)


class TestPartialFailureIsTolerated:
    @pytest.mark.asyncio
    async def test_observation_failure_does_not_break_context(self, collector, monkeypatch):
        async def boom(env, namespace, sandbox):
            raise RuntimeError("boom")

        monkeypatch.setattr(collector, "_collect_observations", boom)
        context = await collector.collect(
            user_id=uuid.uuid4(), namespace=NS, db=_FakeDB()
        )
        assert context["observations"] == {}
        assert context["environment"] == environments.KUBERNETES

    @pytest.mark.asyncio
    async def test_slow_collection_times_out(self, collector, monkeypatch):
        import asyncio

        async def slow(env, namespace, sandbox):
            await asyncio.sleep(10)

        monkeypatch.setattr(
            collector, "_collect_observations", slow
        )
        monkeypatch.setattr(
            "app.services.runtime_context.settings.RUNTIME_CONTEXT_TIMEOUT_SECONDS", 0.05
        )
        context = await collector.collect(
            user_id=uuid.uuid4(), namespace=NS, db=_FakeDB()
        )
        assert context["observations"] == {}

    @pytest.mark.asyncio
    async def test_one_failed_probe_keeps_the_others(self, collector, monkeypatch):
        class _Service:
            def reference_for(self, **kwargs):
                return type("S", (), {"id": "s1"})()

            def exec_in_sandbox(self, sandbox, argv):
                if "df" in " ".join(argv):
                    raise RuntimeError("boom")
                return "ok"

        monkeypatch.setattr(
            "app.services.sandbox_service.get_sandbox_service", lambda: _Service()
        )
        result = await collector._observe_linux(NS, None)
        assert "disk" not in result
        assert result.get("memory") == "ok"


class TestRedaction:
    """관측값은 그대로 LLM 프로바이더로 나간다. 민감정보를 지워야 한다."""

    @pytest.mark.parametrize(
        "raw",
        [
            "kubectl create secret generic s --from-literal=password=hunter2",
            "Authorization: Bearer abc.def.ghi",
            "TOKEN=abcd1234",
            "api_key: sk-1234567890",
        ],
    )
    def test_sensitive_values_are_removed(self, raw):
        cleaned = redact_text(raw)
        assert "***REDACTED***" in cleaned
        for leak in ("hunter2", "abc.def.ghi", "abcd1234", "sk-1234567890"):
            assert leak not in cleaned

    def test_normal_commands_are_untouched(self):
        assert redact_text("kubectl get pods") == "kubectl get pods"
        assert redact_text("docker ps -a") == "docker ps -a"

    def test_environment_variables_are_dropped_entirely(self):
        """계획서가 전체 환경변수를 redaction 대상으로 지목했다."""
        result = redact({"env": {"DB_PASSWORD": "x", "PATH": "/usr/bin"}})
        assert result["env"] == "***REDACTED***"

    def test_nested_structures_are_walked(self):
        result = redact({"a": [{"cmd": "TOKEN=secret123"}]})
        assert "secret123" not in str(result)

    @pytest.mark.asyncio
    async def test_context_is_redacted_before_return(self, collector, monkeypatch):
        async def leaky(env, namespace, sandbox):
            return {"note": "password=hunter2"}

        monkeypatch.setattr(collector, "_collect_observations", leaky)
        context = await collector.collect(
            user_id=uuid.uuid4(), namespace=NS, db=_FakeDB()
        )
        assert "hunter2" not in str(context)


class TestSandboxTargetIsServerResolved:
    @pytest.mark.asyncio
    async def test_reference_is_restored_from_namespace(self, collector, monkeypatch):
        """클라이언트가 보낸 값이 아니라 서버가 DB 세션에서 만든 참조를 쓴다."""
        seen = {}

        class _Service:
            def reference_for(self, **kwargs):
                seen.update(kwargs)
                return type("S", (), {"id": "s1"})()

            def exec_in_sandbox(self, sandbox, argv):
                return ""

        monkeypatch.setattr(
            "app.services.sandbox_service.get_sandbox_service", lambda: _Service()
        )
        await collector._observe_docker("user-42", None)
        assert seen["namespace"] == "user-42"
        assert seen["environment"] == environments.DOCKER
