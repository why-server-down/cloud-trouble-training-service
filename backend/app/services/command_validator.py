import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    is_valid: bool
    command: str = ""
    error: str = ""
    requires_confirmation: bool = False


class CommandValidator:
    ALLOWED_COMMANDS = [
        "get", "describe", "logs", "edit", "apply", "delete", "set", "patch",
        "exec", "port-forward", "top", "explain",
        "help", "version", "api-resources", "api-versions",
    ]

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
                error="Invalid kubectl command",
            )

        subcommand = parts[1]
        if subcommand not in self.ALLOWED_COMMANDS:
            return ValidationResult(
                is_valid=False,
                error=f"Command '{subcommand}' is not allowed",
            )

        for pattern in self.BLACKLIST_PATTERNS:
            if re.search(pattern, command):
                return ValidationResult(
                    is_valid=False,
                    error="Command contains forbidden characters",
                )

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
