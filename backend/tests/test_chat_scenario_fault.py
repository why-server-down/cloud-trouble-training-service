"""AI 시나리오 튜터는 실제로 주입된 장애를 기준으로 답한다.

chat.py 가 주입 계획과 다른 자체 표를 써서 probe_failure·crash_loop 를 pod_failure(이미지 문제)로,
cpu_throttle 을 network_latency 로 넘겼다. 튜터(준비 답변·검색·LLM)가 다른 장애를 기준으로 답했다.
"""
from types import SimpleNamespace as NS

import pytest

from app.api.chat import _get_scenario_info


class _DB:
    def __init__(self, scenario):
        self.scenario = scenario

    async def execute(self, _statement):
        return NS(scalar_one_or_none=lambda: self.scenario)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fault_type", "expected"),
    [
        ("probe_failure", "network_latency"),  # readinessProbe 실패 — 예전에는 pod_failure
        ("crash_loop", "crash_loop"),  # 예전에는 pod_failure
        ("cpu_throttle", "cpu_throttle"),  # 예전에는 network_latency
        ("image_pull_error", "pod_failure"),
        ("oom_killed", "memory_stress"),
        ("docker_container_stopped", "docker_container_stopped"),  # 예전에는 pod_failure
        ("linux_disk_pressure", "linux_disk_pressure"),
    ],
)
async def test_tutor_gets_the_injected_chaos_type(fault_type, expected):
    scenario = NS(title="AI 장애", difficulty="expert", fault_type=fault_type)
    title, level, chaos_type = await _get_scenario_info(_DB(scenario), NS(scenario_id="s1"))

    assert (title, level) == ("AI 장애", 4)
    assert chaos_type == expected
