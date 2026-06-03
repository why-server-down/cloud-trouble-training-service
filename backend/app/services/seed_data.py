from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Mission

MISSIONS = [
    {
        "name": "사라진 웹페이지",
        "level": 1,
        "description": "Nginx Pod가 ImagePullBackOff 상태입니다. 이미지 이름을 수정하여 Pod를 정상 상태로 복구하세요.",
        "chaos_type": "pod_failure",
        "base_score": 100,
        "time_limit": 1200,
        "hint_penalty": 5,
    },
    {
        "name": "터져버린 쇼핑몰",
        "level": 2,
        "description": "애플리케이션 Pod가 메모리 부족으로 OOMKilled 되고 있습니다. 리소스 제한을 조정하세요.",
        "chaos_type": "memory_stress",
        "base_score": 100,
        "time_limit": 1500,
        "hint_penalty": 7,
    },
    {
        "name": "끊어진 연결고리",
        "level": 3,
        "description": "Service의 selector가 잘못 설정되어 트래픽이 Pod에 도달하지 않습니다. 설정을 수정하세요.",
        "chaos_type": "service_misconfig",
        "base_score": 100,
        "time_limit": 1800,
        "hint_penalty": 7,
    },
    {
        "name": "좀비 서버의 습격",
        "level": 4,
        "description": "Pod는 Running 상태이지만 트래픽을 전혀 받지 못하고 있습니다. Readiness Probe 설정을 확인하고 서비스가 정상 트래픽을 처리할 수 있도록 복구하세요.",
        "chaos_type": "network_latency",
        "base_score": 100,
        "time_limit": 2100,
        "hint_penalty": 10,
    },
]


async def seed_missions(db: AsyncSession):
    result = await db.execute(select(func.count()).select_from(Mission))
    count = result.scalar()
    if count > 0:
        return

    for data in MISSIONS:
        db.add(Mission(**data))
    await db.commit()
    print(f"[Seed] {len(MISSIONS)}개 미션 데이터 생성 완료")
