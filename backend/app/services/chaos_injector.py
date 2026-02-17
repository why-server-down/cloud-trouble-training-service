import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChaosResult:
    success: bool
    chaos_id: str
    message: str


class BaseChaosInjector(ABC):
    @abstractmethod
    async def inject(self, chaos_type: str, namespace: str) -> ChaosResult:
        pass

    @abstractmethod
    async def revert(self, chaos_id: str) -> bool:
        pass


class MockChaosInjector(BaseChaosInjector):
    """Docker 개발 환경용 Mock 구현. 실제 장애 주입 없이 시뮬레이션."""

    def __init__(self, delay: float = 0.5):
        self._delay = delay
        self._active_chaos: dict[str, dict] = {}

    async def inject(self, chaos_type: str, namespace: str) -> ChaosResult:
        await asyncio.sleep(self._delay)
        chaos_id = f"mock-{chaos_type}-{uuid.uuid4().hex[:8]}"
        self._active_chaos[chaos_id] = {"type": chaos_type, "namespace": namespace}
        print(f"[MOCK] Chaos injected: {chaos_type} -> {namespace} (id={chaos_id})")
        return ChaosResult(
            success=True,
            chaos_id=chaos_id,
            message=f"[MOCK] {chaos_type} injected into {namespace}",
        )

    async def revert(self, chaos_id: str) -> bool:
        if chaos_id in self._active_chaos:
            del self._active_chaos[chaos_id]
            print(f"[MOCK] Chaos reverted: {chaos_id}")
            return True
        return False
