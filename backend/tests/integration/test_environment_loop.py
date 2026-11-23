"""실제 클러스터에서의 환경별 훈련 루프 (BE-24).

`pytest -m integration` 으로만 돈다. 기본 유닛 스위트는 클러스터 없이 돌아야 하기
때문이다(CI 포함).

이 파일이 필요한 이유: 이 프로젝트에서 실제로 발생한 결함은 대부분 유닛 테스트가
잡을 수 없는 것들이었다 — 존재하지 않는 이미지 태그, 잘못된 Chaos Mesh
네임스페이스, RollingUpdate 때문에 장애가 재현되지 않는 문제, exec 으로 띄운
프로세스가 회수되는 문제, busybox 의 동작 차이, grep 자기 자신 매칭.
전부 살아 있는 클러스터에서만 드러났다. 그래서 그때의 수동 검증을 여기에 고정한다.

각 환경마다 한 바퀴를 돈다:
  샌드박스 생성 → 장애 주입 → 검증(미해결) → 사용자 복구 명령 → 검증(해결) → 정리

복구 명령은 반드시 `CommandValidator` 를 통과시켜 실행한다. 정책이 막는 명령으로만
고칠 수 있는 장애는 훈련이 되지 않으므로, 그 계약을 여기서도 같이 확인한다.

Kubernetes 는 미션마다 복구 경로가 달라 한 바퀴로 대표할 수 없다. 대신 샌드박스가
실제로 뜨고 RBAC 격리가 걸리는지를 확인한다(BE-10 에서 수동으로 본 것).
"""
import asyncio
import uuid

import pytest
import pytest_asyncio

from app.core import environments
from app.core.config import settings
from app.services.command_validator import CommandValidator
from app.services.docker_chaos_injector import CONTAINER_STOPPED, DockerChaosInjector
from app.services.docker_validation_service import DockerValidationService
from app.services.linux_chaos_injector import PROCESS_FLOOD, LinuxChaosInjector
from app.services.linux_validation_service import LinuxValidationService
from app.services.k8s_setup import get_k8s_setup_service
from app.services.sandbox_service import SandboxService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# 네임스페이스는 반드시 실제와 같은 `user-{user_id}` 형식이어야 한다.
# 주입기·검증기는 namespace 에서 user_id 를 복원해 샌드박스 참조를 만들기 때문에,
# 형식이 다르면 만든 샌드박스와 찾는 샌드박스가 어긋난다(2026-09-01 실측).
# 실행마다 새 id 를 쓴다. 고정 id 를 쓰면 연속 실행 때 앞 실행이 지우는 중인
# (Terminating) 네임스페이스에 다시 만들려다 실패한다.
USER_IDS = {
    environment: uuid.uuid4()
    for environment in environments.IMPLEMENTED_ENVIRONMENTS
}


def _namespace(environment: str) -> str:
    return f"user-{USER_IDS[environment]}"


NAMESPACES_IN_USE = tuple(USER_IDS)

# 사용자가 실제로 칠 복구 명령
RECOVERY = {
    environments.DOCKER: f"docker start {settings.SANDBOX_TRAINING_CONTAINER}",
    environments.LINUX: "pkill -f afterfail-worker",
}


async def _await_resolution(validation, chaos_type, namespace, expected, *, timeout=90):
    """검증 결과가 기대 상태가 될 때까지 기다린다.

    장애 재현도 복구도 즉시 반영되지 않는다(supervisor 폴링, 컨테이너 상태 전이).
    """
    deadline = asyncio.get_running_loop().time() + timeout
    last = None
    while asyncio.get_running_loop().time() < deadline:
        last = await validation.check_resolution(chaos_type, namespace)
        if last.is_resolved == expected:
            return last
        await asyncio.sleep(2)
    pytest.fail(
        f"{chaos_type}: is_resolved={expected} 를 {timeout}s 안에 보지 못했다. 마지막={last}"
    )


def _run_user_command(service, sandbox, command, environment):
    """사용자가 터미널에 친 것과 같은 경로로 실행한다."""
    validator = CommandValidator()
    result = validator.validate_command(command, sandbox.namespace, environment=environment)
    if result.requires_confirmation:
        result = validator.validate_delete(
            command, sandbox.namespace, confirmed=True, environment=environment
        )
    assert result.is_valid, f"명령 정책이 복구 명령을 막는다: {result.error}"
    return service.exec_in_sandbox(sandbox, result.argv)


