"""훈련 환경(Environment) 상수 및 검증.

캡스톤2에서 K8s 외에 Docker / Linux 환경을 단계적으로 추가한다.
미션/시나리오/터미널 세션이 어느 환경에서 동작하는지를 이 값으로 구분한다.
"""

from typing import Literal, get_args

from app.core.config import settings

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

# 실제 장애 주입/검증이 **코드에 구현된** 환경. 새 환경 구현체를 붙일 때 추가한다.
# 이건 코드의 사실이라 배포 설정으로 바뀌지 않는다.
IMPLEMENTED_ENVIRONMENTS: tuple[str, ...] = (KUBERNETES, DOCKER, LINUX)


def _resolve_enabled() -> tuple[str, ...]:
    """이 배포에서 실제로 열 환경.

    구현 여부(IMPLEMENTED)와 배포에서 여는지(ENABLED)는 다른 사실이다. 섞으면
    둘 다 거짓이 된다 — 구현이 끝난 환경을 "준비 중" 이라고 말하거나, 반대로
    이 호스트에 올리지 않기로 한 환경을 열어버린다.

    비우면 구현된 환경을 모두 연다. 잘못된 값은 **기동 시점에 실패**시킨다.
    조용히 무시하면 운영자는 열었다고 믿는데 실제로는 닫혀 있다.
    """
    raw = (settings.ENABLED_ENVIRONMENTS or "").strip()
    if not raw:
        return IMPLEMENTED_ENVIRONMENTS

    requested = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    if not requested:
        raise RuntimeError(
            "ENABLED_ENVIRONMENTS 가 비어 있지 않은데 읽어낸 환경이 없습니다. "
            "쉼표로 구분한 환경 이름을 지정하거나 값을 비우세요."
        )

    unknown = [env for env in requested if env not in IMPLEMENTED_ENVIRONMENTS]
    if unknown:
        raise RuntimeError(
            f"ENABLED_ENVIRONMENTS 에 구현되지 않은 환경이 있습니다: {', '.join(unknown)} "
            f"(구현된 환경: {', '.join(IMPLEMENTED_ENVIRONMENTS)})"
        )
    return requested


# 이 배포에서 여는 환경. 요청을 막는 관문은 이 값이다.
ENABLED_ENVIRONMENTS: tuple[str, ...] = _resolve_enabled()

# 환경이 닫혀 있는 이유. 프론트가 문구를 고를 수 있게 계약에 덧붙인다(선택 필드).
NOT_IMPLEMENTED = "not_implemented"   # 코드에 구현이 없다
NOT_DEPLOYED = "not_deployed"         # 구현은 됐지만 이 배포에서 열지 않았다


def is_supported(environment: str) -> bool:
    return environment in SUPPORTED_ENVIRONMENTS


def is_implemented(environment: str) -> bool:
    """코드에 구현이 있는가. 배포에서 열려 있는지와는 다른 질문이다."""
    return environment in IMPLEMENTED_ENVIRONMENTS


def is_enabled(environment: str) -> bool:
    """이 배포에서 쓸 수 있는가. 요청을 막는 기준은 이쪽이다."""
    return environment in ENABLED_ENVIRONMENTS


def validate(environment: str) -> str:
    """지원 목록에 없으면 ValueError. 값은 그대로 반환."""
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(
            f"지원하지 않는 환경입니다: {environment} "
            f"(가능: {', '.join(SUPPORTED_ENVIRONMENTS)})"
        )
    return environment


def assert_implemented(environment: str) -> str:
    """이 배포에서 쓸 수 없는 환경이면 ValueError.

    이름은 호출부 호환을 위해 유지한다. 판정 기준은 ENABLED 다.
    닫힌 이유에 따라 문구를 나눈다 — 구현이 끝난 환경을 "준비 중" 이라고 하면
    거짓말이고, 사용자는 기다리면 열린다고 오해한다.
    """
    validate(environment)
    if environment in ENABLED_ENVIRONMENTS:
        return environment

    available = ", ".join(ENABLED_ENVIRONMENTS) or "없음"
    if environment in IMPLEMENTED_ENVIRONMENTS:
        raise ValueError(
            f"'{environment}' 환경은 이 배포에서 제공되지 않습니다. "
            f"현재 이용 가능: {available}"
        )
    raise ValueError(
        f"'{environment}' 환경은 아직 준비 중입니다. 현재 이용 가능: {available}"
    )


# 환경별로 현재 제공되는 기능. 프론트가 탭을 그릴 때 쓰는 값이며
# label/설명 같은 표시 문구는 프론트 책임이다.
# 환경이 실제로 제공하는 기능. **광고이지 관문이 아니다.**
# 요청을 막는 것은 assert_implemented 이고, 여기 값으로 400 을 내지 않는다.
# 없는 기능을 광고하면 프론트가 열 수 없는 화면을 그리고, 있는 기능을 빼면
# 프론트가 쓸 수 있는 화면을 잠근다. 둘 다 틀린 정보이므로 구현과 함께 갱신한다.
#
# 2026-09-02: docker/linux 가 (static_mission, terminal) 로 남아 있어 낡아 있었다.
#   ai_scenario  : 환경별 fault type 과 프롬프트가 붙었다 (chaos_plan.FAULT_TYPES_BY_ENVIRONMENT)
#   tutor        : tutor_service 가 attempt.environment 를 끝까지 넘긴다 (AI-18~20)
#   observability: 세 환경 모두 관측기가 있다 (runtime_context._OBSERVERS)
#                  단 Grafana 대시보드는 아직 Kubernetes 뿐이다. 여기서 말하는
#                  observability 는 **런타임 관측**이고 대시보드 유무가 아니다.
_CAPABILITIES: dict[str, tuple[str, ...]] = {
    KUBERNETES: ("static_mission", "ai_scenario", "terminal", "tutor", "observability"),
    DOCKER: ("static_mission", "ai_scenario", "terminal", "tutor", "observability"),
    LINUX: ("static_mission", "ai_scenario", "terminal", "tutor", "observability"),
}

AVAILABLE = "available"
PREPARING = "preparing"


def availability() -> list[dict]:
    """지원 환경의 가용 상태 목록. `GET /api/environments` 의 원본이다."""
    items = []
    for environment in SUPPORTED_ENVIRONMENTS:
        enabled = is_enabled(environment)
        item = {
            "id": environment,
            "status": AVAILABLE if enabled else PREPARING,
            "capabilities": list(_CAPABILITIES.get(environment, ())) if enabled else [],
        }
        if not enabled:
            # status 는 프론트와 계약된 두 값뿐이라 늘리지 않는다. 대신 이유를
            # 선택 필드로 덧붙여, 문구를 고를 수 있게 한다(무시해도 동작은 같다).
            item["reason"] = (
                NOT_DEPLOYED if is_implemented(environment) else NOT_IMPLEMENTED
            )
        items.append(item)
    return items


# EnvironmentId(API 계약)와 SUPPORTED_ENVIRONMENTS(런타임 검증)가 갈라지면
# 한쪽만 고쳤을 때 조용히 어긋난다. import 시점에 못 박는다.
assert set(get_args(EnvironmentId)) == set(SUPPORTED_ENVIRONMENTS), (
    "EnvironmentId 와 SUPPORTED_ENVIRONMENTS 가 일치하지 않는다"
)
