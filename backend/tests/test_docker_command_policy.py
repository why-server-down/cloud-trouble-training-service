"""Docker 환경 명령 정책 (BE-12).

샌드박스가 privileged DinD 이므로, 사용자가 칠 수 있는 명령을 좁히는 것이
실질적인 방어선이다. 커널 탈출을 시도할 명령을 애초에 만들지 못하게 한다.
"""
import pytest

from app.core.config import settings
from app.services.command_validator import CommandValidator

NS = "user-test"
APP = settings.SANDBOX_TRAINING_CONTAINER
NET = settings.SANDBOX_TRAINING_NETWORK


@pytest.fixture
def validator():
    return CommandValidator()


def _check(validator, command, targets=None):
    return validator.validate_command(command, NS, environment="docker", allowed_targets=targets)


class TestReadCommandsAreAllowed:
    @pytest.mark.parametrize(
        "command",
        [
            "docker ps",
            "docker ps -a",
            f"docker inspect {APP}",
            f"docker logs {APP}",
            f"docker logs --tail 50 {APP}",
            f"docker stats --no-stream {APP}",
            "docker network ls",
            f"docker network inspect {NET}",
            "docker volume ls",
        ],
    )
    def test_allowed(self, validator, command):
        assert _check(validator, command).is_valid


class TestRecoveryCommandsAreAllowed:
    @pytest.mark.parametrize(
        "command",
        [
            f"docker start {APP}",
            f"docker restart {APP}",
            f"docker update --memory 256m {APP}",
            f"docker update --memory=256m {APP}",
            f"docker network connect {NET} {APP}",
            f"docker network disconnect {NET} {APP}",
        ],
    )
    def test_allowed(self, validator, command):
        assert _check(validator, command).is_valid

    def test_flag_value_is_not_treated_as_target(self, validator):
        """`--memory 256m` 의 256m 을 대상 이름으로 오인하면 정상 복구가 막힌다."""
        result = _check(validator, f"docker update --memory 256m {APP}")
        assert result.is_valid, result.error


class TestBlockedCommands:
    @pytest.mark.parametrize(
        "command",
        [
            "docker run -d nginx",
            "docker run --privileged -v /:/host alpine",
            f"docker exec -it {APP} sh",
            "docker system prune -a",
            "docker build -t x .",
            "docker commit x y",
            "docker cp /etc/passwd x:/tmp",
            "docker login",
            "docker swarm init",
            "docker compose up",
        ],
    )
    def test_blocked(self, validator, command):
        result = _check(validator, command)
        assert not result.is_valid
        assert not result.requires_confirmation


class TestDaemonCannotBeRedirected:
    """인수 조건: docker -H, socket mount, privileged run 이 차단된다."""

    @pytest.mark.parametrize(
        "command",
        [
            "docker -H tcp://evil:2375 ps",
            "docker --host tcp://evil:2375 ps",
            "docker --context remote ps",
            "docker --config /tmp/cfg ps",
            "docker -H=tcp://evil:2375 ps",
        ],
    )
    def test_daemon_flags_blocked(self, validator, command):
        result = _check(validator, command)
        assert not result.is_valid
        assert "daemon" in result.error.lower() or "not allowed" in result.error.lower()

    def test_privileged_run_blocked(self, validator):
        assert not _check(validator, "docker run --privileged alpine").is_valid

    def test_socket_mount_blocked(self, validator):
        # run 자체가 막히므로 소켓 마운트에 도달하지 못한다
        assert not _check(
            validator, "docker run -v /var/run/docker.sock:/var/run/docker.sock alpine"
        ).is_valid

    def test_privilege_escalation_via_update_blocked(self, validator):
        result = _check(validator, f"docker update --privileged {APP}")
        assert not result.is_valid


class TestTargetsAreRestrictedToTrainingResources:
    """인수 조건: 모든 target 이름은 허용된 resource set 안에 있어야 한다."""

    def test_unknown_container_rejected(self, validator):
        result = _check(validator, "docker inspect some-other-container")
        assert not result.is_valid
        assert "training resource" in result.error

    def test_unknown_target_rejected_on_recovery(self, validator):
        assert not _check(validator, "docker restart other-app").is_valid

    def test_scenario_can_widen_allowed_targets(self, validator):
        """시나리오가 허용한 리소스는 통과한다."""
        result = _check(validator, "docker restart web-1", targets={"web-1"})
        assert result.is_valid

    def test_scenario_set_replaces_default(self, validator):
        """시나리오가 집합을 주면 기본 훈련 컨테이너는 포함되지 않는다."""
        assert not _check(validator, f"docker restart {APP}", targets={"web-1"}).is_valid

    def test_recovery_requires_a_target(self, validator):
        assert not _check(validator, "docker restart").is_valid


class TestDeleteRequiresConfirmation:
    """인수 조건: delete 계열은 confirmation 계약을 따른다."""

    @pytest.mark.parametrize("command", [f"docker rm {APP}", f"docker kill {APP}"])
    def test_requires_confirmation(self, validator, command):
        result = _check(validator, command)
        assert not result.is_valid
        assert result.requires_confirmation

    def test_confirmed_delete_still_checks_targets(self, validator):
        """확인을 거쳐도 허용되지 않은 대상은 삭제할 수 없다."""
        result = validator.validate_delete(
            "docker rm other-container", NS, confirmed=True, environment="docker"
        )
        assert not result.is_valid

    def test_confirmed_delete_of_training_resource_passes(self, validator):
        result = validator.validate_delete(
            f"docker rm {APP}", NS, confirmed=True, environment="docker"
        )
        assert result.is_valid


class TestShellMetacharactersStillRejected:
    @pytest.mark.parametrize(
        "command",
        [
            "docker ps | grep x",
            "docker ps; rm -rf /",
            "docker ps && docker run alpine",
            "docker ps $(whoami)",
        ],
    )
    def test_rejected(self, validator, command):
        assert not _check(validator, command).is_valid


class TestEnvironmentIsolation:
    def test_kubectl_is_rejected_in_docker_environment(self, validator):
        assert not _check(validator, "kubectl get pods").is_valid

    def test_docker_is_rejected_in_kubernetes_environment(self, validator):
        result = validator.validate_command(
            f"docker ps", NS, environment="kubernetes"
        )
        assert not result.is_valid
        assert "kubectl" in result.error

    def test_unknown_environment_has_no_policy(self, validator):
        result = validator.validate_command("docker ps", NS, environment="linux")
        assert not result.is_valid
