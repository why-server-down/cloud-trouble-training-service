"""훈련 환경(Environment) 상수 및 검증.

캡스톤2에서 K8s 외에 Docker / Linux 환경을 단계적으로 추가한다.
미션/시나리오/터미널 세션이 어느 환경에서 동작하는지를 이 값으로 구분한다.
"""

KUBERNETES = "kubernetes"
DOCKER = "docker"
LINUX = "linux"

# 프론트 환경 탭과 계약되는 enum. (Application 탭은 캡스톤2 스코프에서 제외)
SUPPORTED_ENVIRONMENTS: tuple[str, ...] = (KUBERNETES, DOCKER, LINUX)

DEFAULT_ENVIRONMENT = KUBERNETES

# 실제 장애 주입/검증이 구현된 환경. 새 환경 구현체를 붙일 때마다 여기에 추가한다.
IMPLEMENTED_ENVIRONMENTS: tuple[str, ...] = (KUBERNETES,)


def is_supported(environment: str) -> bool:
    return environment in SUPPORTED_ENVIRONMENTS


def is_implemented(environment: str) -> bool:
    return environment in IMPLEMENTED_ENVIRONMENTS


def validate(environment: str) -> str:
    """지원 목록에 없으면 ValueError. 값은 그대로 반환."""
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(
            f"지원하지 않는 환경입니다: {environment} "
            f"(가능: {', '.join(SUPPORTED_ENVIRONMENTS)})"
        )
    return environment


def assert_implemented(environment: str) -> str:
    """지원은 하지만 아직 구현 전인 환경이면 ValueError."""
    validate(environment)
    if environment not in IMPLEMENTED_ENVIRONMENTS:
        raise ValueError(
            f"'{environment}' 환경은 아직 준비 중입니다. "
            f"현재 이용 가능: {', '.join(IMPLEMENTED_ENVIRONMENTS)}"
        )
    return environment
