"""사용자 명령 검증.

핵심 방어선은 **argv allowlist + 샌드박스 exec** 이다. 여기서 만들어진 argv 는
셸을 거치지 않고 샌드박스 Pod 안에서 그대로 실행된다. 문자열 blacklist 는
셸 메타문자를 조기에 거절하기 위한 보조 수단일 뿐 단독 방어수단이 아니다.

환경마다 허용 명령이 다르므로 정책을 environment 별로 나눈다.
"""
import re
import shlex
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.environments import DEFAULT_ENVIRONMENT, DOCKER, LINUX, EnvironmentId, KUBERNETES


@dataclass
class ValidationResult:
    is_valid: bool
    # 셸을 거치지 않고 실행할 인자 목록. 문자열 명령을 그대로 넘기지 않는다.
    argv: list[str] = field(default_factory=list)
    error: str = ""
    requires_confirmation: bool = False

    @property
    def command(self) -> str:
        """로그·표시용 문자열. 실행에는 argv 를 쓴다."""
        return shlex.join(self.argv)


def _invalid(error: str) -> ValidationResult:
    return ValidationResult(is_valid=False, error=error)


class _PolicyBase:
    binary: str | None = None
    # 터미널 접속 배너에 보여줄 예시. 환경마다 칠 수 있는 명령이 다르다.
    EXAMPLE = ""
    MIN_ARGV = 2

    # 하위 명령 위치가 환경마다 다르다. kubectl/docker 는 argv[1], Linux 는 argv[0].
    CONFIRM_INDEX = 1
    CONFIRM_SUBCOMMANDS: tuple[str, ...] = ()

    def confirmation_target(self, argv: list[str]) -> str | None:
        if len(argv) <= self.CONFIRM_INDEX:
            return None
        token = argv[self.CONFIRM_INDEX]
        return token if token in self.CONFIRM_SUBCOMMANDS else None


class KubectlPolicy(_PolicyBase):
    """Kubernetes 환경 정책."""

    binary = "kubectl"
    EXAMPLE = "kubectl get pods"

    FORBIDDEN_COMMANDS = [
        "cluster-info", "cordon", "uncordon", "drain", "proxy",
        "auth", "certificate", "alpha", "cp", "plugin", "attach"
    ]

    # kubectl create 는 훈련 시나리오 복구에 실제로 필요한 리소스만 허용한다.
    # (secret_ref_missing 미션의 정답 경로에 Secret 생성이 포함된다)
    CREATE_ALLOWED_RESOURCES = ("secret", "configmap")
    CREATE_SECRET_TYPES = ("generic", "docker-registry", "tls")

    CONFIRM_SUBCOMMANDS = ("delete",)

    def validate(self, argv: list[str], namespace: str, allowed_targets) -> ValidationResult:
        subcommand = argv[1]
        if subcommand in self.FORBIDDEN_COMMANDS:
            return _invalid(f"Command '{subcommand}' is restricted for safety reasons")

        if subcommand == "create":
            create_error = self._validate_create(argv)
            if create_error is not None:
                return create_error

        return self._finalize(argv, namespace)

    def _validate_create(self, argv: list[str]) -> ValidationResult | None:
        resource = argv[2] if len(argv) > 2 else ""

        if resource not in self.CREATE_ALLOWED_RESOURCES:
            allowed = ", ".join(self.CREATE_ALLOWED_RESOURCES)
            target = f"create {resource}".strip()
            return _invalid(
                f"'{target}' is not allowed. Only these resources can be created: {allowed}"
            )

        if resource == "secret":
            secret_type = argv[3] if len(argv) > 3 else ""
            if secret_type not in self.CREATE_SECRET_TYPES:
                types = ", ".join(self.CREATE_SECRET_TYPES)
                target = f"create secret {secret_type}".strip()
                return _invalid(f"'{target}' is not allowed. Specify a secret type: {types}")
            name_index = 4
        else:
            name_index = 3

        name = argv[name_index] if len(argv) > name_index else ""
        if not name or name.startswith("-"):
            return _invalid(f"'create {resource}' is not allowed without a resource name")
        return None

    @staticmethod
    def _namespace_index(argv: list[str]) -> int | None:
        for index, token in enumerate(argv):
            if token in ("-n", "--namespace") or token.startswith("--namespace="):
                return index
        return None

    def _finalize(self, argv: list[str], namespace: str) -> ValidationResult:
        if self._namespace_index(argv) is None:
            argv = [*argv[:2], "-n", namespace, *argv[2:]]
        if not self._verify_namespace(argv, namespace):
            return _invalid(f"Access denied: You can only access namespace '{namespace}'")
        return ValidationResult(is_valid=True, argv=argv)

    def _verify_namespace(self, argv: list[str], allowed_namespace: str) -> bool:
        index = self._namespace_index(argv)
        if index is None:
            return True
        token = argv[index]
        if token.startswith("--namespace="):
            requested = token.split("=", 1)[1]
        else:
            requested = argv[index + 1] if index + 1 < len(argv) else ""
        return requested == allowed_namespace