@pytest.fixture(scope="module")
def service():
    return SandboxService()


@pytest.fixture(scope="module", autouse=True)
def cleanup_namespaces():
    """모듈이 끝난 뒤에만 네임스페이스를 지운다.

    테스트마다 지우면 다음 테스트가 Terminating 상태의 네임스페이스에 만들려다
    실패한다. 남겨 두면 클러스터에 훈련 네임스페이스가 쌓이므로 마지막에 정리한다.
    """
    yield
    setup = get_k8s_setup_service()

    async def teardown():
        for environment in NAMESPACES_IN_USE:
            await setup.teardown_user_namespace(_namespace(environment))

    asyncio.run(teardown())


@pytest_asyncio.fixture
async def sandbox(request, service):
    """환경별 샌드박스. 샌드박스 리소스만 지운다(네임스페이스는 모듈 끝에서)."""
    environment = request.param
    reference = await service.ensure(
        user_id=USER_IDS[environment],
        namespace=_namespace(environment),
        environment=environment,
    )
    yield reference
    await service.cleanup(reference)


class TestDockerLoop:
    @pytest.mark.parametrize("sandbox", [environments.DOCKER], indirect=True)
    async def test_inject_recover_validate(self, service, sandbox):
        service.ensure_training_workload(sandbox)
        injector = DockerChaosInjector(sandbox_service=service)
        validation = DockerValidationService(sandbox_service=service)

        injected = await injector.inject(CONTAINER_STOPPED, sandbox.namespace)
        assert injected.success, injected.message

        await _await_resolution(validation, CONTAINER_STOPPED, sandbox.namespace, False)
        _run_user_command(
            service, sandbox, RECOVERY[environments.DOCKER], environments.DOCKER
        )
        await _await_resolution(validation, CONTAINER_STOPPED, sandbox.namespace, True)

        # revert 는 이미 복구된 상태에서도 안전해야 한다(사용자가 먼저 고친 경우)
        assert await injector.revert(injected.chaos_id, sandbox.namespace) is True


class TestLinuxLoop:
    @pytest.mark.parametrize("sandbox", [environments.LINUX], indirect=True)
    async def test_inject_recover_validate(self, service, sandbox):
        injector = LinuxChaosInjector(sandbox_service=service)
        validation = LinuxValidationService(sandbox_service=service)

        injected = await injector.inject(PROCESS_FLOOD, sandbox.namespace)
        assert injected.success, injected.message

        # supervisor 가 신호 파일을 읽고 워크로드를 띄울 때까지 기다린다
        await _await_resolution(validation, PROCESS_FLOOD, sandbox.namespace, False)

        _run_user_command(
            service, sandbox, RECOVERY[environments.LINUX], environments.LINUX
        )
        await _await_resolution(validation, PROCESS_FLOOD, sandbox.namespace, True)

        assert await injector.revert(injected.chaos_id, sandbox.namespace) is True

    @pytest.mark.parametrize("sandbox", [environments.LINUX], indirect=True)
    async def test_sandbox_has_no_cluster_credentials(self, service, sandbox):
        """Linux 샌드박스에는 ServiceAccount 토큰을 마운트하지 않는다."""
        output = service.exec_in_sandbox(
            sandbox, ["ls", "/var/run/secrets/kubernetes.io/serviceaccount"]
        )
        assert "token" not in output


class TestKubernetesSandbox:
    @pytest.mark.parametrize("sandbox", [environments.KUBERNETES], indirect=True)
    async def test_user_can_only_see_their_own_namespace(self, service, sandbox):
        """RBAC 격리. 정책을 우회해 직접 실행해도 다른 네임스페이스는 막힌다."""
        mine = _run_user_command(
            service, sandbox, "kubectl get pods", environments.KUBERNETES
        )
        assert "nginx" in mine

        # 검증기를 거치지 않고 직접 쏴도 RBAC 이 막아야 한다
        foreign = service.exec_in_sandbox(
            sandbox, ["kubectl", "get", "pods", "-n", "kube-system"]
        )
        assert "forbidden" in foreign.lower() or "cannot list" in foreign.lower()
