"""LLM 을 못 쓸 때 나가는 준비 답변이 실제 주입된 장애와 힌트 레벨 규칙을 지키는지."""
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai.tutor_service import _MOCK_HINTS, TutorService
from app.services.command_validator import CommandValidator, LinuxPolicy
from app.services.docker_chaos_injector import DockerChaosInjector
from app.services.linux_chaos_injector import LinuxChaosInjector

_LINUX_COMMANDS = (
    LinuxPolicy.READ_COMMANDS | LinuxPolicy.FILE_READ_COMMANDS | LinuxPolicy.RECOVERY_COMMANDS
)
# 상태를 바꾸는 명령. 레벨 2 이하에는 나오면 안 된다.
_RECOVERY = {
    "kubernetes": re.compile(r"^kubectl (set|patch|rollout undo|delete|edit|scale|apply|create)\b"),
    "docker": re.compile(r"^docker (start|restart|stop|update|unpause|rm|kill|network (connect|disconnect))\b"),
    "linux": re.compile(r"^(kill|pkill|rm|truncate)\b"),
}
_CASES = [
    (env, chaos, level)
    for env, scenarios in _MOCK_HINTS.items()
    for chaos, hints in scenarios.items()
    for level in hints
]


def _commands(environment: str, text: str) -> list[str]:
    """백틱 안의 내용 중 그 환경 명령으로 시작하는 것만 뽑는다."""
    found = []
    for snippet in re.findall(r"`([^`]+)`", text):
        first = snippet.split()[0]
        if environment == "linux":
            if first in _LINUX_COMMANDS:
                found.append(snippet)
        elif first == ("kubectl" if environment == "kubernetes" else "docker"):
            found.append(snippet)
    return found


def _hint(environment, chaos_type, level):
    return TutorService()._mock_response("질문", level, chaos_type, environment)


def test_every_environment_has_all_levels_and_a_default():
    for scenarios in _MOCK_HINTS.values():
        assert "default" in scenarios
        for hints in scenarios.values():
            assert set(hints) == {0, 1, 2, 3}


@pytest.mark.parametrize("environment, injector", [
    ("docker", DockerChaosInjector), ("linux", LinuxChaosInjector),
])
def test_hints_cover_exactly_the_injected_chaos_types(environment, injector):
    supported = injector.__new__(injector).supported_chaos_types()
    assert set(_MOCK_HINTS[environment]) - {"default"} == set(supported)


@pytest.mark.parametrize("environment, chaos_type, level", _CASES)
def test_level_rules_follow_socratic_prompt(environment, chaos_type, level):
    commands = _commands(environment, _hint(environment, chaos_type, level))
    if level <= 1:
        assert commands == []
    elif level == 2:
        assert commands
        assert not [c for c in commands if _RECOVERY[environment].match(c)]
    elif chaos_type != "default":
        assert any(_RECOVERY[environment].match(c) for c in commands)


@pytest.mark.parametrize("environment, chaos_type, level", _CASES)
def test_commands_pass_the_environment_command_policy(environment, chaos_type, level):
    """튜터가 알려준 명령을 그대로 치면 터미널이 받아줘야 한다."""
    validator = CommandValidator()
    for command in _commands(environment, _hint(environment, chaos_type, level)):
        if "<" in command:  # `<이름>` 같은 자리표시자는 사용자가 채운다
            continue
        result = validator.validate_command(command, "user-test", environment)
        assert result.is_valid or result.requires_confirmation, (command, result.error)


@pytest.mark.parametrize("environment, chaos_type, level", _CASES)
def test_no_cross_environment_or_tty_commands(environment, chaos_type, level):
    text = _hint(environment, chaos_type, level)
    assert "kubectl edit" not in text  # 터미널에 TTY 가 없다
    assert "kubectl top" not in text   # 학생에게 금지된 명령
    if environment != "kubernetes":
        assert "kubectl" not in text and "클러스터" not in text
    if environment != "docker":
        assert "docker " not in text


def test_pod_failure_fix_restores_the_image_instead_of_deleting_pods():
    text = _hint("kubernetes", "pod_failure", 3)
    assert "nginx:wrongtag" in text
    assert "kubectl delete" not in text
    assert "kubectl set image deployment/nginx" in text or "kubectl rollout undo" in text
    assert "사라지" not in _hint("kubernetes", "pod_failure", 0)


def test_memory_stress_fix_raises_the_limit_instead_of_restarting():
    text = _hint("kubernetes", "memory_stress", 3)
    assert "kubectl set resources deployment/nginx --limits=memory=128Mi" in text


def test_service_misconfig_fix_targets_only_the_service_selector():
    text = _hint("kubernetes", "service_misconfig", 3)
    assert "kubectl patch svc webapp-svc" in text
    assert "Pod label 수정" not in text and "kubectl label" not in text


def test_network_latency_fix_uses_non_interactive_patch():
    text = _hint("kubernetes", "network_latency", 3)
    assert "--type=json" in text and "readinessProbe" in text


@pytest.mark.parametrize("environment", ["docker", "linux"])
def test_kubernetes_chaos_type_in_other_environment_falls_back_to_that_environment(environment):
    """AI 시나리오는 모르는 fault 를 pod_failure 로 넘긴다. 그래도 kubectl 을 안내하면 안 된다."""
    for level in range(4):
        text = _hint(environment, "pod_failure", level)
        assert text == _MOCK_HINTS[environment]["default"][level]
        assert "kubectl" not in text