class DockerPolicy(_PolicyBase):
    """Docker 환경 정책.

    샌드박스가 privileged DinD 이므로, 사용자가 칠 수 있는 명령을 좁히는 것이
    실질적인 방어선이다. 커널 탈출을 시도할 수 있는 명령을 애초에 만들지 못하게 한다.
    """

    binary = "docker"
    EXAMPLE = "docker ps"

    # 조회 계열. 대상이 없어도 되고 상태를 바꾸지 않는다.
    READ_COMMANDS = {
        "ps": (),
        "images": (),
        "version": (),
        "info": (),
        "inspect": (),
        "logs": (),
        "stats": (),
        "port": (),
        "top": (),
        "diff": (),
    }
    # 하위 명령이 있는 조회 계열
    READ_SUBCOMMANDS = {
        "network": {"ls", "inspect"},
        "volume": {"ls", "inspect"},
        "container": {"ls", "inspect"},
    }

    # 복구 계열. 훈련 대상 리소스에만 쓸 수 있다.
    RECOVERY_COMMANDS = {"start", "restart", "stop", "unpause", "update"}
    RECOVERY_SUBCOMMANDS = {
        "network": {"connect", "disconnect"},
        "volume": {"create"},
    }

    CONFIRM_SUBCOMMANDS = ("rm", "kill")

    # 대상 없이도 광범위한 영향을 주는 명령. 항상 거절한다.
    BLOCKED_COMMANDS = {
        "run", "exec", "create", "build", "commit", "push", "pull", "save", "load",
        "export", "import", "cp", "attach", "system", "swarm", "node", "service",
        "stack", "secret", "config", "context", "login", "logout", "plugin", "builder",
        "buildx", "compose", "manifest", "trust", "checkpoint",
    }

    # 데몬 자체를 바꾸거나 다른 소켓을 가리키는 전역 옵션
    BLOCKED_GLOBAL_FLAGS = ("-H", "--host", "--context", "--config", "--tlsverify")

    # update 로 자원 상한을 조정하는 것만 허용한다. 특권 상승 옵션은 막는다.
    UPDATE_ALLOWED_FLAGS = (
        "--memory", "-m", "--memory-swap", "--cpus", "--cpu-shares",
        "--restart", "--pids-limit",
    )

    # 뒤에 값을 하나 받는 플래그. 그 값을 대상 이름으로 오인하면 안 된다.
    # (`docker update --memory 256m training-app` 의 256m 은 대상이 아니다)
    VALUE_FLAGS = {
        "--memory", "-m", "--memory-swap", "--cpus", "--cpu-shares",
        "--restart", "--pids-limit", "--tail", "--since", "--until",
        "--format", "-f", "--filter", "--signal", "-s",
    }

    def validate(self, argv: list[str], namespace: str, allowed_targets) -> ValidationResult:
        flag_error = self._check_global_flags(argv)
        if flag_error is not None:
            return flag_error

        subcommand = argv[1]

        if subcommand in self.BLOCKED_COMMANDS:
            return _invalid(
                f"'docker {subcommand}' is not allowed in the training sandbox"
            )

        if subcommand in self.READ_SUBCOMMANDS or subcommand in self.RECOVERY_SUBCOMMANDS:
            return self._validate_grouped(argv, subcommand, allowed_targets)

        if subcommand in self.READ_COMMANDS:
            return self._validate_targets(argv, allowed_targets, required=False)

        if subcommand in self.RECOVERY_COMMANDS:
            if subcommand == "update":
                update_error = self._check_update_flags(argv)
                if update_error is not None:
                    return update_error
            return self._validate_targets(argv, allowed_targets, required=True)

        return _invalid(
            f"'docker {subcommand}' is not allowed. "
            "Available: ps, inspect, logs, stats, network/volume ls·inspect, "
            "start, restart, stop, update, network connect/disconnect"
        )

    def _check_global_flags(self, argv: list[str]) -> ValidationResult | None:
        """데몬 지정·설정 변경 옵션은 어떤 위치에서도 거절한다."""
        for token in argv[1:]:
            base = token.split("=", 1)[0]
            if base in self.BLOCKED_GLOBAL_FLAGS:
                return _invalid(
                    f"'{base}' is not allowed. "
                    "The sandbox daemon cannot be changed."
                )
        return None

    def _check_update_flags(self, argv: list[str]) -> ValidationResult | None:
        for token in argv[2:]:
            if not token.startswith("-"):
                continue
            base = token.split("=", 1)[0]
            if base not in self.UPDATE_ALLOWED_FLAGS:
                allowed = ", ".join(self.UPDATE_ALLOWED_FLAGS)
                return _invalid(f"'{base}' is not allowed for update. Allowed: {allowed}")
        return None

    def _validate_grouped(
        self, argv: list[str], group: str, allowed_targets
    ) -> ValidationResult:
        action = argv[2] if len(argv) > 2 else ""
        read_actions = self.READ_SUBCOMMANDS.get(group, set())
        recovery_actions = self.RECOVERY_SUBCOMMANDS.get(group, set())

        if action in read_actions:
            return self._validate_targets(argv, allowed_targets, required=False, start=3)
        if action in recovery_actions:
            return self._validate_targets(argv, allowed_targets, required=True, start=3)

        allowed = ", ".join(sorted(read_actions | recovery_actions)) or "none"
        return _invalid(f"'docker {group} {action}'.strip() is not allowed. Allowed: {allowed}")

    def _validate_targets(
        self,
        argv: list[str],
        allowed_targets,
        *,
        required: bool,
        start: int = 2,
    ) -> ValidationResult:
        """대상 이름이 훈련이 허용한 리소스 안에 있는지 확인한다."""
        targets = self._positional_args(argv[start:])

        if required and not targets:
            return _invalid("This command requires a target resource name")

        unknown = [t for t in targets if t not in allowed_targets]
        if unknown:
            allowed = ", ".join(sorted(allowed_targets))
            return _invalid(
                f"'{unknown[0]}' is not a training resource. Allowed: {allowed}"
            )

        return ValidationResult(is_valid=True, argv=argv)

    def _positional_args(self, tokens: list[str]) -> list[str]:
        """플래그와 그 값을 제외한 실제 대상 이름만 뽑는다."""
        positional = []
        skip_next = False
        for token in tokens:
            if skip_next:
                skip_next = False
                continue
            if token.startswith("-"):
                # `--memory=256m` 은 값이 붙어 있으므로 다음 토큰을 건너뛰지 않는다
                if "=" not in token and token in self.VALUE_FLAGS:
                    skip_next = True
                continue
            positional.append(token)
        return positional


