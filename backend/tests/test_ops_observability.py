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
from app.main import app

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

    def test_localhost_and_loopback_ip_are_both_allowed_by_default(self):
        """브라우저는 localhost 와 127.0.0.1 을 다른 origin 으로 본다.

        기본값에 한쪽만 있으면 같은 .env 로 한쪽만 동작한다(2026-09-02 프론트 보고).
        """
        origins = settings.cors_origin_list
        assert any("localhost:3000" in origin for origin in origins)
        assert any("127.0.0.1:3000" in origin for origin in origins)

    def test_retry_after_is_exposed_to_the_browser(self):
        """allow_headers 는 **요청** 헤더용이다.

        Retry-After 는 CORS-safelisted 응답 헤더가 아니므로 expose_headers 에
        넣지 않으면 cross-origin 호출에서 JS 가 null 로 읽는다. 429 를 받고도
        언제 다시 시도할지 화면에 띄울 수 없다.
        """
        cors = [
            middleware for middleware in app.user_middleware
            if middleware.cls.__name__ == "CORSMiddleware"
        ]
        assert cors, "CORSMiddleware 가 등록돼 있지 않다"
        assert "Retry-After" in cors[0].kwargs["expose_headers"]

    def test_rate_limited_response_carries_retry_after(self):
        """429 를 내는 쪽과 노출하는 쪽이 함께 있어야 의미가 있다."""
        source = (APP_DIR / "api" / "chat.py").read_text()
        assert "Retry-After" in source


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


class TestImagesAreImmutable(object):
    """움직이는 태그를 쓰면 같은 미션이 다른 이미지 위에서 돈다 (BE-25).

    `:latest` 는 그 위에 imagePullPolicy 기본값이 Always 라, 네임스페이스를 만들
    때마다 레지스트리를 다시 다녀온다. 배포 환경에서는 digest 로 고정한다
    (.env.example 의 배포 섹션).
    """

    IMAGE_SETTINGS = (
        "SANDBOX_TOOLBOX_IMAGE",
        "SANDBOX_DIND_IMAGE",
        "SANDBOX_LINUX_IMAGE",
        "SANDBOX_TRAINING_IMAGE",
        "TRAINING_K8S_IMAGE",
    )

    @pytest.mark.parametrize("name", IMAGE_SETTINGS)
    def test_no_floating_latest_tag(self, name):
        value = getattr(settings, name)
        assert value, f"{name} 이 비어 있다"
        assert not value.endswith(":latest"), f"{name} 이 움직이는 태그다: {value}"
        assert ":" in value or "@" in value, f"{name} 에 태그가 없다(=latest): {value}"

    def test_no_image_is_hardcoded_in_the_cluster_setup(self):
        """설정을 우회해 코드에 이미지를 박으면 배포에서 고정할 수 없다."""
        source = (APP_DIR / "services" / "k8s_setup.py").read_text()
        assert "nginx:latest" not in source
        assert "settings.TRAINING_K8S_IMAGE" in source

    def test_training_workload_does_not_repull_every_time(self):
        source = (APP_DIR / "services" / "k8s_setup.py").read_text()
        assert 'image_pull_policy="IfNotPresent"' in source


class TestDeploymentManifestsAreLocked(object):
    """배포 매니페스트의 보안 성질을 텍스트 수준에서 고정한다 (BE-25).

    매니페스트는 백엔드 테스트가 아니지만, 여기서 막지 않으면 되돌아가도 아무도
    모른다. 실제 클러스터 검증 결과는 infra/k8s/README.md 에 기록돼 있다.
    """

    MANIFESTS = pathlib.Path(__file__).resolve().parents[2] / "infra" / "k8s"

    def _read(self, name: str) -> str:
        path = self.MANIFESTS / name
        assert path.exists(), f"{path} 가 없다"
        return path.read_text()

    def test_backend_rbac_has_no_wildcards(self):
        """`*` 하나가 최소 권한을 전부 무의미하게 만든다."""
        rbac = self._read("base/rbac.yaml")
        for line in rbac.splitlines():
            stripped = line.strip()
            if stripped.startswith(("apiGroups:", "resources:", "verbs:")):
                assert '"*"' not in stripped, f"와일드카드: {stripped}"

    def test_backend_rbac_does_not_grant_escalation(self):
        """escalate/bind 가 있으면 스스로 권한을 넓힐 수 있다."""
        rbac = self._read("base/rbac.yaml")
        for verb in ("escalate", "bind", "impersonate"):
            assert f'"{verb}"' not in rbac

    def test_secret_values_are_not_committed(self):
        """커밋된 비밀은 지워도 히스토리에 남는다."""
        template = self._read("base/secret.template.yaml")
        assert "<배포 시점" in template
        # 주석으로 언급하는 것은 괜찮다. `resources:` 목록에 없어야 한다.
        resources = [
            line.strip().lstrip("- ")
            for line in self._read("base/kustomization.yaml").splitlines()
            if line.strip().startswith("- ")
        ]
        assert "secret.template.yaml" not in resources

    def test_app_namespace_enforces_restricted_pod_security(self):
        namespace = self._read("base/namespace.yaml")
        assert "pod-security.kubernetes.io/enforce: restricted" in namespace

    def test_workloads_run_unprivileged(self):
        for name in ("base/backend.yaml", "base/migration-job.yaml"):
            manifest = self._read(name)
            assert "runAsNonRoot: true" in manifest, name
            assert "allowPrivilegeEscalation: false" in manifest, name
            assert 'drop: ["ALL"]' in manifest, name
            assert "privileged: true" not in manifest, name

    def test_deployment_does_not_create_schema_on_startup(self):
        """스키마의 단일 출처는 Alembic 이다. 배포에서 create_all 을 쓰지 않는다."""
        assert 'AUTO_CREATE_SCHEMA: "false"' in self._read("base/config.yaml")

    def test_admission_policy_scopes_the_backend_to_training_namespaces(self):
        """ClusterRole 로는 좁힐 수 없는 부분을 admission 이 막는다."""
        policy = self._read("base/admission-policy.yaml")
        assert "ValidatingAdmissionPolicy" in policy
        assert "request.namespace.startsWith('user-')" in policy
        assert "validationActions: [Deny]" in policy


class TestMetricsEndpointIsScrapable(object):
    """수집기가 `/metrics` 를 그대로 긁을 수 있어야 한다 (BE-25).

    mount 로 붙였을 때는 정확히 `/metrics` 로 온 요청이 `/metrics/` 로 307
    리다이렉트됐다(실측 2026-09-02). Prometheus 는 따라가지만 Location 이 절대
    URL 이라 TLS 종료 프록시 뒤에서 http 로 내려가고, 그것을 거부하는 수집기도 있다.
    """

    @pytest.mark.asyncio
    async def test_exact_path_answers_without_a_redirect(self):
        import httpx

        from app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "# HELP" in response.text
