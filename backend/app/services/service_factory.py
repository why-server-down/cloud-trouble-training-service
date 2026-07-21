from collections.abc import Callable

from app.core.config import settings
from app.core import environments
from app.services.chaos_injector import BaseChaosInjector, ChaosMeshInjector, MockChaosInjector
from app.services.mission_service import MissionService
from app.services.scenario_service import ScenarioService
from app.services.scoring_service import ScoringService
from app.services.validation_rule_service import ValidationRuleService
from app.services.validation_service import (
    BaseValidationService,
    K8sValidationService,
    MockValidationService,
    PrometheusValidationService,
)


# CHAOS_BACKEND → injector 팩토리 레지스트리.
# docker/linux 환경 구현체가 생기면 (environment, backend) 조합 키로 확장한다.
_INJECTOR_FACTORIES: dict[str, Callable[[], BaseChaosInjector]] = {
    "mock": MockChaosInjector,
    "chaos_mesh": ChaosMeshInjector,
}

# VALIDATION_BACKEND → 검증 서비스 팩토리 레지스트리.
_VALIDATION_FACTORIES: dict[str, Callable[[], BaseValidationService]] = {
    "mock": lambda: MockValidationService(auto_pass=settings.MOCK_VALIDATION_AUTO_PASS),
    "k8s": K8sValidationService,
    "prometheus": lambda: PrometheusValidationService(settings.PROMETHEUS_URL),
}


def create_chaos_injector(
    environment: str = environments.DEFAULT_ENVIRONMENT,
) -> BaseChaosInjector:
    # 현재 kubernetes 환경만 구현됨. docker/linux injector는 후속 브랜치에서 분기 추가.
    environments.assert_implemented(environment)
    factory = _INJECTOR_FACTORIES.get(settings.CHAOS_BACKEND)
    if factory is None:
        raise ValueError(f"Unknown CHAOS_BACKEND: {settings.CHAOS_BACKEND}")
    return factory()


def create_validation_service(
    environment: str = environments.DEFAULT_ENVIRONMENT,
) -> BaseValidationService:
    # 현재 kubernetes 환경만 구현됨. docker/linux 검증기는 후속 브랜치에서 분기 추가.
    environments.assert_implemented(environment)
    factory = _VALIDATION_FACTORIES.get(settings.VALIDATION_BACKEND)
    if factory is None:
        raise ValueError(f"Unknown VALIDATION_BACKEND: {settings.VALIDATION_BACKEND}")
    return factory()


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


def create_scenario_service() -> ScenarioService:
    return ScenarioService(
        chaos_injector=create_chaos_injector(),
        scoring_service=ScoringService(),
        validation_rule_service=ValidationRuleService(settings.PROMETHEUS_URL),
    )


_scenario_service: ScenarioService | None = None


def get_scenario_service() -> ScenarioService:
    global _scenario_service
    if _scenario_service is None:
        _scenario_service = create_scenario_service()
    return _scenario_service
