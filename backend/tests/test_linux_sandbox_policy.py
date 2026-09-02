"""Linux 샌드박스와 명령 정책 (BE-16).

허용 명령 목록은 **실제 컨테이너에서 동작하는 것만** 넣는다. 되지 않는 명령을
목록에 두면 사용자가 그것을 정답으로 착각한다.
"""
import pytest

from app.core import environments
from app.core.config import settings
from app.services.command_validator import CommandValidator, LinuxPolicy
from app.services.sandbox_service import SandboxService

NS = "user-test"


@pytest.fixture
def validator():
    return CommandValidator()


def _check(validator, command):
    return validator.validate_command(command, NS, environment=environments.LINUX)


class TestAllowedObservationCommands:
    @pytest.mark.parametrize(
        "command",
        [
            "ps aux", "free -m", "df -h", "top -b -n1", "uptime",
            "ss -tan", "netstat -tan", "iostat", "lsof -n", "pstree",
        ],
    )
    def test_allowed(self, validator, command):
        assert _check(validator, command).is_valid


class TestCommandsThatDoNotWorkInContainers:
    """실측으로 동작하지 않는 명령은 목록에 없다.

    journalctl/systemctl 은 systemd 부재, dmesg 는 커널 링 버퍼 접근 제한 때문에
    어떤 이미지에서도 동작하지 않는다.
    """

    @pytest.mark.parametrize("command", ["journalctl -n 5", "dmesg", "systemctl status"])
    def test_not_offered(self, validator, command):
        assert not _check(validator, command).is_valid

    def test_policy_does_not_list_them(self):
        policy = LinuxPolicy()
        offered = policy.READ_COMMANDS | policy.FILE_READ_COMMANDS | policy.RECOVERY_COMMANDS
        for command in ("journalctl", "systemctl", "dmesg"):
            assert command not in offered


class TestFilePathRestriction:
    @pytest.mark.parametrize(
        "command",
        ["cat /proc/meminfo", "cat /sys/fs/cgroup/memory.max", "ls /tmp/afterfail"],
    )
    def test_allowed_paths(self, validator, command):
        assert _check(validator, command).is_valid

    @pytest.mark.parametrize(
        "command",
        ["cat /etc/shadow", "cat /etc/passwd", "ls /root", "head /var/log/auth.log"],
    )
    def test_blocked_paths(self, validator, command):
        result = _check(validator, command)
        assert not result.is_valid
        assert "Allowed paths" in result.error

    def test_path_traversal_blocked(self, validator):
        result = _check(validator, "cat ../../etc/passwd")
        assert not result.is_valid
        assert "escape" in result.error


class TestShellEscapeIsNotAvailable:
    @pytest.mark.parametrize(
        "command",
        ["sh -c whoami", "bash -c id", "curl http://evil", "wget http://evil", "nc -l 4444"],
    )
    def test_blocked(self, validator, command):
        assert not _check(validator, command).is_valid

    @pytest.mark.parametrize(
        "command", ["ps aux | grep x", "ps; whoami", "ps && id", "ps $(whoami)"],
    )
    def test_shell_metacharacters_blocked(self, validator, command):
        assert not _check(validator, command).is_valid


class TestRecoveryCommands:
    def test_signal_requires_confirmation(self, validator):
        result = _check(validator, "kill 4242")
        assert not result.is_valid
        assert result.requires_confirmation

    def test_pid_1_is_rejected_immediately(self, validator):
        """PID 1 은 샌드박스 자체다. 확인해도 통과할 수 없으므로 바로 거절한다."""
        result = _check(validator, "kill 1")
        assert not result.is_valid
        assert not result.requires_confirmation

    def test_non_training_process_name_rejected(self, validator):
        result = _check(validator, "pkill sshd")
        assert not result.is_valid
        assert not result.requires_confirmation

    def test_training_process_name_allowed(self, validator):
        result = _check(validator, "pkill afterfail-hog")
        assert result.requires_confirmation

    def test_rm_outside_training_dir_rejected_immediately(self, validator):
        """확인해도 통과 못 할 명령을 '확인 필요'로 답하면 잘못된 방향으로 유도한다."""
        result = _check(validator, "rm -rf /")
        assert not result.is_valid
        assert not result.requires_confirmation
        assert "Allowed paths" in result.error

    def test_rm_inside_training_dir_requires_confirmation(self, validator):
        result = _check(validator, "rm /tmp/afterfail/big.dat")
        assert result.requires_confirmation

    def test_confirmed_rm_still_checks_path(self, validator):
        result = validator.validate_delete(
            "rm -rf /etc", NS, confirmed=True, environment=environments.LINUX
        )
        assert not result.is_valid


