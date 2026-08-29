"""Docker 환경 장애 주입.

DinD 샌드박스 안에서 docker 명령으로 장애를 만든다. Chaos Mesh 는 Kubernetes
전용이라 이 환경에는 쓸 수 없다.

**등록 기준: 사용자가 BE-12 명령 정책 안에서 실제로 복구할 수 있는 장애만 넣는다.**
장애는 나는데 아무도 못 고치는 미션은 교육적으로 무의미하다.
(Kubernetes 미션 4가 실제로 그 상태였고 BE-10 에서 고쳤다)

계획서가 요구한 volume/mount error 는 제외했다. 실측 근거:
  - `docker update` 에 볼륨·마운트 옵션이 없어 실행 중 변경이 불가능하다
  - 사용 중인 볼륨은 삭제가 거부된다("volume is in use")
  - 컨테이너를 멈춰도 참조가 남아 삭제되지 않는다
유일한 경로가 `docker rm` 후 볼륨 없이 `docker run` 인데, 복구하려면 사용자가
`docker run` 을 칠 수 있어야 한다. 그 명령은 임의 이미지 실행 위험 때문에
BE-12 에서 차단했다. 대신 컨테이너 중지 장애를 넣었다.
"""
import asyncio
import logging
import uuid

from app.core import environments
from app.core.config import settings
from app.services.chaos_injector import BaseChaosInjector, ChaosResult
from app.services.sandbox_service import SandboxRef, get_sandbox_service

logger = logging.getLogger(__name__)

NETWORK_DISCONNECT = "docker_network_disconnect"
CONTAINER_STOPPED = "docker_container_stopped"
CPU_THROTTLE = "docker_cpu_throttle"


