"""훈련 환경(Environment) 상수 및 검증.

캡스톤2에서 K8s 외에 Docker / Linux 환경을 단계적으로 추가한다.
미션/시나리오/터미널 세션이 어느 환경에서 동작하는지를 이 값으로 구분한다.
"""

from typing import Literal, get_args

KUBERNETES = "kubernetes"
DOCKER = "docker"
LINUX = "linux"

# API 계약에서 environment 를 검증하기 위한 타입.
# Pydantic 이 Literal 을 읽어 잘못된 값을 422 로 거절한다.
# (Literal 은 정적 값이어야 하므로 아래에서 SUPPORTED_ENVIRONMENTS 와 일치를 강제한다)
EnvironmentId = Literal["kubernetes", "docker", "linux"]

# 프론트 환경 탭과 계약되는 enum. (Application 탭은 캡스톤2 스코프에서 제외)
SUPPORTED_ENVIRONMENTS: tuple[str, ...] = (KUBERNETES, DOCKER, LINUX)

DEFAULT_ENVIRONMENT = KUBERNETES

# 실제 장애 주입/검증이 구현된 환경. 새 환경 구현체를 붙일 때마다 여기에 추가한다.
IMPLEMENTED_ENVIRONMENTS: tuple[str, ...] = (KUBERNETES, DOCKER)


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


# 환경별로 현재 제공되는 기능. 프론트가 탭을 그릴 때 쓰는 값이며
# label/설명 같은 표시 문구는 프론트 책임이다.
_CAPABILITIES: dict[str, tuple[str, ...]] = {
    KUBERNETES: ("static_mission", "ai_scenario", "terminal", "tutor", "observability"),
    # Docker 는 고정 미션과 터미널만 제공한다. 없는 기능을 광고하면 프론트가
    # 열 수 없는 화면을 그린다.
    #   ai_scenario  : 시나리오 생성이 Kubernetes fault type 기준이다 (BE-20)
    #   tutor        : RuntimeContext 수집이 Kubernetes 전용이다 (BE-19)
    #   observability: Grafana/Prometheus 대시보드가 K8s 메트릭 기준이다
    DOCKER: ("static_mission", "terminal"),
}

AVAILABLE = "available"
PREPARING = "preparing"


def availability() -> list[dict]:
    """지원 환경의 가용 상태 목록. `GET /api/environments` 의 원본이다."""
    items = []
    for environment in SUPPORTED_ENVIRONMENTS:
        implemented = is_implemented(environment)
        items.append(
            {
                "id": environment,
                "status": AVAILABLE if implemented else PREPARING,
                "capabilities": list(_CAPABILITIES.get(environment, ())) if implemented else [],
            }
        )
    return items


# EnvironmentId(API 계약)와 SUPPORTED_ENVIRONMENTS(런타임 검증)가 갈라지면
# 한쪽만 고쳤을 때 조용히 어긋난다. import 시점에 못 박는다.
assert set(get_args(EnvironmentId)) == set(SUPPORTED_ENVIRONMENTS), (
    "EnvironmentId 와 SUPPORTED_ENVIRONMENTS 가 일치하지 않는다"
)