class TestLinuxSandboxSpec:
    def _pod(self):
        class _FakeCoreApi:
            def __init__(self):
                self.created = []
                self.config_maps = []

            def read_namespaced_pod(self, name, namespace):
                from kubernetes.client.exceptions import ApiException

                raise ApiException(status=404)

            def create_namespaced_pod(self, namespace, body):
                self.created.append(body)

            # supervisor 스크립트는 ConfigMap 으로 들어간다
            def read_namespaced_config_map(self, name, namespace):
                from kubernetes.client.exceptions import ApiException

                raise ApiException(status=404)

            def create_namespaced_config_map(self, namespace, body):
                self.config_maps.append(body)

        api = _FakeCoreApi()
        service = SandboxService(
            core_api=api, rbac_api=object(), networking_api=object(), k8s_setup=object()
        )
        container = service._provision_linux("user-1", "sandbox-1", {})
        assert container == SandboxService.LINUX_CONTAINER
        return api.created[0]

    def test_does_not_share_host_namespaces(self):
        """장애는 컨테이너 cgroup 범위 안에서만 재현된다."""
        spec = self._pod().spec
        assert spec.host_pid is False
        assert spec.host_network is False
        assert spec.host_ipc is False

    def test_does_not_mount_service_account_token(self):
        assert self._pod().spec.automount_service_account_token is False

    def test_supervisor_is_the_main_process(self):
        """exec 으로 띄운 워크로드는 살아남지 않는다. PID 1 이 대신 띄운다."""
        container = self._pod().spec.containers[0]
        assert SandboxService.LINUX_SUPERVISOR_FILE in " ".join(container.command)

    def test_is_not_privileged(self):
        """Docker 환경과 달리 데몬이 필요 없으므로 특권을 주지 않는다."""
        context = self._pod().spec.containers[0].security_context
        assert context.privileged is False
        assert context.allow_privilege_escalation is False

    def test_has_resource_and_storage_limits(self):
        limits = self._pod().spec.containers[0].resources.limits
        assert limits["cpu"] == settings.SANDBOX_LINUX_CPU_LIMIT
        assert limits["memory"] == settings.SANDBOX_LINUX_MEMORY_LIMIT
        # 디스크를 채우는 훈련이 노드를 위협하면 안 된다
        assert limits["ephemeral-storage"] == settings.SANDBOX_LINUX_STORAGE_LIMIT


class TestEnvironmentIsolation:
    def test_linux_commands_rejected_in_other_environments(self, validator):
        assert not validator.validate_command(
            "ps aux", NS, environment=environments.KUBERNETES
        ).is_valid
        assert not validator.validate_command(
            "ps aux", NS, environment=environments.DOCKER
        ).is_valid

    def test_other_environment_commands_rejected_in_linux(self, validator):
        assert not _check(validator, "kubectl get pods").is_valid
        assert not _check(validator, "docker ps").is_valid

    def test_linux_is_implemented(self):
        """BE-18 에서 injector/validator 와 시드가 붙어 환경이 열렸다."""
        assert environments.is_implemented(environments.LINUX)


def _confirmed(validator, command):
    return validator.validate_delete(
        command, NS, confirmed=True, environment=environments.LINUX
    )


