"""환경별 end-to-end 반복 검증 (BE-26) 과 지연 측정 (BE-27).

`pytest -m integration` 으로만 돈다. 실제 클러스터가 필요하다.

계획서가 요구한 반복 횟수:

    Kubernetes  2회 x 4미션   kubectl, Chaos Mesh, K8s validation
    Docker      2회 x 3미션   DinD 격리, Docker injector/validator
    Linux       2회 x 3미션   cgroup/ephemeral/PID 격리, Linux validator

각 실행에서 session user/environment, sandbox ID, inject/revert, validation latency,
cleanup 을 기록하고 JSON 보고서로 남긴다. 보고서를 남기는 이유: "돌려봤다" 가 아니라
**무엇이 몇 ms 걸렸는지**가 제출물이고, 다음에 느려졌을 때 비교 대상이 된다.

**복구는 세 환경 모두 사용자가 실제로 칠 명령으로 한다.** 명령은 `CommandValidator`
를 통과시켜 실행하므로, 정책이 막는 명령으로만 고칠 수 있는 장애는 여기서 걸린다.

처음에는 Kubernetes 만 `injector.revert()` 로 복구했는데 `service_misconfig` 에서
막혔다. 그 미션의 revert 는 검증기가 들여다보는 Service 자체를 지우기 때문에
되돌린 뒤에는 검증이 영원히 404 를 본다. 실제 흐름에서 revert 는 훈련이 끝난 뒤의
정리라 문제가 없지만, "revert 를 복구로 쓴다" 는 가정이 틀렸다는 뜻이다.
"""
import asyncio
import json
import os
import pathlib
import statistics
import time
import uuid

import pytest
import pytest_asyncio

from app.core import environments
from app.core.config import settings
from app.services.chaos_injector import ChaosMeshInjector
from app.services.command_validator import CommandValidator
from app.services.docker_chaos_injector import (
    CONTAINER_STOPPED,
    CPU_THROTTLE,
    NETWORK_DISCONNECT,
    DockerChaosInjector,
)
from app.services.docker_validation_service import DockerValidationService
from app.services.k8s_setup import get_k8s_setup_service
from app.services.linux_chaos_injector import (
    CPU_SATURATION,
    DISK_PRESSURE,
    PROCESS_FLOOD,
    LinuxChaosInjector,
)
from app.services.linux_validation_service import LinuxValidationService
from app.services.sandbox_service import SandboxService
from app.services.validation_service import K8sValidationService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

REPEAT = 2
APP = settings.SANDBOX_TRAINING_CONTAINER
NET = settings.SANDBOX_TRAINING_NETWORK
WORKDIR = settings.SANDBOX_LINUX_WORKDIR

# Kubernetes 복구 명령은 주입 핸들러 주석에 적힌 정답 경로를 그대로 옮긴 것이다.
K8S_IMAGE_FIX = "kubectl set image deployment/nginx nginx=" + settings.TRAINING_K8S_IMAGE
K8S_MEMORY_FIX = (
    'kubectl patch deployment/nginx -p '
    '\'{"spec":{"template":{"spec":{"containers":[{"name":"nginx",'
    '"resources":{"limits":{"memory":"128Mi"},"requests":{"memory":"64Mi"}}}]}}}}\''
)
K8S_SELECTOR_FIX = (
    'kubectl patch service webapp-svc -p \'{"spec":{"selector":{"app":"webapp"}}}\''
)
K8S_PROBE_FIX = (
    'kubectl patch deployment/nginx -p '
    '\'{"spec":{"template":{"spec":{"containers":[{"name":"nginx",'
    '"readinessProbe":null}]}}}}\''
)

# (환경, chaos_type, 사용자가 실제로 칠 복구 명령)
MATRIX = [
    (environments.KUBERNETES, "pod_failure", K8S_IMAGE_FIX),
    (environments.KUBERNETES, "memory_stress", K8S_MEMORY_FIX),
    (environments.KUBERNETES, "service_misconfig", K8S_SELECTOR_FIX),
    (environments.KUBERNETES, "network_latency", K8S_PROBE_FIX),
    (environments.DOCKER, CONTAINER_STOPPED, "docker start " + APP),
    (environments.DOCKER, NETWORK_DISCONNECT, "docker network connect " + NET + " " + APP),
    (environments.DOCKER, CPU_THROTTLE,
     "docker update --cpus " + settings.SANDBOX_TRAINING_CPUS + " " + APP),
    (environments.LINUX, DISK_PRESSURE, "rm " + WORKDIR + "/afterfail-fill.dat"),
    (environments.LINUX, CPU_SATURATION, "pkill -f afterfail-cpuburn"),
    (environments.LINUX, PROCESS_FLOOD, "pkill -f afterfail-worker"),
]

# BE-27 목표. 외부 단계(LLM, Prometheus)는 이 경로에 들어 있지 않다.
VALIDATION_TARGET_MS = 300

REPORT_PATH = pathlib.Path(
    os.environ.get(
        "BE26_REPORT",
        str(pathlib.Path(__file__).resolve().parents[2] / "reports" / "environment_matrix.json"),
    )
)