class LinuxPolicy(_PolicyBase):
    """Linux 환경 정책.

    kubectl/docker 와 달리 단일 바이너리가 아니라 명령 자체가 argv[0] 이다.

    허용 목록은 **실제 컨테이너에서 동작하는 것만** 넣었다(BE-16 실측).
    `journalctl` / `systemctl` 은 systemd 가 없어서, `dmesg` 는 커널 링 버퍼 접근이
    막혀 있어서 어떤 이미지에서도 동작하지 않는다. 되지 않는 명령을 목록에 넣으면
    사용자가 그것을 정답으로 착각한다.
    """

    binary = None
    EXAMPLE = "ps aux"
    MIN_ARGV = 1
    CONFIRM_INDEX = 0
    CONFIRM_SUBCOMMANDS = ("kill", "pkill", "rm", "truncate")

    # 상태를 바꾸지 않는 조회 명령
    READ_COMMANDS = {
        "ps", "free", "df", "du", "top", "uptime", "iostat",
        "ss", "netstat", "lsof", "pstree", "id", "whoami", "env",
    }
    # 파일을 읽는 명령. 경로 제한을 받는다.
    FILE_READ_COMMANDS = {"cat", "head", "tail", "wc", "ls", "stat", "find"}
    # 복구 명령. 확인 계약을 따르고 대상이 제한된다.
    RECOVERY_COMMANDS = {"kill", "pkill", "rm", "truncate"}

    # 읽기가 허용된 경로. 훈련과 무관한 파일을 뒤지지 못하게 한다.
    READABLE_PREFIXES = ("/proc", "/sys/fs/cgroup", "/tmp/afterfail", ".")
    # 쓰기·삭제가 허용된 경로
    WRITABLE_PREFIXES = ("/tmp/afterfail",)

    # 뒤에 값을 하나 받는 플래그. 그 값을 경로나 신호 대상으로 오인하면 안 된다.
    # (`truncate -s 0 /tmp/afterfail/x` 의 0 은 경로가 아니다)
    #
    # kubectl/docker 와 달리 명령별로 다르다. 특히 `pkill -f afterfail-worker` 의
    # `-f` 값은 **대상 그 자체**이므로 값 플래그로 넣으면 안 된다. 넣으면 대상이
    # 사라져 "This command requires a target" 으로 거절된다.
    VALUE_FLAGS: dict[str, frozenset[str]] = {
        "truncate": frozenset({"-s", "--size", "-r", "--reference"}),
        "tail": frozenset({"-n", "-c", "--lines", "--bytes"}),
        "head": frozenset({"-n", "-c", "--lines", "--bytes"}),
        "find": frozenset({
            "-name", "-iname", "-type", "-maxdepth", "-mindepth",
            "-size", "-mtime", "-newer", "-path", "-regex",
        }),
        "stat": frozenset({"-c", "--format", "--printf"}),
        "du": frozenset({"-d", "--max-depth", "--block-size", "-B", "--threshold"}),
        "df": frozenset({"--block-size", "-B", "-t", "--type", "-x", "--exclude-type"}),
        "ps": frozenset({"-o", "-eo", "--format", "-p", "--pid", "-u", "-U", "-C"}),
        "kill": frozenset({"-s", "--signal", "-n"}),
        "wc": frozenset(),
    }

    def validate(self, argv: list[str], namespace: str, allowed_targets) -> ValidationResult:
        command = argv[0]

        if command in self.READ_COMMANDS:
            return ValidationResult(is_valid=True, argv=argv)

        if command in self.FILE_READ_COMMANDS:
            return self._check_paths(argv, self.READABLE_PREFIXES, "read")

        if command in self.RECOVERY_COMMANDS:
            if command in ("rm", "truncate"):
                return self._check_paths(argv, self.WRITABLE_PREFIXES, "modify")
            return self._check_signal_target(argv)

        allowed = ", ".join(sorted(self.READ_COMMANDS | self.FILE_READ_COMMANDS))
        return _invalid(f"'{command}' is not allowed. Available: {allowed}")

    def validate_confirmed(self, argv: list[str]) -> ValidationResult:
        """확인을 거친 명령도 대상·경로 검사는 그대로 받는다."""
        command = argv[0]
        if command in ("rm", "truncate"):
            return self._check_paths(argv, self.WRITABLE_PREFIXES, "modify")
        return self._check_signal_target(argv)

    def _positional(self, tokens: list[str], command: str = "") -> list[str]:
        """플래그와 그 값을 제외한 실제 대상만 뽑는다."""
        value_flags = self.VALUE_FLAGS.get(command, frozenset())
        positional: list[str] = []
        skip_next = False
        for token in tokens:
            if skip_next:
                skip_next = False
                continue
            if token.startswith("-"):
                # `--size=0` 은 값이 붙어 있으므로 다음 토큰을 건너뛰지 않는다
                if "=" not in token and token in value_flags:
                    skip_next = True
                continue
            positional.append(token)
        return positional

    def _check_paths(
        self, argv: list[str], prefixes: tuple[str, ...], action: str
    ) -> ValidationResult:
        paths = self._positional(argv[1:], argv[0])
        for path in paths:
            if ".." in path:
                return _invalid("Relative paths that escape the directory are not allowed")
            if not path.startswith(prefixes):
                allowed = ", ".join(p for p in prefixes if p != ".")
                return _invalid(
                    f"Cannot {action} '{path}'. Allowed paths: {allowed}"
                )
        return ValidationResult(is_valid=True, argv=argv)

    def _check_signal_target(self, argv: list[str]) -> ValidationResult:
        """신호를 보낼 대상은 PID 나 훈련 프로세스 이름만 허용한다."""
        targets = self._positional(argv[1:], argv[0])
        if not targets:
            return _invalid("This command requires a target")
        for target in targets:
            if target.isdigit():
                if int(target) <= 1:
                    # PID 1 은 샌드박스 자체다. 죽이면 훈련이 끝난다.
                    return _invalid("PID 1 is the sandbox itself and cannot be signaled")
                continue
            if not target.startswith("afterfail-"):
                return _invalid(
                    f"'{target}' is not a training process. "
                    "Use a PID or a name starting with 'afterfail-'"
                )
        return ValidationResult(is_valid=True, argv=argv)


