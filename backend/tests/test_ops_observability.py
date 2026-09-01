"""운영 설정과 관측 (BE-23).

인수 조건
  - 운영 모드에서 wildcard CORS 가 아니다
  - metrics label 에 user ID, namespace, command, scenario title 이 없다
  - health 와 readiness 를 구분하고 의존 상태를 노출한다
  - 한도를 넘긴 chat 요청이 429 로 거절되고 정상 요청은 영향받지 않는다
  - AI 호출 메트릭 label 에 프롬프트·응답 본문이 들어가지 않는다
"""
import ast
import pathlib

import pytest

from app.core import metrics
from app.core.config import settings
from app.core.rate_limit import RateLimiter

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"


class TestCorsIsNotWildcard:
    def test_origins_come_from_settings(self):
        assert "*" not in settings.cors_origin_list

    def test_wildcard_is_not_hardcoded(self):
        source = (APP_DIR / "main.py").read_text()
        assert 'allow_origins=["*"]' not in source

    def test_list_is_parsed_from_comma_separated_value(self):
        from app.core.config import Settings

        parsed = Settings(CORS_ORIGINS="https://a.io, https://b.io ,").cors_origin_list
        assert parsed == ["https://a.io", "https://b.io"]


class TestMetricLabelsAreLowCardinality:
    """label 에 사용자 값이 들어가면 시계열이 무한히 늘고 민감정보가 남는다."""

    FORBIDDEN = {"user", "user_id", "namespace", "command", "title", "scenario", "pod"}

    def test_no_high_cardinality_labels(self):
        for name in dir(metrics):
            metric = getattr(metrics, name)
            labels = getattr(metric, "_labelnames", None)
            if not labels:
                continue
            for label in labels:
                assert label not in self.FORBIDDEN, f"{name} 의 label '{label}'"

    def test_command_category_reduces_user_input(self):
        assert metrics.command_category(["kubectl", "get", "pods", "-n", "user-abc"]) == (
            "kubectl:get"
        )
        assert metrics.command_category(["docker", "ps", "-a"]) == "docker:ps"

    def test_command_category_handles_empty(self):
        assert metrics.command_category([]) == "unknown"

    def test_ai_metrics_do_not_label_content(self):
        """프롬프트·응답 본문이 label 에 들어가면 그대로 저장된다."""
        for metric in (metrics.AI_CALLS, metrics.AI_CALL_DURATION, metrics.AI_TOKENS):
            for label in metric._labelnames:
                assert label in {"provider", "purpose", "result", "kind"}

    def test_required_metrics_exist(self):
        for name in (
            "SANDBOX_PROVISION", "COMMAND_EXECUTIONS", "CHAOS_OPERATIONS",
            "VALIDATION_CHECKS", "AI_CALLS", "ACTIVE_SESSIONS",
            "ACTIVE_ATTEMPTS", "CLEANUP_FAILURES",
        ):
            assert hasattr(metrics, name)


class TestRateLimit:
    def test_allows_up_to_the_limit(self):
        limiter = RateLimiter(limit=3)
        assert all(limiter.check("u1") is None for _ in range(3))

    def test_rejects_beyond_the_limit(self):
        limiter = RateLimiter(limit=2)
        limiter.check("u1")
        limiter.check("u1")
        retry_after = limiter.check("u1")
        assert retry_after is not None and retry_after > 0

    def test_users_are_counted_separately(self):
        """한 사용자의 과다 호출이 다른 사용자를 막으면 안 된다."""
        limiter = RateLimiter(limit=1)
        limiter.check("u1")
        assert limiter.check("u1") is not None
        assert limiter.check("u2") is None

    def test_window_expiry_frees_the_slot(self):
        limiter = RateLimiter(limit=1, window_seconds=0)
        limiter.check("u1")
        assert limiter.check("u1") is None

    def test_zero_limit_disables_the_check(self):
        limiter = RateLimiter(limit=0)
        assert all(limiter.check("u1") is None for _ in range(10))

    def test_chat_endpoint_applies_the_limit(self):
        source = (APP_DIR / "api" / "chat.py").read_text()
        assert "RateLimiter" in source
        assert "429" in source or "TOO_MANY_REQUESTS" in source
        # 언제 다시 시도할 수 있는지 알려야 프론트가 표시할 수 있다
        assert "Retry-After" in source


class TestHealthAndReadinessAreSeparate:
    @pytest.mark.asyncio
    async def test_health_does_not_check_dependencies(self):
        """의존 상태를 여기서 보면 DB 가 흔들릴 때 살아 있는 프로세스가 죽는다."""
        import inspect

        from app.main import health_check

        source = inspect.getsource(health_check)
        for dependency in ("engine", "kubernetes", "qdrant"):
            assert dependency not in source.split('"""')[-1]

    @pytest.mark.asyncio
    async def test_readiness_reports_each_dependency(self):
        import httpx

        from app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            response = await client.get("/ready")

        body = response.json()
        assert set(body["checks"]) == {"database", "kubernetes", "qdrant"}
        for state in body["checks"].values():
            assert "ok" in state and "required" in state

    def test_optional_dependencies_are_marked_in_mock_mode(self):
        """mock 백엔드에서는 K8s·Qdrant 없이도 준비된 것으로 본다."""
        import inspect

        from app.main import _check_kubernetes, _check_qdrant

        assert 'TERMINAL_BACKEND != "mock"' in inspect.getsource(_check_kubernetes)
        assert 'AI_BACKEND != "mock"' in inspect.getsource(_check_qdrant)


class TestNoPrintDebugging:
    """운영 로그가 print 로 섞이면 레벨·구조화 필터가 통하지 않는다."""

    def test_backend_owned_code_has_no_print(self):
        offenders = []
        for path in APP_DIR.rglob("*.py"):
            # app/ai/ 는 AI 담당 소유 경로다
            if "ai" in path.relative_to(APP_DIR).parts[:1]:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
                    offenders.append(f"{path.name}:{node.lineno}")
        assert offenders == []
