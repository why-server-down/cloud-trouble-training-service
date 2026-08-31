"""외부 LLM으로 전달되는 튜터 컨텍스트의 redaction과 크기 제한."""
from __future__ import annotations

import json
import re
from typing import Any

REDACTED = "***REDACTED***"
TRUNCATED = "...[TRUNCATED]"

QUESTION_MAX_CHARS = 2_000
OBSERVATIONS_MAX_CHARS = 8_000
COMMANDS_MAX_CHARS = 3_000
LOGS_MAX_CHARS = 4_000
DOCS_MAX_CHARS = 8_000
USER_MAX_CHARS = 2_000
TOTAL_UNTRUSTED_MAX_CHARS = 24_000

_SENSITIVE_KEY_VALUE = re.compile(
    r"(?i)\b(token|secret|password|passwd|pwd|api[_-]?key|authorization|credential|"
    r"private[_-]?key|access[_-]?key|client[_-]?secret)\b\s*[:=]\s*[^\n,;\]}]+"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_PROVIDER_TOKEN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b"
)
_LITERAL_FLAG = re.compile(r"(?i)(--from-literal=\S+?=)\S+")
_ENV_ASSIGNMENT = re.compile(r"(?m)\b[A-Z][A-Z0-9_]{2,}\s*=\s*[^\s]+")
_LONG_BASE64 = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")
_SENSITIVE_FIELDS = {
    "token", "secret", "password", "passwd", "pwd", "api_key", "apikey",
    "authorization", "credential", "private_key", "access_key", "client_secret",
    "env", "environ", "environment_variables", "stringdata",
}


def redact_text(value: str) -> str:
    if not value:
        return value
    value = _SENSITIVE_KEY_VALUE.sub(lambda match: f"{match.group(1)}={REDACTED}", value)
    value = _BEARER.sub(f"Bearer {REDACTED}", value)
    value = _PROVIDER_TOKEN.sub(REDACTED, value)
    value = _LITERAL_FLAG.sub(lambda match: f"{match.group(1)}{REDACTED}", value)
    value = _ENV_ASSIGNMENT.sub(REDACTED, value)
    return _LONG_BASE64.sub(REDACTED, value)


def redact(value: Any, *, kubernetes_secret: bool = False) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(item, kubernetes_secret=kubernetes_secret) for item in value]
    if isinstance(value, dict):
        is_secret = kubernetes_secret or str(value.get("kind", "")).casefold() == "secret"
        result = {}
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in _SENSITIVE_FIELDS or (is_secret and normalized == "data"):
                result[key] = REDACTED
            else:
                result[key] = redact(item, kubernetes_secret=is_secret)
        return result
    return value


def truncate_text(value: str, limit: int) -> str:
    value = redact_text(value)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - len(TRUNCATED))] + TRUNCATED


def limit_value(value: Any, limit: int) -> Any:
    """구조와 앞부분의 핵심 관측을 유지하며 JSON 직렬화 크기를 제한한다."""
    cleaned = redact(value)
    serialized = json.dumps(cleaned, ensure_ascii=False, default=str)
    if len(serialized) <= limit:
        return cleaned
    if isinstance(cleaned, dict):
        result = {}
        remaining = limit
        for key, item in cleaned.items():
            if remaining <= len(TRUNCATED):
                result["_truncated"] = True
                break
            item_limit = min(max(256, remaining // max(1, len(cleaned) - len(result))), remaining)
            limited = limit_value(item, item_limit)
            result[key] = limited
            remaining -= len(json.dumps({key: limited}, ensure_ascii=False, default=str))
        result.setdefault("_truncated", True)
        return result
    if isinstance(cleaned, list):
        result = []
        remaining = limit
        for item in cleaned:
            if remaining <= len(TRUNCATED):
                result.append(TRUNCATED)
                break
            limited = limit_value(item, min(2_000, remaining))
            result.append(limited)
            remaining -= len(json.dumps(limited, ensure_ascii=False, default=str))
        if not result or result[-1] != TRUNCATED:
            result.append(TRUNCATED)
        return result
    return truncate_text(str(cleaned), limit)