class TestFlagValuesAreNotTargets:
    """플래그 값을 경로·신호 대상으로 오인하면 정당한 복구가 막힌다.

    Docker 정책에서 `docker update --memory 256m` 의 256m 을 대상으로 읽던 것과
    같은 계열의 결함이다. Linux 는 명령마다 플래그 의미가 달라 명령별로 다룬다.
    (2026-09-02 프론트 보고: `truncate -s 0` 이 막혀 truncate 가 복구 명령으로
     기능하지 못했다)
    """

    @pytest.mark.parametrize(
        "command",
        [
            "tail -n 50 /tmp/afterfail/app.log",
            "head -n 20 /proc/meminfo",
            "head -c 200 /proc/loadavg",
            "find /tmp/afterfail -name afterfail-fill.dat",
            "stat -c %s /tmp/afterfail/fill.dat",
        ],
    )
    def test_read_commands_accept_flag_values(self, validator, command):
        result = _check(validator, command)
        assert result.is_valid, result.error

    @pytest.mark.parametrize(
        "command",
        [
            "truncate -s 0 /tmp/afterfail/fill.dat",
            "truncate --size=0 /tmp/afterfail/fill.dat",
            "kill -s TERM 4321",
            "kill -9 4321",
        ],
    )
    def test_recovery_commands_accept_flag_values(self, validator, command):
        result = _confirmed(validator, command)
        assert result.is_valid, result.error

    def test_pkill_pattern_stays_a_target(self):
        """`pkill -f afterfail-worker` 의 `-f` 값은 대상 그 자체다.

        값 플래그로 취급하면 대상이 사라져 "requires a target" 으로 거절된다.
        """
        assert "-f" not in LinuxPolicy.VALUE_FLAGS.get("pkill", frozenset())

    @pytest.mark.parametrize(
        "command",
        [
            "truncate -s 0 /etc/passwd",
            "tail -n 50 /etc/shadow",
            "head -c 100 /root/.ssh/id_rsa",
            "find / -name id_rsa",
            "rm -f /etc/hosts",
        ],
    )
    def test_flag_handling_does_not_open_a_path_escape(self, validator, command):
        """값 플래그를 건너뛰는 것이 경로 검사를 무력화하면 안 된다."""
        result = _check(validator, command)
        if result.requires_confirmation:
            result = _confirmed(validator, command)
        assert not result.is_valid

    @pytest.mark.parametrize(
        "command", ["pkill -f nginx", "kill -s TERM 1", "kill -9 1"]
    )
    def test_signal_targets_are_still_restricted(self, validator, command):
        assert not _confirmed(validator, command).is_valid


class TestTerminalBanner:
    """접속 배너는 환경마다 달라야 한다.

    Kubernetes 안내를 그대로 보내 Linux 세션에서도 kubectl 을 치라고 안내하고
    있었다(2026-09-02 프론트 보고). 문구를 손으로 두 곳에 두지 않고 정책에서 만든다.
    """

    def test_linux_hint_does_not_mention_kubectl(self, validator):
        hint = validator.usage_hint(environments.LINUX)
        assert "kubectl" not in hint
        assert "docker" not in hint

    def test_linux_hint_lists_commands_the_policy_allows(self, validator):
        hint = validator.usage_hint(environments.LINUX)
        for command in ("ps", "df", "cat", "pkill"):
            assert command in hint

    @pytest.mark.parametrize(
        "environment,expected",
        [
            (environments.KUBERNETES, "kubectl"),
            (environments.DOCKER, "docker"),
        ],
    )
    def test_binary_environments_name_their_binary(self, validator, environment, expected):
        assert expected in validator.usage_hint(environment)

    def test_unknown_environment_gets_no_hint(self, validator):
        assert validator.usage_hint("windows") == ""

    def test_banner_is_built_from_the_policy(self):
        """websocket_handler 가 문구를 직접 갖고 있으면 정책과 따로 늙는다."""
        import pathlib

        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "app" / "services" / "websocket_handler.py"
        ).read_text()
        assert "usage_hint" in source
        assert "Type 'kubectl'" not in source
