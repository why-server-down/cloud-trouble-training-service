"""AI 계층으로 나가는 관측값에서 민감정보를 지운다.

RuntimeContext 는 사용자가 친 명령과 클러스터 상태를 그대로 담는다. 그 안에는
토큰·비밀번호·환경변수가 섞일 수 있고, 그대로 LLM 프로바이더에 전송된다.
"""
import re

_REDACTED = "***REDACTED***"

# key=value / key: value 형태의 민감 항목.
# 값은 줄 끝까지 지운다. "Authorization: Bearer a.b.c" 처럼 값이 여러 토큰인 경우
# 한 토큰만 지우면 나머지가 그대로 남는다.
_SENSITIVE_KEY = re.compile(
    r"(?i)\b(token|secret|password|passwd|pwd|api[_-]?key|authorization|credential|"
    r"private[_-]?key|access[_-]?key)\b\s*[:=]\s*[^\n]*"
)
# 키 없이 나오는 Bearer 토큰
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}")
# --from-literal=key=value 처럼 값이 붙는 플래그
_LITERAL_FLAG = re.compile(r"(?i)(--from-literal=\S+?=)\S+")
# base64 로 보이는 긴 문자열(Secret data 값 등)
_LONG_BASE64 = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")


def redact_text(value: str) -> str:
    """문자열에서 민감해 보이는 값을 지운다."""
    if not value:
        return value
    value = _SENSITIVE_KEY.sub(rf"\1={_REDACTED}", value)
    value = _BEARER.sub(f"Bearer {_REDACTED}", value)
    value = _LITERAL_FLAG.sub(rf"\1{_REDACTED}", value)
    value = _LONG_BASE64.sub(_REDACTED, value)
    return value


def redact(value):
    """dict/list/str 을 재귀적으로 훑어 민감값을 지운다.

    환경변수는 이름만 남기고 값을 통째로 지운다. 계획서가 "전체 환경변수"를
    redaction 대상으로 지목했다.
    """
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in ("env", "environ", "environment_variables"):
                result[key] = _REDACTED
                continue
            result[key] = redact(item)
        return result
    return value
