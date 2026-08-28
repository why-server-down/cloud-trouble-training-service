"""사용자 명령 검증.

핵심 방어선은 **argv allowlist + 샌드박스 exec** 이다. 여기서 만들어진 argv 는
셸을 거치지 않고 샌드박스 Pod 안에서 그대로 실행된다. 문자열 blacklist 는
셸 메타문자를 조기에 거절하기 위한 보조 수단일 뿐 단독 방어수단이 아니다.
"""
import re
import shlex
from dataclasses import dataclass, field

from app.core.environments import DEFAULT_ENVIRONMENT, EnvironmentId


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


class CommandValidator:
    FORBIDDEN_COMMANDS = [
        "cluster-info", "cordon", "uncordon", "drain", "proxy",
        "auth", "certificate", "alpha", "cp", "plugin", "attach"
    ]

    # kubectl create 는 훈련 시나리오 복구에 실제로 필요한 리소스만 허용한다.
    # (secret_ref_missing 미션의 정답 경로에 Secret 생성이 포함된다)
    CREATE_ALLOWED_RESOURCES = ("secret", "configmap")

    # secret 은 타입까지 지정해야 실제로 생성 가능한 명령이 된다.
    CREATE_SECRET_TYPES = ("generic", "docker-registry", "tls")

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

    def validate_command(
        self,
        command: str,
        namespace: str,
        environment: EnvironmentId = DEFAULT_ENVIRONMENT,
    ) -> ValidationResult:
        command = command.strip()

        if not command.startswith("kubectl"):
            return ValidationResult(
                is_valid=False,
                error="Only kubectl commands are allowed",
            )

        blacklist_error = self._check_blacklist(command)
        if blacklist_error is not None:
            return blacklist_error

        argv = self._split(command)
        if argv is None:
            return ValidationResult(
                is_valid=False,
                error="Command could not be parsed. Check quotes.",
            )

        if len(argv) < 2:
            return ValidationResult(
                is_valid=False,
                error="명령어 목록을 보려면 'kubectl help'를 입력하세요.",
            )

        subcommand = argv[1]
        if subcommand in self.FORBIDDEN_COMMANDS:
            return ValidationResult(
                is_valid=False,
                error=f"Command '{subcommand}' is restricted for safety reasons",
            )

        if subcommand == "create":
            create_error = self._validate_create(argv)
            if create_error is not None:
                return create_error

        if subcommand == "delete":
            return ValidationResult(
                is_valid=False,
                error="Delete operation requires confirmation",
                requires_confirmation=True,
                argv=argv,
            )

        return self._finalize(argv, namespace)

    def validate_delete(
        self,
        command: str,
        namespace: str,
        confirmed: bool = False,
        environment: EnvironmentId = DEFAULT_ENVIRONMENT,
    ) -> ValidationResult:
        command = command.strip()

        if not confirmed:
            argv = self._split(command) or []
            return ValidationResult(
                is_valid=False,
                error="Delete operation requires confirmation",
                requires_confirmation=True,
                argv=argv,
            )

        blacklist_error = self._check_blacklist(command)
        if blacklist_error is not None:
            return blacklist_error

        argv = self._split(command)
        if argv is None:
            return ValidationResult(
                is_valid=False,
                error="Command could not be parsed. Check quotes.",
            )

        return self._finalize(argv, namespace)

    def _check_blacklist(self, command: str) -> ValidationResult | None:
        for pattern in self.BLACKLIST_PATTERNS:
            if re.search(pattern, command):
                return ValidationResult(
                    is_valid=False,
                    error="Command contains forbidden characters",
                )
        return None

    @staticmethod
    def _split(command: str) -> list[str] | None:
        """셸 파싱 없이 인자만 분리한다. 따옴표가 안 맞으면 None."""
        try:
            return shlex.split(command)
        except ValueError:
            return None

    def _finalize(self, argv: list[str], namespace: str) -> ValidationResult:
        argv = self._apply_namespace(argv, namespace)
        if not self._verify_namespace(argv, namespace):
            return ValidationResult(
                is_valid=False,
                error=f"Access denied: You can only access namespace '{namespace}'",
            )
        return ValidationResult(is_valid=True, argv=argv)

    def _validate_create(self, argv: list[str]) -> ValidationResult | None:
        """kubectl create 의 허용 범위를 검사한다. 문제가 없으면 None."""
        resource = argv[2] if len(argv) > 2 else ""

        if resource not in self.CREATE_ALLOWED_RESOURCES:
            allowed = ", ".join(self.CREATE_ALLOWED_RESOURCES)
            target = f"create {resource}".strip()
            return ValidationResult(
                is_valid=False,
                error=f"'{target}' is not allowed. Only these resources can be created: {allowed}",
            )

        if resource == "secret":
            secret_type = argv[3] if len(argv) > 3 else ""
            if secret_type not in self.CREATE_SECRET_TYPES:
                types = ", ".join(self.CREATE_SECRET_TYPES)
                target = f"create secret {secret_type}".strip()
                return ValidationResult(
                    is_valid=False,
                    error=f"'{target}' is not allowed. Specify a secret type: {types}",
                )
            name_index = 4
        else:
            name_index = 3

        name = argv[name_index] if len(argv) > name_index else ""
        if not name or name.startswith("-"):
            return ValidationResult(
                is_valid=False,
                error=f"'create {resource}' is not allowed without a resource name",
            )

        return None

    @staticmethod
    def _namespace_index(argv: list[str]) -> int | None:
        for index, token in enumerate(argv):
            if token in ("-n", "--namespace") or token.startswith("--namespace="):
                return index
        return None

    def _apply_namespace(self, argv: list[str], namespace: str) -> list[str]:
        """네임스페이스가 지정되지 않았으면 서버가 정한 값을 넣는다."""
        if self._namespace_index(argv) is not None:
            return argv
        return [*argv[:2], "-n", namespace, *argv[2:]]

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
