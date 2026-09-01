import sys
import json
from copy import deepcopy
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai.scenario_agent import MockScenarioAgent, OpenAIScenarioAgent, ScenarioGenerationInput
from app.services.chaos_plan import ChaosPlanCompiler, allowed_fault_types


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
    assert candidates[0].rejected is True
    assert "schema_error" in candidates[0].rejection_reason


def test_recent_fault_penalty_is_calculated_with_environment_input():
    gen_input = _input("docker")
    gen_input.recent_fault_types = ["docker_network_disconnect"]
    candidates = MockScenarioAgent().generate(gen_input)
    scores = {candidate.scenario["fault"]["type"]: candidate.score for candidate in candidates}
    assert scores["docker_network_disconnect"] < scores["docker_container_stopped"]


def _scenario(environment="docker"):
    return MockScenarioAgent().generate(_input(environment))[0].scenario


def _parse(scenario, environment="docker"):
    return OpenAIScenarioAgent("test-key")._parse_response(
        json.dumps({"scenarios": [scenario]}, ensure_ascii=False), _input(environment)
    )[0]


@pytest.mark.parametrize(
    "mutator,reason",
    [
        (lambda scenario: scenario.update(environment="linux"), "wrong_environment"),
        (lambda scenario: scenario["fault"].update(type="unknown_fault"), "unknown_fault"),
        (lambda scenario: scenario.update(unexpected="value"), "schema_error"),
        (lambda scenario: scenario.pop("validation"), "schema_error"),
        (lambda scenario: scenario.update(student_brief="원인은 CPU 제한입니다. docker update로 복구하세요."), "schema_error"),
        (lambda scenario: scenario["scoring"].update(time_limit_seconds=10), "schema_error"),
    ],
)
def test_invalid_candidate_records_reject_reason(mutator, reason):
    scenario = deepcopy(_scenario())
    mutator(scenario)
    candidate = _parse(scenario)
    assert candidate.rejected is True
    assert reason in candidate.rejection_reason


def test_invalid_json_is_rejected_with_reason():
    candidate = OpenAIScenarioAgent("test-key")._parse_response("{broken", _input("docker"))[0]
    assert candidate.rejected is True
    assert candidate.rejection_reason.startswith("invalid_json")


@pytest.mark.parametrize("environment", ["kubernetes", "docker", "linux"])
@pytest.mark.parametrize("difficulty", ["beginner", "intermediate", "advanced", "expert"])
def test_every_fixture_strict_parses_and_compiles(environment, difficulty):
    gen_input = ScenarioGenerationInput(
        difficulty=difficulty, namespace="user-test", recent_fault_types=[],
        allowed_fault_types=sorted(allowed_fault_types(environment)), environment=environment,
    )
    compiler = ChaosPlanCompiler()
    for fixture_candidate in MockScenarioAgent().generate(gen_input):
        parsed = OpenAIScenarioAgent("test-key")._parse_response(
            json.dumps({"scenarios": [fixture_candidate.scenario]}, ensure_ascii=False), gen_input
        )[0]
        assert parsed.rejected is False, parsed.rejection_reason
        compiler.compile(parsed.scenario, "user-test", environment=environment)


def test_scenario_prompt_declares_environment_contracts_and_forbids_commands():
    prompt = (Path(__file__).resolve().parents[1] / "prompts" / "scenario_gen.md").read_text()
    for section in ("## Kubernetes", "## Docker", "## Linux", "## Exact candidate schema"):
        assert section in prompt
    for fault in ("docker_network_disconnect", "linux_disk_pressure", "crash_loop"):
        assert fault in prompt
    assert "declarative `fault.parameters` only" in prompt
    assert "Never generate shell scripts" in prompt