class DockerChaosInjector(BaseChaosInjector):
    """DinD 샌드박스 안에서 훈련 컨테이너에 장애를 만든다."""

    environment = environments.DOCKER

    # 자원 고갈 장애에서 낮출 CPU 상한. 샌드박스 한도 안에서만 움직인다.
    #
    # 메모리를 쓰지 않는 이유(실측): docker 는 메모리 상한을 올릴 때
    # memory+swap >= memory 를 요구해서, 사용자가 `--memory` 만 쳐서는
    # "memory+swap limit should be >= memory limit" 로 복구가 실패한다.
    # 항상 `--memory-swap` 을 짝으로 요구하는 것은 훈련 난이도가 아니라 함정이다.
    # CPU 는 낮추기/올리기 왕복이 그대로 동작한다.
    THROTTLED_CPUS = "0.05"

    def __init__(self, sandbox_service=None):
        self._sandboxes = sandbox_service or get_sandbox_service()

    def supported_chaos_types(self) -> frozenset[str]:
        return frozenset(self._HANDLERS)

    async def inject(self, chaos_type: str, namespace: str) -> ChaosResult:
        handlers = self._HANDLERS.get(chaos_type)
        if handlers is None:
            return ChaosResult(
                success=False,
                chaos_id=f"error-{uuid.uuid4().hex[:8]}",
                message=f"Unknown chaos_type: {chaos_type}",
            )

        chaos_id = f"{chaos_type.replace('_', '-')}-{uuid.uuid4().hex[:8]}"
        apply_handler, revert_handler = handlers
        loop = asyncio.get_running_loop()

        try:
            sandbox = self._sandbox_for(namespace)
            snapshot = await loop.run_in_executor(
                None, lambda: self._snapshot(sandbox)
            )
            await loop.run_in_executor(None, lambda: apply_handler(self, sandbox))
        except Exception as exc:
            logger.exception("docker chaos inject failed", extra={"namespace": namespace})
            # 부분 적용이 남지 않도록 되돌린 뒤 실패를 알린다.
            try:
                await loop.run_in_executor(None, lambda: revert_handler(self, sandbox))
            except Exception:
                logger.exception("partial docker chaos rollback failed")
            return ChaosResult(
                success=False,
                chaos_id=f"error-{uuid.uuid4().hex[:8]}",
                message=str(exc),
            )

        logger.info(
            "docker chaos injected",
            extra={"chaos_id": chaos_id, "namespace": namespace, "chaos_type": chaos_type},
        )
        return ChaosResult(
            success=True,
            chaos_id=chaos_id,
            message=f"{chaos_type} injected into {namespace}",
            # 원상태 스냅샷. 복구는 스냅샷 없이도 되지만 진단용으로 남긴다.
            metadata={"snapshot": snapshot},
        )

    async def revert(self, chaos_id: str, namespace: str) -> bool:
        chaos_type = self.chaos_type_from_id(chaos_id)
        handlers = self._HANDLERS.get(chaos_type) if chaos_type else None
        if handlers is None:
            logger.warning(
                "cannot resolve docker chaos type", extra={"chaos_id": chaos_id}
            )
            return False

        _, revert_handler = handlers
        loop = asyncio.get_running_loop()
        try:
            sandbox = self._sandbox_for(namespace)
            await loop.run_in_executor(None, lambda: revert_handler(self, sandbox))
        except Exception:
            # 재시도할 수 있도록 원인을 남긴다.
            logger.exception(
                "docker chaos revert failed",
                extra={"chaos_id": chaos_id, "namespace": namespace},
            )
            return False

        logger.info(
            "docker chaos reverted",
            extra={"chaos_id": chaos_id, "namespace": namespace},
        )
        return True

    # --- 실행 헬퍼 -------------------------------------------------------

    def _sandbox_for(self, namespace: str) -> SandboxRef:
        """namespace 로 서버가 만든 샌드박스 참조를 복원한다.

        namespace 는 `user-{user_id}` 형식이다. 클라이언트 입력이 아니라
        DB 세션에서 온 값이므로 신뢰할 수 있다.
        """
        user_id = namespace.removeprefix("user-")
        return self._sandboxes.reference_for(
            user_id=user_id, namespace=namespace, environment=environments.DOCKER
        )

    def _run(self, sandbox: SandboxRef, argv: list[str]) -> str:
        return self._sandboxes.exec_in_sandbox(sandbox, argv)

    @property
    def _app(self) -> str:
        return settings.SANDBOX_TRAINING_CONTAINER

    @property
    def _network(self) -> str:
        return settings.SANDBOX_TRAINING_NETWORK

    # inspect 전체 출력은 exec 채널을 거치며 표준 JSON 으로 오지 않는다.
    # 필요한 값만 --format 으로 하나씩 뽑는다.
    _SNAPSHOT_FIELDS = {
        "state": "{{.State.Status}}",
        "networks": "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}",
        "nano_cpus": "{{.HostConfig.NanoCpus}}",
        "memory": "{{.HostConfig.Memory}}",
    }

    def _snapshot(self, sandbox: SandboxRef) -> dict:
        """주입 전 상태. 복구가 실패했을 때 무엇이 달라졌는지 알기 위해 남긴다."""
        snapshot = {}
        for key, template in self._SNAPSHOT_FIELDS.items():
            try:
                value = self._run(
                    sandbox, ["docker", "inspect", self._app, "--format", template]
                ).strip()
            except Exception:
                logger.warning(
                    "docker snapshot field failed",
                    extra={"container": self._app, "field": key},
                )
                continue
            snapshot[key] = value.split() if key == "networks" else value
        return snapshot

    # --- 장애: 네트워크 분리 ---------------------------------------------
    # 사용자 복구: docker network connect training-net training-app

    def _apply_network_disconnect(self, sandbox: SandboxRef) -> None:
        self._run(
            sandbox, ["docker", "network", "disconnect", self._network, self._app]
        )

    def _revert_network_disconnect(self, sandbox: SandboxRef) -> None:
        # 이미 연결돼 있으면 docker 가 오류를 내므로 상태를 먼저 확인한다(멱등).
        if self._network in self._connected_networks(sandbox):
            return
        self._run(sandbox, ["docker", "network", "connect", self._network, self._app])

    def _connected_networks(self, sandbox: SandboxRef) -> set[str]:
        raw = self._run(
            sandbox,
            [
                "docker", "inspect", self._app,
                "--format", "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}",
            ],
        )
        return set(raw.split())

    # --- 장애: 컨테이너 중지 ---------------------------------------------
    # 사용자 복구: docker start training-app

    def _apply_container_stopped(self, sandbox: SandboxRef) -> None:
        self._run(sandbox, ["docker", "stop", self._app])

    def _revert_container_stopped(self, sandbox: SandboxRef) -> None:
        if self._container_state(sandbox) == "running":
            return
        self._run(sandbox, ["docker", "start", self._app])

    def _container_state(self, sandbox: SandboxRef) -> str:
        return self._run(
            sandbox, ["docker", "inspect", self._app, "--format", "{{.State.Status}}"]
        ).strip()

    # --- 장애: CPU 고갈 ---------------------------------------------------
    # 사용자 복구: docker update --cpus 1 training-app

    def _apply_cpu_throttle(self, sandbox: SandboxRef) -> None:
        self._run(
            sandbox, ["docker", "update", "--cpus", self.THROTTLED_CPUS, self._app]
        )

    def _revert_cpu_throttle(self, sandbox: SandboxRef) -> None:
        self._run(
            sandbox,
            ["docker", "update", "--cpus", settings.SANDBOX_TRAINING_CPUS, self._app],
        )

    _HANDLERS = {
        NETWORK_DISCONNECT: (_apply_network_disconnect, _revert_network_disconnect),
        CONTAINER_STOPPED: (_apply_container_stopped, _revert_container_stopped),
        CPU_THROTTLE: (_apply_cpu_throttle, _revert_cpu_throttle),
    }
