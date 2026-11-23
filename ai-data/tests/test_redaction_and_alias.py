"""마스킹이 JSON patch 경로를 지우지 않고, docker_* 가 container_* 문서와 맞는다."""
from context_safety import redact_text
from rag_service import _FAULT_TYPE_ALIASES


def test_json_patch_path_is_not_redacted():
    cmd = ('kubectl patch deployment nginx --type=json '
           '-p=[{"op":"remove","path":"/spec/template/spec/containers/0/readinessProbe"}]')
    out = redact_text(cmd)
    assert "/spec/template/spec/containers/0/readinessProbe" in out
    assert "REDACTED" not in out


def test_real_secrets_still_redacted():
    assert "REDACTED" in redact_text("--from-literal=password=supersecretvalue123")
    # 연속 영숫자 토큰(슬래시 없음)은 계속 가린다
    assert "REDACTED" in redact_text("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOP0123456789")


def test_docker_fault_types_alias_to_container_tags():
    assert _FAULT_TYPE_ALIASES["docker_network_disconnect"] == "container_network_disconnect"
    assert _FAULT_TYPE_ALIASES["docker_cpu_throttle"] == "container_cpu_throttle"
