"""Linux 환경 장애 주입.

장애 워크로드를 exec 으로 직접 띄우지 않는다. Kubernetes exec 으로 만든 백그라운드
프로세스는 exec 세션이 끝나면 containerd 가 프로세스 그룹째 정리하기 때문이다
(BE-17 실측: setsid / nohup / </dev/null 모두 무효).

대신 injector 는 **신호 파일만 만들고**, 샌드박스의 PID 1 인 supervisor 가 그것을 보고
워크로드를 띄운다. supervisor 는 한 번 처리한 신호를 다시 실행하지 않으므로,
사용자가 워크로드를 정리하면 그대로 복구된다.

계획서가 요구한 zombie/orphan 은 제외했다. 실측 결과 이 이미지의 busybox sh 가
자식을 곧바로 회수해 좀비가 유지되지 않는다. 중첩 셸로 exec 세션 안에서는 좀비를
만들 수 있었지만, supervisor 가 띄운 워크로드에서는 재현되지 않았다. 관측되지 않는
장애는 훈련이 될 수 없으므로 CPU 포화로 대체했다.

안전 기준(계획서):
  - 호스트 OOM-Killer 를 직접 유발하지 않는다 → 모든 장애가 컨테이너 cgroup 안에서 끝난다
  - 호스트 디스크를 채우지 않는다 → 작업 디렉터리가 크기 제한된 tmpfs 다
  - process count 를 제한한다 → 생성 개수를 설정으로 묶는다
  - 모든 워크로드에 duration 과 cleanup 이 있다 → 워크로드는 24시간 후 종료되고
    revert 가 즉시 정리한다
"""
import asyncio
import logging
import uuid

from app.core import environments
from app.core.config import settings
from app.services.chaos_injector import BaseChaosInjector, ChaosResult
from app.services.sandbox_service import SandboxRef, get_sandbox_service

logger = logging.getLogger(__name__)

DISK_PRESSURE = "linux_disk_pressure"
CPU_SATURATION = "linux_cpu_saturation"
PROCESS_FLOOD = "linux_process_flood"

# supervisor 가 읽는 신호 이름
_SIGNAL_NAMES = {
    DISK_PRESSURE: "disk_pressure",
    CPU_SATURATION: "cpu_saturation",
    PROCESS_FLOOD: "process_flood",
}