class CommandValidator:
    # 셸을 쓰지 않으므로 아래 문자들은 실행 전에 거절한다.
    # (argv 로 넘어가면 리터럴이 되지만, 사용자가 셸 동작을 기대하고 입력한 것이므로
    #  조용히 다르게 동작시키는 대신 명확히 거절한다)
    BLACKLIST_PATTERNS = [
        r"\|",      # Pipe
        r">",       # Redirect
        r"<",       # Redirect
        r"&&",      # Command chaining
        r";",       # Command separator
        r"`",       # Command substitution
        r"\$\(",    # Command substitution
        r"\n|\r",   # 개행을 이용한 명령 분리
    ]

    _POLICIES = {
        KUBERNETES: KubectlPolicy(),
        DOCKER: DockerPolicy(),
        LINUX: LinuxPolicy(),
    }

    def usage_hint(self, environment: EnvironmentId = DEFAULT_ENVIRONMENT) -> str:
        """터미널 배너에 넣을 안내. 정책에서 만들어 문구가 따로 늙지 않게 한다.

        (Kubernetes 안내를 모든 환경에 그대로 보내 Linux 세션에서도 kubectl 을
        치라고 안내하던 문제를 여기서 없앤다)
        """
        policy = self._POLICIES.get(environment)
        if policy is None:
            return ""
        if policy.binary:
            return f"'{policy.binary}' 명령을 입력하세요. 예: {policy.EXAMPLE}"

        available = ", ".join(
            sorted(policy.READ_COMMANDS | policy.FILE_READ_COMMANDS | policy.RECOVERY_COMMANDS)
        )
        return f"사용 가능한 명령: {available}\n예: {policy.EXAMPLE}"

    def validate_command(
        self,
        command: str,
        namespace: str,
        environment: EnvironmentId = DEFAULT_ENVIRONMENT,
        allowed_targets: set[str] | None = None,
    ) -> ValidationResult:
        parsed = self._parse(command, environment)
        if isinstance(parsed, ValidationResult):
            return parsed
        policy, argv = parsed

        targets = self._targets(allowed_targets)
        confirm_target = policy.confirmation_target(argv)
        if confirm_target is not None:
            # 확인해도 통과하지 못할 명령은 지금 거절한다.
            # "확인하면 되겠구나"로 읽히면 사용자가 잘못된 방향으로 시도한다.
            precheck = self._validate_confirmed(policy, argv, namespace, targets)
            if not precheck.is_valid:
                return precheck
            return ValidationResult(
                is_valid=False,
                error=f"{confirm_target.capitalize()} operation requires confirmation",
                requires_confirmation=True,
                argv=argv,
            )

        return policy.validate(argv, namespace, targets)

    def validate_delete(
        self,
        command: str,
        namespace: str,
        confirmed: bool = False,
        environment: EnvironmentId = DEFAULT_ENVIRONMENT,
        allowed_targets: set[str] | None = None,
    ) -> ValidationResult:
        if not confirmed:
            parsed = self._parse(command, environment)
            argv = parsed[1] if not isinstance(parsed, ValidationResult) else []
            return ValidationResult(
                is_valid=False,
                error="Delete operation requires confirmation",
                requires_confirmation=True,
                argv=argv,
            )

        parsed = self._parse(command, environment)
        if isinstance(parsed, ValidationResult):
            return parsed
        policy, argv = parsed

        return self._validate_confirmed(policy, argv, namespace, self._targets(allowed_targets))

    @staticmethod
    def _validate_confirmed(policy, argv: list[str], namespace: str, targets) -> ValidationResult:
        """확인을 거친 명령도 정책 검사는 그대로 받는다."""
        if isinstance(policy, KubectlPolicy):
            return policy._finalize(argv, namespace)
        if isinstance(policy, LinuxPolicy):
            return policy.validate_confirmed(argv)
        return policy._validate_targets(argv, targets, required=True)

    def _parse(self, command: str, environment: str):
        """공통 전처리: 대상 바이너리 확인 → 셸 메타문자 거절 → argv 분리."""
        command = command.strip()
        policy = self._POLICIES.get(environment)
        if policy is None:
            return _invalid(f"'{environment}' 환경의 명령 정책이 없습니다")

        if policy.binary and not command.startswith(policy.binary):
            return _invalid(f"Only {policy.binary} commands are allowed")

        for pattern in self.BLACKLIST_PATTERNS:
            if re.search(pattern, command):
                return _invalid("Command contains forbidden characters")

        try:
            argv = shlex.split(command)
        except ValueError:
            return _invalid("Command could not be parsed. Check quotes.")

        if len(argv) < policy.MIN_ARGV:
            hint = f"'{policy.binary} help'" if policy.binary else "'help'"
            return _invalid(f"명령어 목록을 보려면 {hint}를 입력하세요.")

        return policy, argv

    @staticmethod
    def _targets(allowed_targets: set[str] | None) -> set[str]:
        """훈련이 허용한 리소스 집합. 시나리오가 지정하지 않으면 기본 훈련 대상만."""
        if allowed_targets:
            return set(allowed_targets)
        # 시나리오가 지정하지 않으면 기본 훈련 리소스(컨테이너·네트워크·볼륨)만 허용한다.
        return {
            settings.SANDBOX_TRAINING_CONTAINER,
            settings.SANDBOX_TRAINING_NETWORK,
            settings.SANDBOX_TRAINING_VOLUME,
        }
