from app.core.config import settings
from app.services.chaos_injector import BaseChaosInjector, ChaosMeshInjector, MockChaosInjector
from app.services.mission_service import MissionService
from app.services.scoring_service import ScoringService
from app.services.validation_service import (
    BaseValidationService,
    K8sValidationService,
    MockValidationService,
    PrometheusValidationService,
)


def create_chaos_injector() -> BaseChaosInjector:
    if settings.CHAOS_BACKEND == "mock":
        return MockChaosInjector()
    if settings.CHAOS_BACKEND == "chaos_mesh":
        return ChaosMeshInjector()
    raise ValueError(f"Unknown CHAOS_BACKEND: {settings.CHAOS_BACKEND}")


def create_validation_service() -> BaseValidationService:
    if settings.VALIDATION_BACKEND == "mock":
        return MockValidationService(auto_pass=settings.MOCK_VALIDATION_AUTO_PASS)
    if settings.VALIDATION_BACKEND == "k8s":
        return K8sValidationService()
    if settings.VALIDATION_BACKEND == "prometheus":
        return PrometheusValidationService(settings.PROMETHEUS_URL)
    raise ValueError(f"Unknown VALIDATION_BACKEND: {settings.VALIDATION_BACKEND}")


def create_mission_service() -> MissionService:
    return MissionService(
        chaos_injector=create_chaos_injector(),
        validation_service=create_validation_service(),
        scoring_service=ScoringService(),
    )


_mission_service: MissionService | None = None


def get_mission_service() -> MissionService:
    global _mission_service
    if _mission_service is None:
        _mission_service = create_mission_service()
    return _mission_service
