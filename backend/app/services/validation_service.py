from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_resolved: bool
    message: str
    details: dict | None = field(default=None)


class BaseValidationService(ABC):
    @abstractmethod
    async def check_resolution(self, chaos_type: str, namespace: str) -> ValidationResult:
        pass


class MockValidationService(BaseValidationService):
    """Docker 개발 환경용 Mock 구현. debug/resolve 엔드포인트로 수동 해결 트리거."""

    def __init__(self, auto_pass: bool = False):
        self._auto_pass = auto_pass
        self._resolved_namespaces: set[str] = set()

    async def check_resolution(self, chaos_type: str, namespace: str) -> ValidationResult:
        if self._auto_pass or namespace in self._resolved_namespaces:
            return ValidationResult(
                is_resolved=True,
                message="장애가 해결되었습니다!",
            )
        return ValidationResult(
            is_resolved=False,
            message=f"[MOCK] {chaos_type} 장애가 아직 해결되지 않았습니다.",
        )

    def mark_resolved(self, namespace: str):
        self._resolved_namespaces.add(namespace)

    def reset(self, namespace: str):
        self._resolved_namespaces.discard(namespace)
