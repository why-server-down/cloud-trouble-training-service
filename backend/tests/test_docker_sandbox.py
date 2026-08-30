"""Docker(DinD) 샌드박스 프로비저닝 (BE-11).

privileged 를 쓰는 대신 격리를 좁힌 부분이 지켜지는지 고정한다.
rootless 가 왜 불가능했는지는 sandbox_service._ensure_dind_pod docstring 참고.
"""
import pytest

from app.core import environments
from app.core.config import settings
from app.services.sandbox_service import SandboxRef, SandboxService


class _FakeApiException(Exception):
    def __init__(self, status=404):
        self.status = status


class _FakeCoreApi:
    def __init__(self, existing_pods=()):
        self.existing = set(existing_pods)
        self.created = []

    def read_namespaced_pod(self, name, namespace):
        if name not in self.existing:
            from kubernetes.client.exceptions import ApiException

            raise ApiException(status=404)
        return object()

    def create_namespaced_pod(self, namespace, body):
        self.created.append(body)
        self.existing.add(body.metadata.name)


def _service(core_api):
    return SandboxService(
        core_api=core_api, rbac_api=object(), networking_api=object(), k8s_setup=object()
    )


class TestProvisionerRegistry:
    def test_registered_provisioners_are_supported_environments(self):
        """프로비저너는 계약에 있는 환경에만 등록된다."""
        assert set(SandboxService._PROVISIONERS) <= set(
            environments.SUPPORTED_ENVIRONMENTS
        )
        assert environments.DOCKER in SandboxService._PROVISIONERS

    def test_every_provisioner_has_a_container_name(self):
        """참조 복원 시 컨테이너 이름이 환경마다 달라야 한다.

        고정값을 쓰면 "container toolbox is not valid for pod ..." 로 exec 이 실패한다.
        """
        for environment in SandboxService._PROVISIONERS:
            assert SandboxService.container_name_for(environment)
        names = {
            SandboxService.container_name_for(env)
            for env in SandboxService._PROVISIONERS
        }
        assert len(names) == len(SandboxService._PROVISIONERS), "환경마다 이름이 달라야 한다"

    @pytest.mark.asyncio
    async def test_unregistered_environment_is_rejected(self):
        service = _service(_FakeCoreApi())
        with pytest.raises(ValueError):
            await service.ensure(
                user_id="u1", namespace="user-u1", environment="application"
            )


class TestDindPodSpec:
    def _pod(self):
        api = _FakeCoreApi()
        service = _service(api)
        container = service._provision_docker("user-1", "sandbox-1", {})
        assert container == SandboxService.DIND_CONTAINER
        return api.created[0]

    def test_uses_privileged_because_rootless_does_not_start(self):
        """rootless 가 클러스터에서 기동하지 않아 privileged 를 쓴다(BE-11 실측)."""
        container = self._pod().spec.containers[0]
        assert container.security_context.privileged is True

    def test_does_not_mount_service_account_token(self):
        """Docker 환경은 Kubernetes API 를 쓰지 않는다. 접근 경로 자체를 없앤다."""
        assert self._pod().spec.automount_service_account_token is False

    def test_has_resource_limits_including_storage(self):
        limits = self._pod().spec.containers[0].resources.limits
        assert limits["cpu"] == settings.SANDBOX_DIND_CPU_LIMIT
        assert limits["memory"] == settings.SANDBOX_DIND_MEMORY_LIMIT
        # 디스크를 채우는 훈련이 노드를 위협하면 안 된다
        assert limits["ephemeral-storage"] == settings.SANDBOX_DIND_STORAGE_LIMIT

    def test_daemon_is_not_exposed_over_tls_port(self):
        """유닉스 소켓만 쓴다. 데몬을 네트워크에 열지 않는다."""
        env = {e.name: e.value for e in self._pod().spec.containers[0].env}
        assert env["DOCKER_TLS_CERTDIR"] == ""

    def test_readiness_probe_waits_for_daemon(self):
        probe = self._pod().spec.containers[0].readiness_probe
        assert probe._exec.command == ["docker", "info"]

    def test_is_idempotent(self):
        api = _FakeCoreApi(existing_pods={"sandbox-1"})
        _service(api)._provision_docker("user-1", "sandbox-1", {})
        assert api.created == [], "이미 있으면 다시 만들지 않는다"


class TestTrainingWorkload:
    def _service_with_exec(self, ps_output):
        service = _service(_FakeCoreApi())
        calls = []

        def fake_exec(namespace, pod, container, argv):
            calls.append(argv)
            if argv[:2] == ["docker", "ps"]:
                return ps_output
            return ""

        service._exec_in_sandbox = fake_exec
        return service, calls

    def _ref(self, environment=environments.DOCKER):
        return SandboxRef(
            id="s1",
            namespace="user-1",
            pod_name="sandbox-1",
            container_name="dind",
            environment=environment,
        )

    def test_creates_container_when_absent(self):
        service, calls = self._service_with_exec("")
        service.ensure_training_workload(self._ref())
        assert any(c[:2] == ["docker", "run"] for c in calls)

    def test_does_not_recreate_running_container(self):
        service, calls = self._service_with_exec("training-app running")
        service.ensure_training_workload(self._ref())
        assert not any(c[:2] == ["docker", "run"] for c in calls)
        assert not any(c[:2] == ["docker", "start"] for c in calls)

    def test_restarts_stopped_container(self):
        service, calls = self._service_with_exec("training-app exited")
        service.ensure_training_workload(self._ref())
        assert any(c[:2] == ["docker", "start"] for c in calls)
        assert not any(c[:2] == ["docker", "run"] for c in calls)

    def test_noop_for_kubernetes_environment(self):
        service, calls = self._service_with_exec("")
        service.ensure_training_workload(self._ref(environments.KUBERNETES))
        assert calls == []
