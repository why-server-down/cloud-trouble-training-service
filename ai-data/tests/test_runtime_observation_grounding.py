import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai.runtime_observations import prepare_runtime_context
from prompt_engine import SocraticPromptEngine, TrainingContext


@pytest.mark.parametrize(
    "environment,question,observations,expected,excluded",
    [
        (
            "kubernetes", "Pod readiness 상태를 보고 싶어요",
            {"kubernetes_state": {"pods": [{"name": "web", "ready": False}],
                                  "deployments": [{"name": "web"}],
                                  "services": [{"name": "web"}],
                                  "recent_events": ["Unhealthy"]}},
            {"pods", "readiness"}, {"deployments", "services", "events"},
        ),
        (
            "docker", "컨테이너 exit code를 확인할까요?",
            {"containers": "web exited", "exit": "web 137", "resources": "cpu 2%",
             "networks": "bridge", "volumes": "data", "logs": "oom"},
            {"containers", "exit"}, {"resources", "networks", "volumes", "logs"},
        ),
        (
            "linux", "디스크와 load가 이상해요",
            {"processes": "pid 1", "memory": "free", "disk": "99%", "load": "8.0",
             "sockets": "80", "services": "nginx", "logs": "error"},
            {"disk", "load"}, {"processes", "memory", "sockets", "services", "logs"},
        ),
    ],
)
def test_environment_grounding_selects_only_relevant_summary(
    environment, question, observations, expected, excluded
):
    result = prepare_runtime_context({"observations": observations}, question, environment)
    assert expected <= set(result["observations"])
    assert excluded.isdisjoint(result["observations"])


def test_unavailable_observation_is_explicit_and_prompt_forbids_invention():
    result = prepare_runtime_context({"observations": {}}, "상태를 알려줘", "docker")
    assert result["collection_status"]["state"] == "unavailable"
    assert result["collection_status"]["missing"]
    prompt = SocraticPromptEngine().generate_prompt(
        "상태를 알려줘", training_ctx=TrainingContext(
            environment="docker", collection_status=result["collection_status"]
        )
    )
    assert '"state": "unavailable"' in prompt
    assert "Never invent an uncollected observation" in prompt


def test_command_output_and_logs_are_redacted_before_prompt():
    result = prepare_runtime_context(
        {
            "observations": {"logs": "Authorization: Bearer abcdefghijk"},
            "logs": ["password=hunter2"],
            "recent_user_commands": [{"output_summary": "TOKEN=secret123"}],
        },
        "로그를 확인해줘", "linux",
    )
    serialized = str(result)
    assert "hunter2" not in serialized
    assert "secret123" not in serialized
    assert "abcdefghijk" not in serialized
    assert "***REDACTED***" in serialized
