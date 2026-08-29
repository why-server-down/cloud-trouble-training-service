"""환경·백엔드 조합으로 서비스 구현체를 고른다.

레지스트리 키가 `(environment, configured_backend)` 인 이유: 같은 백엔드 이름이라도
환경마다 구현체가 다르다. docker/linux 구현체가 붙을 때 이 표에 줄만 추가하면 되고,
등록되지 않은 조합은 kubernetes 로 조용히 대체되지 않고 실패한다.
"""
from collections.abc import Callable

from app.core import environments
from app.core.config import settings
from app.services.chaos_injector import BaseChaosInjector, ChaosMeshInjector, MockChaosInjector
from app.services.docker_chaos_injector import DockerChaosInjector
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

K8S = environments.KUBERNETES
DOCKER = environments.DOCKER

# (environment, CHAOS_BACKEND) → injector 팩토리
# CHAOS_BACKEND 는 "mock 이냐 실제냐"를 고르는 값이다. Docker 환경은 Chaos Mesh 를
# 쓰지 않고 DinD 안에서 docker CLI 로 주입하지만, 실제 주입이라는 점에서 같은 키를 쓴다.
_INJECTOR_FACTORIES: dict[tuple[str, str], Callable[[], BaseChaosInjector]] = {
    (K8S, "mock"): lambda: MockChaosInjector(environment=K8S),
    (K8S, "chaos_mesh"): ChaosMeshInjector,
    (DOCKER, "mock"): lambda: MockChaosInjector(environment=DOCKER),
    (DOCKER, "chaos_mesh"): DockerChaosInjector,
}

# (environment, VALIDATION_BACKEND) → 검증 서비스 팩토리
_VALIDATION_FACTORIES: dict[tuple[str, str], Callable[[], BaseValidationService]] = {
    (K8S, "mock"): lambda: MockValidationService(
        auto_pass=settings.MOCK_VALIDATION_AUTO_PASS, environment=K8S
    ),
    (K8S, "k8s"): K8sValidationService,
    (K8S, "prometheus"): lambda: PrometheusValidationService(settings.PROMETHEUS_URL),
}


def _lookup(
    registry: dict, environment: str, backend: str, kind: str
) -> Callable:
    environments.assert_implemented(environment)
    factory = registry.get((environment, backend))
    if factory is None:
        available = sorted({env for env, _ in registry if env == environment})
        raise ValueError(
            f"'{environment}' 환경에 등록된 {kind} 구현이 없습니다 "
            f"(backend={backend}). 등록된 조합: "
            + ", ".join(f"{env}/{be}" for env, be in sorted(registry))
            + (f" / 이 환경의 사용 가능한 backend 없음" if not available else "")
        )
    return factory


def create_chaos_injector(
    environment: str = environments.DEFAULT_ENVIRONMENT,
) -> BaseChaosInjector:
    factory = _lookup(_INJECTOR_FACTORIES, environment, settings.CHAOS_BACKEND, "장애 주입기")
    return factory()


def create_validation_service(
    environment: str = environments.DEFAULT_ENVIRONMENT,
) -> BaseValidationService:
    factory = _lookup(
        _VALIDATION_FACTORIES, environment, settings.VALIDATION_BACKEND, "검증 서비스"
    )
    return factory()


def create_mission_service() -> MissionService:
    # 환경별 서비스 인스턴스를 따로 두지 않는다. 서비스는 상태를 갖지 않고,
    # attempt 의 environment 로 그때그때 구현체를 조회한다.
    return MissionService(
        injector_for=create_chaos_injector,
        validation_for=create_validation_service,
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
        injector_for=create_chaos_injector,
        scoring_service=ScoringService(),
        validation_rule_service=ValidationRuleService(settings.PROMETHEUS_URL),
    )


_scenario_service: ScenarioService | None = None


def get_scenario_service() -> ScenarioService:
    global _scenario_service
    if _scenario_service is None:
        _scenario_service = create_scenario_service()
    return _scenario_service
