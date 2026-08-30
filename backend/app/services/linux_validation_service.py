"""Linux 환경 해결 검증.

샌드박스 안에서 `/proc` 과 파일시스템 상태를 구조적으로 읽어 판정한다.
명령 출력 문자열을 그대로 비교하지 않고, 숫자로 뽑아 임계값과 비교한다.

검증은 외부 의존이 없다. Kubernetes API 도 Prometheus 도 쓰지 않고 샌드박스
exec 한 번으로 끝나므로, 계획서의 300ms 목표는 exec 왕복 시간이 지배한다.
"""
import asyncio
import logging
import time

from app.core import environments
from app.core.config import settings
from app.services.linux_chaos_injector import (
    CPU_SATURATION,
    DISK_PRESSURE,
    PROCESS_FLOOD,
)
from app.services.sandbox_service import SandboxRef, get_sandbox_service
from app.services.validation_service import (
    RETRY_MESSAGE,
    SUCCESS_MESSAGE,
    BaseValidationService,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# 작업 디렉터리 사용률이 이 값 아래로 내려오면 해결로 본다.
_DISK_RECOVERY_PERCENT = 20
# 남아 있어도 되는 워크로드 수. 패턴이 자기 명령줄을 세지 않으므로 0 을 요구할 수 있다.
_PROCESS_RECOVERY_MAX = 0


class LinuxValidationService(BaseValidationService):
    environment = environments.LINUX

    def __init__(self, sandbox_service=None):
        self._sandboxes = sandbox_service or get_sandbox_service()

    async def check_resolution(self, chaos_type: str, namespace: str) -> ValidationResult:
        check = self._CHECKS.get(chaos_type)
        if check is None:
            logger.warning("unknown linux chaos type", extra={"chaos_type": chaos_type})
            return self._retry()

        loop = asyncio.get_event_loop()
        started = time.perf_counter()
        try:
            result = await loop.run_in_executor(None, lambda: check(self, namespace))
        except Exception:
            # 원인은 서버 로그에만 남긴다. 사용자에게 내부 상태를 노출하지 않는다.
            logger.exception(
                "linux validation failed",
                extra={"chaos_type": chaos_type, "namespace": namespace},
            )
            return self._retry()

        elapsed_ms = round((time.perf_counter() - started) * 1000)
        logger.info(
            "linux validation done",
            extra={"chaos_type": chaos_type, "duration_ms": elapsed_ms},
        )
        if result.is_resolved and result.details is not None:
            result.details["duration_ms"] = elapsed_ms
        return result

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
            user_id=user_id, namespace=namespace, environment=environments.LINUX
        )

    def _run(self, namespace: str, argv: list[str]) -> str:
        return self._sandboxes.exec_in_sandbox(self._sandbox_for(namespace), argv).strip()

    @staticmethod
    def _self_excluding_pattern(name: str) -> str:
        """자기 명령줄을 세지 않는 grep 패턴.

        `grep -c afterfail-worker` 를 쓰면 검사를 실행하는 sh 와 grep 자신의
        명령줄에도 그 문자열이 들어가 항상 2 이상이 나온다. 첫 글자를 문자
        클래스로 감싸면 패턴 자체는 매치되지 않고 실제 프로세스만 잡힌다.
        """
        return f"[{name[0]}]{name[1:]}"

    def _count_workload(self, namespace: str, name: str) -> int:
        """이름이 붙은 워크로드 수. 명령줄을 직접 센다."""
        pattern = self._self_excluding_pattern(name)
        output = self._run(
            namespace,
            ["sh", "-c", f"ps -eo args | grep -c '{pattern}' || true"],
        )
        try:
            return int(output or 0)
        except ValueError:
            return 0

    # --- 검증 ------------------------------------------------------------

    def _check_disk_pressure(self, namespace: str) -> ValidationResult:
        raw = self._run(
            namespace,
            [
                "sh", "-c",
                f"df -P '{settings.SANDBOX_LINUX_WORKDIR}' | tail -1 | awk '{{print $5}}'",
            ],
        )
        used = int(raw.rstrip("%") or 0)
        if used >= _DISK_RECOVERY_PERCENT:
            return self._retry()
        return self._resolved({"workdir_used_percent": used})

    def _check_cpu_saturation(self, namespace: str) -> ValidationResult:
        remaining = self._count_workload(namespace, "afterfail-cpuburn")
        if remaining > 0:
            return self._retry()
        return self._resolved({"cpuburn_processes": remaining})

    def _check_process_flood(self, namespace: str) -> ValidationResult:
        remaining = self._count_workload(namespace, "afterfail-worker")
        if remaining > _PROCESS_RECOVERY_MAX:
            return self._retry()
        return self._resolved({"worker_processes": remaining})

    _CHECKS = {
        DISK_PRESSURE: _check_disk_pressure,
        CPU_SATURATION: _check_cpu_saturation,
        PROCESS_FLOOD: _check_process_flood,
    }
