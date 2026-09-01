import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai.scenario_agent import MockScenarioAgent, OpenAIScenarioAgent, ScenarioGenerationInput


ALLOWED = {
    "kubernetes": ["crash_loop", "image_pull_error", "oom_killed"],
    "docker": ["docker_network_disconnect", "docker_container_stopped", "docker_cpu_throttle"],
    "linux": ["linux_disk_pressure", "linux_cpu_saturation", "linux_process_flood"],
}


def _input(environment, allowed=None):
    return ScenarioGenerationInput(
        difficulty="beginner", namespace="user-test", recent_fault_types=[],
        allowed_fault_types=ALLOWED[environment] if allowed is None else allowed,
        environment=environment,
    )


@pytest.mark.parametrize("environment", ["kubernetes", "docker", "linux"])
def test_mock_candidates_stay_in_requested_environment(environment):
    candidates = MockScenarioAgent().generate(_input(environment))
    assert candidates
    assert all(candidate.scenario["environment"] == environment for candidate in candidates)
    assert all(candidate.scenario["fault"]["type"] in ALLOWED[environment] for candidate in candidates)


def test_docker_api_failure_falls_back_only_to_docker(monkeypatch):
    class _FailingOpenAI:
        def __init__(self, **kwargs):
            raise RuntimeError("provider down")

    import openai
    monkeypatch.setattr(openai, "OpenAI", _FailingOpenAI)
    candidates = OpenAIScenarioAgent("test-key").generate(_input("docker"))
    assert all(candidate.scenario["environment"] == "docker" for candidate in candidates)


@pytest.mark.parametrize("environment", ["kubernetes", "docker", "linux"])
def test_empty_allowed_list_is_explicit_error(environment):
    with pytest.raises(ValueError, match="허용 fault type 목록이 비어"):
        MockScenarioAgent().generate(_input(environment, allowed=[]))


def test_wrong_environment_llm_response_falls_back_to_requested_environment():
    agent = OpenAIScenarioAgent("test-key")
    raw = '{"scenarios":[{"environment":"kubernetes","title":"wrong","student_brief":"x","fault":{"type":"crash_loop","target":{"namespace":"{{namespace}}"}},"validation":{"rules":[]}}]}'
    candidates = agent._parse_response(raw, _input("docker"))
    assert all(candidate.scenario["environment"] == "docker" for candidate in candidates)


def test_recent_fault_penalty_is_calculated_with_environment_input():
    gen_input = _input("docker")
    gen_input.recent_fault_types = ["docker_network_disconnect"]
    candidates = MockScenarioAgent().generate(gen_input)
    scores = {candidate.scenario["fault"]["type"]: candidate.score for candidate in candidates}
    assert scores["docker_network_disconnect"] < scores["docker_container_stopped"]
