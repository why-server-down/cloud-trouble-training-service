"""Docker 환경 해결 검증.

DinD 샌드박스 안에서 `docker inspect` 결과를 읽어 판정한다.

문자열 출력을 그대로 비교하지 않고 필요한 값을 Go template 으로 뽑아 구조적으로
읽는다. `docker inspect` 전체 출력은 exec 채널을 거치며 표준 JSON 으로 오지 않아
`json.loads` 가 실패한다(BE-13 실측). 필드별 `--format` 이 이 환경에서 신뢰할 수 있는
유일한 방법이다.
"""
import asyncio
import logging

from app.core import environments
from app.core.config import settings
from app.services.docker_chaos_injector import (
    CONTAINER_STOPPED,
    CPU_THROTTLE,
    NETWORK_DISCONNECT,
)
from app.services.sandbox_service import SandboxRef, get_sandbox_service
from app.services.validation_service import (
    RETRY_MESSAGE,
    SUCCESS_MESSAGE,
    BaseValidationService,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# CPU 가 이 값 이상으로 회복되면 해결로 본다. 사용자가 정확히 같은 값을 넣지 않아도
# 되도록 여유를 둔다(예: --cpus 0.5 로 올려도 훈련 목적은 달성된다).
_CPU_RECOVERY_RATIO = 0.5


class DockerValidationService(BaseValidationService):
    environment = environments.DOCKER

    def __init__(self, sandbox_service=None):
        self._sandboxes = sandbox_service or get_sandbox_service()

    async def check_resolution(self, chaos_type: str, namespace: str) -> ValidationResult:
        check = self._CHECKS.get(chaos_type)
        if check is None:
            logger.warning("unknown docker chaos type", extra={"chaos_type": chaos_type})
            return self._retry()

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, lambda: check(self, namespace))
        except Exception:
            # 원인은 서버 로그에만 남긴다. 사용자에게 내부 상태를 노출하지 않는다.
            logger.exception(
                "docker validation failed",
                extra={"chaos_type": chaos_type, "namespace": namespace},
            )
            return self._retry()

    @staticmethod
    def _retry() -> ValidationResult:
        return ValidationResult(is_resolved=False, message=RETRY_MESSAGE)

    @staticmethod
    def _resolved(details: dict) -> ValidationResult:
        # details 는 내부 진단용이다. message 에는 정답을 담지 않는다.
        return ValidationResult(
            is_resolved=True, message=SUCCESS_MESSAGE, details=details
        )

    # --- 실행 헬퍼 -------------------------------------------------------

    def _sandbox_for(self, namespace: str) -> SandboxRef:
        user_id = namespace.removeprefix("user-")
        return self._sandboxes.reference_for(
            user_id=user_id, namespace=namespace, environment=environments.DOCKER
        )

    def _inspect(self, namespace: str, template: str) -> str:
        """훈련 컨테이너에서 필요한 값 하나만 구조적으로 읽는다."""
        sandbox = self._sandbox_for(namespace)
        return self._sandboxes.exec_in_sandbox(
            sandbox,
            [
                "docker", "inspect", settings.SANDBOX_TRAINING_CONTAINER,
                "--format", template,
            ],
        ).strip()

    # --- 검증 ------------------------------------------------------------

    def _check_network_disconnect(self, namespace: str) -> ValidationResult:
        raw = self._inspect(
            namespace,
            "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}",
        )
        networks = set(raw.split())
        if settings.SANDBOX_TRAINING_NETWORK not in networks:
            return self._retry()
        return self._resolved({"networks": sorted(networks)})

    def _check_container_stopped(self, namespace: str) -> ValidationResult:
        state = self._inspect(namespace, "{{.State.Status}}")
        if state != "running":
            return self._retry()
        return self._resolved({"state": state})

    def _check_cpu_throttle(self, namespace: str) -> ValidationResult:
        raw = self._inspect(namespace, "{{.HostConfig.NanoCpus}}")
        nano_cpus = int(raw or 0)
        # 0 은 제한 없음을 뜻한다. 제한을 아예 푼 것도 해결로 본다.
        if nano_cpus == 0:
            return self._resolved({"nano_cpus": nano_cpus, "cpus": "unlimited"})

        baseline = float(settings.SANDBOX_TRAINING_CPUS) * 1_000_000_000
        if nano_cpus < baseline * _CPU_RECOVERY_RATIO:
            return self._retry()
        return self._resolved({"nano_cpus": nano_cpus, "cpus": nano_cpus / 1e9})

    _CHECKS = {
        NETWORK_DISCONNECT: _check_network_disconnect,
        CONTAINER_STOPPED: _check_container_stopped,
        CPU_THROTTLE: _check_cpu_throttle,
    }