def _injector_for(environment, service):
    if environment == environments.KUBERNETES:
        return ChaosMeshInjector()
    if environment == environments.DOCKER:
        return DockerChaosInjector(sandbox_service=service)
    return LinuxChaosInjector(sandbox_service=service)


def _validation_for(environment, service):
    if environment == environments.KUBERNETES:
        return K8sValidationService()
    if environment == environments.DOCKER:
        return DockerValidationService(sandbox_service=service)
    return LinuxValidationService(sandbox_service=service)


async def _await_state(validation, chaos_type, namespace, expected, *, timeout=120):
    """검증 결과가 기대 상태가 될 때까지 기다리고, 걸린 시간과 단건 검증 시간을 돌려준다.

    장애 재현도 복구도 즉시 반영되지 않는다(Pod 재시작, supervisor 폴링, 상태 전이).
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    started = time.perf_counter()
    durations = []
    last = None
    while loop.time() < deadline:
        check_started = time.perf_counter()
        last = await validation.check_resolution(chaos_type, namespace)
        durations.append((time.perf_counter() - check_started) * 1000)
        if last.is_resolved == expected:
            return (time.perf_counter() - started) * 1000, durations
        await asyncio.sleep(2)
    pytest.fail(
        chaos_type + ": is_resolved=" + str(expected)
        + " 를 " + str(timeout) + "s 안에 보지 못했다. 마지막=" + str(last)
    )


def _run_user_command(service, sandbox, command, environment):
    """사용자가 터미널에 친 것과 같은 경로로 실행한다."""
    validator = CommandValidator()
    result = validator.validate_command(command, sandbox.namespace, environment=environment)
    if result.requires_confirmation:
        result = validator.validate_delete(
            command, sandbox.namespace, confirmed=True, environment=environment
        )
    assert result.is_valid, "명령 정책이 복구 명령을 막는다: " + command + " — " + result.error
    started = time.perf_counter()
    output = service.exec_in_sandbox(sandbox, result.argv)
    return (time.perf_counter() - started) * 1000, output


class _Recorder:
    """실행 기록을 모아 보고서로 쓴다."""

    def __init__(self):
        self.runs = []
        self.provision_ms = {}
        self.websocket_overhead = []

    def add(self, **row):
        self.runs.append(row)

    @staticmethod
    def _stats(values):
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, int(round(0.95 * len(ordered))) - 1))
        return {
            "count": len(ordered),
            "min": round(ordered[0], 1),
            "median": round(statistics.median(ordered), 1),
            "p95": round(ordered[index], 1),
            "max": round(ordered[-1], 1),
        }

    def validation_samples(self):
        return [ms for run in self.runs for ms in run.get("validation_samples_ms", [])]

    def summary(self):
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "cluster": os.environ.get("BE26_CLUSTER", "docker-desktop"),
            "runs": len(self.runs),
            "by_environment": {
                env: sum(1 for r in self.runs if r.get("environment") == env)
                for env in environments.IMPLEMENTED_ENVIRONMENTS
            },
            "target_validation_ms": VALIDATION_TARGET_MS,
            "validation_ms": self._stats(self.validation_samples()),
            "inject_ms": self._stats([r["inject_ms"] for r in self.runs]),
            "recover_ms": self._stats([r["recover_ms"] for r in self.runs]),
            "revert_ms": self._stats([r["revert_ms"] for r in self.runs]),
            "detect_ms": self._stats([r["detect_ms"] for r in self.runs]),
            "resolve_ms": self._stats([r["resolve_ms"] for r in self.runs]),
            "sandbox_provision_ms": self.provision_ms,
            "websocket_overhead": self.websocket_overhead,
        }

    def write(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        summary = self.summary()
        path.write_text(
            json.dumps({"summary": summary, "runs": self.runs}, indent=2, ensure_ascii=False)
        )
        return summary


@pytest.fixture(scope="module")
def recorder():
    return _Recorder()


@pytest.fixture(scope="module")
def service():
    return SandboxService()


@pytest.fixture(scope="module")
def users():
    """환경마다 사용자 하나. 샌드박스를 유지해야 세션 재사용 경로를 잰다."""
    return {env: uuid.uuid4() for env in environments.IMPLEMENTED_ENVIRONMENTS}


@pytest_asyncio.fixture(scope="module")
async def sandboxes(service, users, recorder):
    """환경별 샌드박스를 한 번만 만들고 모든 반복이 재사용한다.

    provision 시간은 BE-27 이 "신규 sandbox provision 은 별도 지표" 라고 명시한
    항목이라 따로 기록한다.
    """
    made = {}
    for environment, user_id in users.items():
        namespace = "user-" + str(user_id)
        started = time.perf_counter()
        made[environment] = await service.ensure(
            user_id=user_id, namespace=namespace, environment=environment
        )
        recorder.provision_ms[environment] = round((time.perf_counter() - started) * 1000, 1)
        if environment == environments.DOCKER:
            service.ensure_training_workload(made[environment])

    yield made

    setup = get_k8s_setup_service()
    for sandbox in made.values():
        try:
            await service.cleanup(sandbox)
            await setup.teardown_user_namespace(sandbox.namespace)
        except Exception as exc:  # 정리 실패가 보고서 작성을 막지 않게 한다
            print("[BE-26] cleanup 실패: " + sandbox.namespace + " — " + str(exc))

    summary = recorder.write(REPORT_PATH)
    print("\n[BE-26] 보고서: " + str(REPORT_PATH))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


@pytest.mark.parametrize("environment,chaos_type,recovery", MATRIX)
@pytest.mark.parametrize("attempt", range(1, REPEAT + 1))
async def test_training_loop(
    environment, chaos_type, recovery, attempt, service, sandboxes, users, recorder
):
    """주입 → 검증(미해결) → 사용자 복구 → 검증(해결) → revert 한 바퀴."""
    sandbox = sandboxes[environment]
    namespace = sandbox.namespace
    injector = _injector_for(environment, service)
    validation = _validation_for(environment, service)

    started = time.perf_counter()
    injected = await injector.inject(chaos_type, namespace)
    inject_ms = (time.perf_counter() - started) * 1000
    assert injected.success, environment + "/" + chaos_type + " 주입 실패: " + injected.message

    detect_ms, unresolved_samples = await _await_state(
        validation, chaos_type, namespace, False
    )

    recover_ms, _ = _run_user_command(service, sandbox, recovery, environment)
    resolve_ms, resolved_samples = await _await_state(
        validation, chaos_type, namespace, True
    )

    # 사용자가 먼저 고친 뒤의 revert 도 안전해야 한다(정리 경로가 여기로 온다).
    started = time.perf_counter()
    reverted = await injector.revert(injected.chaos_id, namespace)
    revert_ms = (time.perf_counter() - started) * 1000
    assert reverted is True

    recorder.add(
        environment=environment,
        attempt=attempt,
        chaos_type=chaos_type,
        user_id=str(users[environment]),
        namespace=namespace,
        sandbox_id=sandbox.id,
        container=sandbox.container_name,
        user_recovery=recovery,
        inject_ms=round(inject_ms, 1),
        detect_ms=round(detect_ms, 1),
        recover_ms=round(recover_ms, 1),
        resolve_ms=round(resolve_ms, 1),
        revert_ms=round(revert_ms, 1),
        validation_samples_ms=[
            round(ms, 1) for ms in (unresolved_samples + resolved_samples)
        ],
    )


class TestPerformanceTargets:
    """BE-27 목표 확인. 매트릭스가 수집한 표본으로 판정한다."""

    async def test_validation_p95_meets_the_target(self, recorder, sandboxes):
        samples = recorder.validation_samples()
        assert samples, "매트릭스가 먼저 돌아야 한다"
        stats = _Recorder._stats(samples)
        assert stats["p95"] < VALIDATION_TARGET_MS, (
            "검증 p95 " + str(stats["p95"]) + "ms 가 목표 "
            + str(VALIDATION_TARGET_MS) + "ms 를 넘었다"
        )

    async def test_websocket_command_overhead_excludes_execution(
        self, service, sandboxes, recorder
    ):
        """WebSocket 경로의 서버 오버헤드를 명령 실행 시간과 분리해 측정한다.

        executor 가 재는 `execution_time` 은 exec 왕복 그 자체다. 여기서는 핸들러가
        하는 일(정책 검증 → 실행 → 로깅 → 기록)을 전부 태운 뒤 그 값을 빼서,
        **서버가 얹는 시간**만 남긴다.
        """
        from app.services.websocket_handler import WebSocketHandler

        class _Socket:
            def __init__(self):
                self.sent = []

            async def send_json(self, data):
                self.sent.append(data)

        class _Db:
            def __init__(self):
                self.added = []

            def add(self, obj):
                self.added.append(obj)

            async def commit(self):
                pass

        class _Session:
            def __init__(self, sandbox):
                self.id = uuid.uuid4()
                self.namespace = sandbox.namespace
                self.environment = sandbox.environment
                self.last_activity = None

        handler = WebSocketHandler()
        for environment, command in (
            (environments.KUBERNETES, "kubectl get pods"),
            (environments.LINUX, "ps aux"),
        ):
            sandbox = sandboxes[environment]
            session = _Session(sandbox)
            for _ in range(3):
                socket = _Socket()
                started = time.perf_counter()
                await handler._handle_command(
                    websocket=socket,
                    command=command,
                    session=session,
                    sandbox=sandbox,
                    db=_Db(),
                )
                total_ms = (time.perf_counter() - started) * 1000
                payload = socket.sent[-1]
                assert payload["type"] == "output", payload
                command_ms = payload["execution_time"]
                recorder.websocket_overhead.append({
                    "environment": environment,
                    "total_ms": round(total_ms, 1),
                    "command_ms": round(command_ms, 1),
                    "server_overhead_ms": round(total_ms - command_ms, 1),
                })

        assert all(o["server_overhead_ms"] >= 0 for o in recorder.websocket_overhead)
