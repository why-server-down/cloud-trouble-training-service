import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.environments import DOCKER, KUBERNETES
from app.models import Mission
from app.services.docker_chaos_injector import (
    CONTAINER_STOPPED as DOCKER_CONTAINER_STOPPED,
    CPU_THROTTLE as DOCKER_CPU_THROTTLE,
    NETWORK_DISCONNECT as DOCKER_NETWORK_DISCONNECT,
)

logger = logging.getLogger(__name__)

MISSIONS = [
    {
        "environment": KUBERNETES,
        "name": "사라진 웹페이지",
        "level": 1,
        "description": "Nginx Pod가 ImagePullBackOff 상태입니다. 이미지 이름을 수정하여 Pod를 정상 상태로 복구하세요.",
        "chaos_type": "pod_failure",
        "base_score": 100,
        "time_limit": 1200,
        "hint_penalty": 5,
    },
    {
        "environment": KUBERNETES,
        "name": "터져버린 쇼핑몰",
        "level": 2,
        "description": "애플리케이션 Pod가 메모리 부족으로 OOMKilled 되고 있습니다. 리소스 제한을 조정하세요.",
        "chaos_type": "memory_stress",
        "base_score": 100,
        "time_limit": 1500,
        "hint_penalty": 7,
    },
    {
        "environment": KUBERNETES,
        "name": "끊어진 연결고리",
        "level": 3,
        "description": "Service의 selector가 잘못 설정되어 트래픽이 Pod에 도달하지 않습니다. 설정을 수정하세요.",
        "chaos_type": "service_misconfig",
        "base_score": 100,
        "time_limit": 1800,
        "hint_penalty": 7,
    },
    {
        "environment": KUBERNETES,
        "name": "좀비 서버의 습격",
        "level": 4,
        "description": "Pod는 Running 상태이지만 트래픽을 전혀 받지 못하고 있습니다. Readiness Probe 설정을 확인하고 서비스가 정상 트래픽을 처리할 수 있도록 복구하세요.",
        "chaos_type": "network_latency",
        "base_score": 100,
        "time_limit": 2100,
        "hint_penalty": 10,
    },
    # --- Docker 환경 (BE-14) ---
    # 난이도 순서: 발견하기 쉬운 것부터. 중지된 컨테이너는 docker ps -a 로 바로 보이고,
    # 네트워크 분리는 컨테이너가 running 이라 알아채기 어렵고,
    # CPU 제한은 running 이고 연결도 되는데 느린 것이라 가장 어렵다.
    {
        "environment": DOCKER,
        "name": "멈춰버린 컨테이너",
        "level": 1,
        "description": "훈련용 컨테이너가 실행되지 않고 있습니다. 컨테이너 상태를 확인하고 다시 시작하세요.",
        "chaos_type": DOCKER_CONTAINER_STOPPED,
        "base_score": 100,
        "time_limit": 900,
        "hint_penalty": 5,
    },
    {
        "environment": DOCKER,
        "name": "고립된 컨테이너",
        "level": 2,
        "description": "컨테이너는 실행 중이지만 다른 서비스와 통신하지 못합니다. 네트워크 연결 상태를 확인하고 복구하세요.",
        "chaos_type": DOCKER_NETWORK_DISCONNECT,
        "base_score": 100,
        "time_limit": 1200,
        "hint_penalty": 7,
    },
    {
        "environment": DOCKER,
        "name": "숨 막히는 컨테이너",
        "level": 3,
        "description": "컨테이너는 정상으로 보이지만 응답이 매우 느립니다. 할당된 자원을 점검하고 정상 수준으로 되돌리세요.",
        "chaos_type": DOCKER_CPU_THROTTLE,
        "base_score": 100,
        "time_limit": 1500,
        "hint_penalty": 7,
    },
]


async def seed_missions(db: AsyncSession):
    """미션 시드를 (environment, level) 기준으로 upsert 한다.

    이전에는 미션이 하나라도 있으면 전체를 건너뛰었다. 그래서 Kubernetes 미션이
    이미 있는 DB 에 Docker/Linux 미션을 추가할 방법이 없었다.
    (environment, level) 을 stable key 로 삼으면 재실행해도 중복이 생기지 않고,
    새 환경 시드만 선택적으로 추가된다.
    """
    created = updated = 0

    for data in MISSIONS:
        result = await db.execute(
            select(Mission).where(
                Mission.environment == data["environment"],
                Mission.level == data["level"],
            )
        )
        mission = result.scalar_one_or_none()

        if mission is None:
            db.add(Mission(**data))
            created += 1
            continue

        # 기존 행은 내용만 갱신한다. id 가 바뀌면 진행 중인 attempt 의 FK 가 끊긴다.
        for field, value in data.items():
            setattr(mission, field, value)
        updated += 1

    await db.commit()
    logger.info("mission seed applied", extra={"created": created, "updated": updated})