class LinuxChaosInjector(BaseChaosInjector):
    environment = environments.LINUX

    # 작업 디렉터리(tmpfs) 크기의 대부분을 채운다. 상한이 있어 호스트에 영향이 없다.
    DISK_FILL_MB = 56
    # 프로세스 상한보다 적게 만든다. PID 고갈로 샌드박스가 마비되면 복구도 못 한다.
    FLOOD_PROCESS_COUNT = 120
    # CPU 를 태우는 워커 수. 컨테이너 CPU 상한 안에서만 돌아 노드에 영향이 없다.
    CPU_BURN_WORKERS = 2

    def __init__(self, sandbox_service=None):
        self._sandboxes = sandbox_service or get_sandbox_service()

    def supported_chaos_types(self) -> frozenset[str]:
        return frozenset(_SIGNAL_NAMES)

    # --- 인터페이스 ------------------------------------------------------

    async def inject(self, chaos_type: str, namespace: str) -> ChaosResult:
        signal = _SIGNAL_NAMES.get(chaos_type)
        if signal is None:
            return ChaosResult(
                success=False,
                chaos_id=f"error-{uuid.uuid4().hex[:8]}",
                message=f"Unknown chaos_type: {chaos_type}",
            )

        chaos_id = f"{chaos_type.replace('_', '-')}-{uuid.uuid4().hex[:8]}"
        loop = asyncio.get_running_loop()
        try:
            sandbox = self._sandbox_for(namespace)
            snapshot = await loop.run_in_executor(None, lambda: self._snapshot(sandbox))
            await loop.run_in_executor(
                None, lambda: self._raise_signal(sandbox, signal, chaos_type)
            )
        except Exception as exc:
            logger.exception("linux chaos inject failed", extra={"namespace": namespace})
            try:
                await loop.run_in_executor(
                    None, lambda: self._clear_signal(sandbox, signal)
                )
            except Exception:
                logger.exception("partial linux chaos rollback failed")
            return ChaosResult(
                success=False,
                chaos_id=f"error-{uuid.uuid4().hex[:8]}",
                message=str(exc),
            )

        logger.info(
            "linux chaos injected",
            extra={"chaos_id": chaos_id, "namespace": namespace, "chaos_type": chaos_type},
        )
        return ChaosResult(
            success=True,
            chaos_id=chaos_id,
            message=f"{chaos_type} injected into {namespace}",
            metadata={"snapshot": snapshot},
        )

    async def revert(self, chaos_id: str, namespace: str) -> bool:
        chaos_type = self.chaos_type_from_id(chaos_id)
        signal = _SIGNAL_NAMES.get(chaos_type) if chaos_type else None
        if signal is None:
            logger.warning("cannot resolve linux chaos type", extra={"chaos_id": chaos_id})
            return False

        loop = asyncio.get_running_loop()
        try:
            sandbox = self._sandbox_for(namespace)
            await loop.run_in_executor(
                None, lambda: self._cleanup(sandbox, signal, chaos_type)
            )
        except Exception:
            logger.exception(
                "linux chaos revert failed",
                extra={"chaos_id": chaos_id, "namespace": namespace},
            )
            return False

        logger.info(
            "linux chaos reverted",
            extra={"chaos_id": chaos_id, "namespace": namespace},
        )
        return True

    # --- 헬퍼 ------------------------------------------------------------

    def _sandbox_for(self, namespace: str) -> SandboxRef:
        user_id = namespace.removeprefix("user-")
        return self._sandboxes.reference_for(
            user_id=user_id, namespace=namespace, environment=environments.LINUX
        )

    def _run(self, sandbox: SandboxRef, argv: list[str]) -> str:
        return self._sandboxes.exec_in_sandbox(sandbox, argv)

    @property
    def _workdir(self) -> str:
        return settings.SANDBOX_LINUX_WORKDIR

    def _signal_path(self, signal: str) -> str:
        return f"{self._workdir}/.signals/{signal}"

    def _raise_signal(self, sandbox: SandboxRef, signal: str, chaos_type: str) -> None:
        """supervisor 가 읽을 신호 파일을 만든다.

        이전 실행 표시(.done)를 먼저 지워야 재주입이 동작한다.
        """
        path = self._signal_path(signal)
        argument = {
            DISK_PRESSURE: str(self.DISK_FILL_MB),
            PROCESS_FLOOD: str(self.FLOOD_PROCESS_COUNT),
            CPU_SATURATION: str(self.CPU_BURN_WORKERS),
        }.get(chaos_type, "")

        self._run(sandbox, ["mkdir", "-p", f"{self._workdir}/.signals"])
        self._run(sandbox, ["rm", "-f", f"{path}.done"])
        # printf 로 값을 쓴다. 사용자 입력이 섞이지 않는 고정 인자다.
        self._run(sandbox, ["sh", "-c", f"printf '%s' '{argument}' > '{path}'"])

    def _clear_signal(self, sandbox: SandboxRef, signal: str) -> None:
        path = self._signal_path(signal)
        self._run(sandbox, ["rm", "-f", path, f"{path}.done"])

    def _cleanup(self, sandbox: SandboxRef, signal: str, chaos_type: str) -> None:
        """신호를 지우고 워크로드 흔적을 정리한다. 여러 번 호출해도 안전하다."""
        self._clear_signal(sandbox, signal)

        if chaos_type == DISK_PRESSURE:
            self._run(sandbox, ["rm", "-f", f"{self._workdir}/afterfail-fill.dat"])
            return

        # 프로세스 계열: 워크로드를 종료한다.
        # 패턴을 [a]fterfail- 로 쓰는 이유: pkill -f afterfail- 는 자기 명령줄과도
        # 매치돼 스스로를 먼저 죽이고 정리가 중단된다.
        # 이미 대상이 없으면 pkill 이 1을 반환하므로 실패로 보지 않는다.
        self._run(sandbox, ["sh", "-c", "pkill -f '[a]fterfail-' || true"])

    def _snapshot(self, sandbox: SandboxRef) -> dict:
        """주입 전 상태. 복구가 실패했을 때 무엇이 달라졌는지 알기 위해 남긴다."""
        snapshot = {}
        probes = {
            "processes": ["sh", "-c", "ps -eo pid | wc -l"],
            "zombies": ["sh", "-c", "ps -eo stat | awk '$1 ~ /^Z/' | wc -l"],
            "workdir_used": ["sh", "-c", f"df -P '{self._workdir}' | tail -1 | awk '{{print $5}}'"],
        }
        for key, argv in probes.items():
            try:
                snapshot[key] = self._run(sandbox, argv).strip()
            except Exception:
                logger.warning("linux snapshot field failed", extra={"field": key})
        return snapshot
