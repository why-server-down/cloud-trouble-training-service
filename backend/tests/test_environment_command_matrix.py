"""환경별 명령 allow/block 매트릭스 (BE-24).

환경마다 정책 파일이 따로 있고 각각의 테스트도 따로 있다. 그러나
"한 환경에서 허용된 명령이 다른 환경으로 새지 않는다"는 성질은 어느 파일에서도
확인하지 않았다. 이 파일은 환경을 가로질러 한 표로 검증한다.

기대값 세 가지:
  allow   - 그대로 실행 가능
  block   - 거절(확인해도 통과하지 못한다)
  confirm - 정책상 유효하지만 사용자 확인이 필요하다
"""
import pytest

from app.core.environments import DOCKER, IMPLEMENTED_ENVIRONMENTS, KUBERNETES, LINUX
from app.services.command_validator import CommandValidator

NAMESPACE = "user-matrix"

ALLOW = "allow"
BLOCK = "block"
CONFIRM = "confirm"

# (명령, {환경: 기대값}) — 명시하지 않은 환경은 block 으로 본다.
MATRIX = [
    # 환경 고유의 정상 명령
    ("kubectl get pods", {KUBERNETES: ALLOW}),
    ("kubectl describe pod nginx", {KUBERNETES: ALLOW}),
    ("kubectl delete pod nginx", {KUBERNETES: CONFIRM}),
    ("docker ps", {DOCKER: ALLOW}),
    ("docker restart training-app", {DOCKER: ALLOW}),
    ("docker rm training-app", {DOCKER: CONFIRM}),
    ("ps aux", {LINUX: ALLOW}),
    ("cat /proc/meminfo", {LINUX: ALLOW}),
    ("kill 4321", {LINUX: CONFIRM}),
    # 다른 환경의 바이너리 — 정책이 다르면 실행 자체가 막혀야 한다
    ("kubectl get pods -n kube-system", {}),
    ("docker run -it alpine sh", {}),
    ("rm -rf /", {}),
    ("cat /etc/shadow", {}),
    ("chmod 777 /etc", {}),
    ("curl http://169.254.169.254/", {}),
]


def _expected(environment: str, expectations: dict) -> str:
    return expectations.get(environment, BLOCK)


def _actual(validator: CommandValidator, command: str, environment: str) -> str:
    result = validator.validate_command(command, NAMESPACE, environment=environment)
    if result.is_valid:
        return ALLOW
    return CONFIRM if result.requires_confirmation else BLOCK


@pytest.fixture
def validator():
    return CommandValidator()


class TestMatrix:
    @pytest.mark.parametrize("command,expectations", MATRIX)
    @pytest.mark.parametrize("environment", IMPLEMENTED_ENVIRONMENTS)
    def test_cell(self, validator, command, expectations, environment):
        assert _actual(validator, command, environment) == _expected(environment, expectations)

    def test_every_implemented_environment_is_covered(self):
        """새 환경을 열면 이 표도 같이 채워야 한다."""
        covered = {env for _, expectations in MATRIX for env in expectations}
        assert covered == set(IMPLEMENTED_ENVIRONMENTS)


class TestNoCrossEnvironmentLeak:
    """한 환경에서 통과한 명령은 다른 환경에서 통과하지 못한다."""

    @pytest.mark.parametrize(
        "command,home",
        [
            ("kubectl get pods", KUBERNETES),
            ("kubectl logs nginx", KUBERNETES),
            ("docker ps", DOCKER),
            ("docker logs training-app", DOCKER),
            ("ps aux", LINUX),
            ("df -h", LINUX),
        ],
    )
    def test_allowed_command_does_not_leak(self, validator, command, home):
        assert _actual(validator, command, home) == ALLOW
        for other in IMPLEMENTED_ENVIRONMENTS:
            if other == home:
                continue
            assert _actual(validator, command, other) == BLOCK, (
                f"{command!r} 가 {other} 환경에서도 통과한다"
            )


class TestSharedGuards:
    """환경과 무관하게 지켜져야 하는 방어선."""

    SHELL_INJECTIONS = [
        "kubectl get pods | grep x",
        "ps aux > /tmp/out",
        "docker ps; rm -rf /",
        "df -h && cat /etc/passwd",
        "ps `whoami`",
        "docker ps $(whoami)",
    ]

    @pytest.mark.parametrize("command", SHELL_INJECTIONS)
    @pytest.mark.parametrize("environment", IMPLEMENTED_ENVIRONMENTS)
    def test_shell_metacharacters_are_rejected_everywhere(
        self, validator, command, environment
    ):
        result = validator.validate_command(command, NAMESPACE, environment=environment)
        assert not result.is_valid
        assert not result.requires_confirmation

    @pytest.mark.parametrize("environment", IMPLEMENTED_ENVIRONMENTS)
    def test_confirmation_never_bypasses_the_policy(self, validator, environment):
        """확인 플래그는 정책을 넘지 못한다.

        확인이 필요한 명령을 확인하면 실행되지만, 애초에 정책이 거절하는 명령은
        확인해도 거절된다. 이 구분이 무너지면 사용자가 '확인'만 눌러
        정책 밖 대상을 건드릴 수 있다.
        """
        forbidden = {
            KUBERNETES: "kubectl delete pod nginx -n kube-system",
            DOCKER: "docker rm postgres-prod",
            LINUX: "rm -rf /etc",
        }[environment]
        confirmed = validator.validate_delete(
            forbidden, NAMESPACE, confirmed=True, environment=environment
        )
        assert not confirmed.is_valid

    def test_unknown_environment_has_no_policy(self, validator):
        result = validator.validate_command("kubectl get pods", NAMESPACE, environment="windows")
        assert not result.is_valid
        assert "정책이 없습니다" in result.error
