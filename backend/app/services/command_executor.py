"""검증된 argv 를 샌드박스 Pod 안에서 실행한다.

호스트 셸에서 사용자 명령을 실행하지 않는다. `shell=True` 나
`create_subprocess_shell` 을 쓰면 validator 를 우회당하는 순간 호스트 RCE 가 된다.
실행 대상(namespace/pod/container)은 항상 서버가 DB 세션에서 만든 SandboxRef 이며
클라이언트가 보낸 값을 쓰지 않는다.
"""
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import settings
from app.services.sandbox_service import SandboxRef

logger = logging.getLogger(__name__)

# kubernetes stream 의 채널 번호
_STDOUT_CHANNEL = 1
_STDERR_CHANNEL = 2
_ERROR_CHANNEL = 3


@dataclass
class CommandResult:
    output: str
    exit_code: int
    execution_time: float  # milliseconds
    truncated: bool = False


def _clamp_timeout(timeout: int | None) -> int:
    if timeout is None:
        timeout = settings.COMMAND_TIMEOUT_SECONDS
    return max(1, min(timeout, settings.COMMAND_TIMEOUT_MAX_SECONDS))


def _truncate(output: str) -> tuple[str, bool]:
    limit = settings.COMMAND_OUTPUT_LIMIT_BYTES
    encoded = output.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return output, False
    clipped = encoded[:limit].decode("utf-8", errors="ignore")
    return clipped + "\n... (출력이 잘렸습니다)", True


class BaseCommandExecutor(ABC):
    @abstractmethod
    async def execute(
        self, argv: list[str], sandbox: SandboxRef, timeout: int | None = None
    ) -> CommandResult:
        """검증된 argv 를 샌드박스 안에서 실행한다."""


class MockCommandExecutor(BaseCommandExecutor):
    """클러스터 없이 UI·계약을 확인하기 위한 실행기."""

    async def execute(
        self, argv: list[str], sandbox: SandboxRef, timeout: int | None = None
    ) -> CommandResult:
        started_at = time.perf_counter()
        await asyncio.sleep(0)
        output = (
            f"[mock] {' '.join(argv)}\n"
            f"[mock] sandbox={sandbox.pod_name} namespace={sandbox.namespace} "
            f"environment={sandbox.environment}\n"
        )
        return CommandResult(
            output=output,
            exit_code=0,
            execution_time=(time.perf_counter() - started_at) * 1000,
        )


class SandboxCommandExecutor(BaseCommandExecutor):
    """Kubernetes exec 으로 샌드박스 Pod 안에서 실행한다."""

    def __init__(self, core_api=None):
        if core_api is None:
            from kubernetes import client, config

            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            core_api = client.CoreV1Api()
        self._core_api = core_api

    async def execute(
        self, argv: list[str], sandbox: SandboxRef, timeout: int | None = None
    ) -> CommandResult:
        seconds = _clamp_timeout(timeout)
        started_at = time.perf_counter()
        loop = asyncio.get_running_loop()

        try:
            output, exit_code = await asyncio.wait_for(
                loop.run_in_executor(None, self._exec_sync, argv, sandbox, seconds),
                timeout=seconds + 1,
            )
        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - started_at) * 1000
            logger.warning(
                "command timed out",
                extra={"sandbox_id": sandbox.id, "timeout_seconds": seconds},
            )
            return CommandResult(
                output=f"명령이 {seconds}초 안에 끝나지 않아 중단했습니다.",
                exit_code=124,
                execution_time=elapsed,
            )
        except Exception:
            elapsed = (time.perf_counter() - started_at) * 1000
            # 원문은 서버 로그에만 남긴다. 사용자에게 내부 오류를 노출하지 않는다.
            logger.exception("command execution failed", extra={"sandbox_id": sandbox.id})
            return CommandResult(
                output="명령을 실행하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                exit_code=1,
                execution_time=elapsed,
            )

        truncated_output, truncated = _truncate(output)
        return CommandResult(
            output=truncated_output,
            exit_code=exit_code,
            execution_time=(time.perf_counter() - started_at) * 1000,
            truncated=truncated,
        )

    def _exec_sync(
        self, argv: list[str], sandbox: SandboxRef, seconds: int
    ) -> tuple[str, int]:
        from kubernetes.stream import stream

        response = stream(
            self._core_api.connect_get_namespaced_pod_exec,
            sandbox.pod_name,
            sandbox.namespace,
            container=sandbox.container_name,
            command=argv,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _preload_content=False,
        )

        chunks: list[str] = []
        deadline = time.monotonic() + seconds
        try:
            while response.is_open():
                if time.monotonic() > deadline:
                    raise TimeoutError
                response.update(timeout=1)
                if response.peek_stdout():
                    chunks.append(response.read_stdout())
                if response.peek_stderr():
                    chunks.append(response.read_stderr())
            exit_code = self._exit_code(response)
        finally:
            response.close()

        return "".join(chunks), exit_code

    @staticmethod
    def _exit_code(response) -> int:
        """exec 결과 채널에서 종료 코드를 읽는다."""
        try:
            import yaml

            raw = response.read_channel(_ERROR_CHANNEL)
            if not raw:
                return 0
            status = yaml.safe_load(raw)
            if not isinstance(status, dict):
                return 0
            if status.get("status") == "Success":
                return 0
            for cause in (status.get("details") or {}).get("causes") or []:
                if cause.get("reason") == "ExitCode":
                    return int(cause.get("message", 1))
            return 1
        except Exception:
            return 1


_EXECUTOR_FACTORIES = {
    "sandbox": SandboxCommandExecutor,
    "mock": MockCommandExecutor,
}


def create_command_executor() -> BaseCommandExecutor:
    factory = _EXECUTOR_FACTORIES.get(settings.TERMINAL_BACKEND)
    if factory is None:
        raise ValueError(f"Unknown TERMINAL_BACKEND: {settings.TERMINAL_BACKEND}")
    return factory()
