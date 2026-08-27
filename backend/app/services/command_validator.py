import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    is_valid: bool
    command: str = ""
    error: str = ""
    requires_confirmation: bool = False


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

    BLACKLIST_PATTERNS = [
        r"\|",      # Pipe
        r">",       # Redirect
        r"<",       # Redirect
        r"&&",      # Command chaining
        r";",       # Command separator
        r"`",       # Command substitution
        r"\$\(",    # Command substitution
    ]

    def validate_command(self, command: str, namespace: str) -> ValidationResult:
        command = command.strip()

        if not command.startswith("kubectl"):
            return ValidationResult(
                is_valid=False,
                error="Only kubectl commands are allowed",
            )

        parts = command.split()
        if len(parts) < 2:
            return ValidationResult(
                is_valid=False,
                error="명령어 목록을 보려면 'kubectl help'를 입력하세요.",
            )

        subcommand = parts[1]
        if subcommand in self.FORBIDDEN_COMMANDS:
            return ValidationResult(
                is_valid=False,
                error=f"Command '{subcommand}' is restricted for safety reasons",
            )

        for pattern in self.BLACKLIST_PATTERNS:
            if re.search(pattern, command):
                return ValidationResult(
                    is_valid=False,
                    error="Command contains forbidden characters",
                )

        if subcommand == "create":
            create_error = self._validate_create(parts)
            if create_error is not None:
                return create_error

        if subcommand == "delete":
            return ValidationResult(
                is_valid=False,
                error="Delete operation requires confirmation",
                requires_confirmation=True,
                command=command,
            )

        if "-n" not in command and "--namespace" not in command:
            command = self._inject_namespace(command, namespace)

        if not self._verify_namespace(command, namespace):
            return ValidationResult(
                is_valid=False,
                error=f"Access denied: You can only access namespace '{namespace}'",
            )

        return ValidationResult(is_valid=True, command=command)

    def validate_delete(self, command: str, namespace: str, confirmed: bool = False) -> ValidationResult:
        if not confirmed:
            return ValidationResult(
                is_valid=False,
                error="Delete operation requires confirmation",
                requires_confirmation=True,
                command=command,
            )

        command = command.strip()

        for pattern in self.BLACKLIST_PATTERNS:
            if re.search(pattern, command):
                return ValidationResult(
                    is_valid=False,
                    error="Command contains forbidden characters",
                )

        if "-n" not in command and "--namespace" not in command:
            command = self._inject_namespace(command, namespace)

        if not self._verify_namespace(command, namespace):
            return ValidationResult(
                is_valid=False,
                error=f"Access denied: You can only access namespace '{namespace}'",
            )

        return ValidationResult(is_valid=True, command=command)

    def _validate_create(self, parts: list[str]) -> ValidationResult | None:
        """kubectl create 의 허용 범위를 검사한다. 문제가 없으면 None."""
        resource = parts[2] if len(parts) > 2 else ""

        if resource not in self.CREATE_ALLOWED_RESOURCES:
            allowed = ", ".join(self.CREATE_ALLOWED_RESOURCES)
            target = f"create {resource}".strip()
            return ValidationResult(
                is_valid=False,
                error=f"'{target}' is not allowed. Only these resources can be created: {allowed}",
            )

        if resource == "secret":
            secret_type = parts[3] if len(parts) > 3 else ""
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

        name = parts[name_index] if len(parts) > name_index else ""
        if not name or name.startswith("-"):
            return ValidationResult(
                is_valid=False,
                error=f"'create {resource}' is not allowed without a resource name",
            )

        return None

    def _inject_namespace(self, command: str, namespace: str) -> str:
        parts = command.split()
        parts.insert(2, f"-n")
        parts.insert(3, namespace)
        return " ".join(parts)

    def _verify_namespace(self, command: str, allowed_namespace: str) -> bool:
        match = re.search(r"-n\s+(\S+)|--namespace[=\s]+(\S+)", command)
        if match:
            namespace = match.group(1) or match.group(2)
            return namespace == allowed_namespace
        return True
