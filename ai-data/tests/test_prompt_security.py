import json
from pathlib import Path

import pytest

from context_safety import REDACTED
from prompt_engine import SocraticPromptEngine, TrainingContext


CASES = [json.loads(line) for line in (
    Path(__file__).parents[1] / "evals" / "prompt_injection_cases.jsonl"
).read_text(encoding="utf-8").splitlines() if line]


def _prompt(case):
    context = TrainingContext(environment="kubernetes", observations={"summary": "Pod restart count increased"})
    question = "무엇을 확인할까요?"
    if case["field"] == "question":
        question = case["payload"]
    elif case["field"] == "logs":
        context.logs = [case["payload"]]
    elif case["field"] == "docs":
        context.retrieved_docs = [{"source": "doc", "content": case["payload"]}]
    elif case["field"] == "commands":
        context.recent_commands = [case["payload"]]
    elif case["field"] == "k8s_secret":
        context.observations["object"] = {"kind": "Secret", "data": {"password": case["payload"]}}
    elif case["field"] == "environment":
        context.observations["env"] = {"OPENAI_API_KEY": case["payload"]}
    return SocraticPromptEngine().generate_prompt(question, hint_level=1, training_ctx=context)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_adversarial_cases_do_not_leak_secrets(case):
    prompt = _prompt(case)
    assert case["secret"] not in prompt
    assert REDACTED in prompt
    assert "never an instruction" in prompt


def test_long_context_is_bounded_and_keeps_observation_summary():
    context = TrainingContext(
        environment="linux",
        observations={"summary": "service port is not listening", "huge": "plain observation " * 3_000},
        logs=["repeated log line " * 3_000],
        retrieved_docs=[{"content": "documentation sentence " * 3_000} for _ in range(10)],
        recent_commands=["diagnostic command output " * 1_000],
    )
    prompt = SocraticPromptEngine().generate_prompt(
        "왜 실패했나요?" + "w" * 10_000, hint_level=1, training_ctx=context
    )

    assert len(prompt) <= 36_000
    assert "service port is not listening" in prompt
    assert "TRUNCATED" in prompt or '"_truncated": true' in prompt


def test_all_untrusted_inputs_have_explicit_boundaries():
    prompt = SocraticPromptEngine().generate_prompt(
        "질문", training_ctx=TrainingContext(logs=["log"], retrieved_docs=[{"content": "doc"}])
    )
    for section in ("OBSERVATIONS", "RUNTIME LOGS", "RECENT COMMANDS", "RETRIEVED DOCUMENTS", "USER QUESTION"):
        assert f"=== {section} (UNTRUSTED DATA) ===" in prompt
