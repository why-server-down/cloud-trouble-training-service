"""RuntimeContext를 튜터용 최소 공통 관측 schema로 정규화한다."""
from __future__ import annotations

from copy import deepcopy

from app.services.runtime_redaction import redact


OBSERVATION_KEYS = {
    "kubernetes": ("pods", "deployments", "services", "events", "readiness"),
    "docker": ("containers", "exit", "resources", "networks", "volumes", "logs"),
    "linux": ("processes", "memory", "disk", "load", "sockets", "services", "logs"),
}
KEYWORDS = {
    "pods": ("pod", "파드", "재시작", "crash"),
    "deployments": ("deployment", "배포", "replica"),
    "services": ("service", "서비스", "systemd"),
    "events": ("event", "이벤트", "원인"),
    "readiness": ("ready", "readiness", "준비", "트래픽"),
    "containers": ("container", "컨테이너", "상태", "중지"),
    "exit": ("exit", "종료", "코드"),
    "resources": ("cpu", "memory", "메모리", "리소스"),
    "networks": ("network", "네트워크", "연결"),
    "volumes": ("volume", "볼륨", "mount", "마운트"),
    "processes": ("process", "프로세스", "pid"),
    "memory": ("memory", "메모리", "oom"),
    "disk": ("disk", "디스크", "용량", "inode"),
    "load": ("load", "부하", "느려"),
    "sockets": ("socket", "소켓", "port", "포트", "listen"),
    "logs": ("log", "로그", "에러", "오류"),
}


def _normalize(environment: str, observations: dict) -> dict:
    normalized = deepcopy(observations or {})
    if environment == "kubernetes":
        state = normalized.pop("kubernetes_state", None) or {}
        normalized.setdefault("pods", state.get("pods"))
        normalized.setdefault("deployments", state.get("deployments"))
        normalized.setdefault("services", state.get("services"))
        normalized.setdefault("events", state.get("recent_events"))
        pods = normalized.get("pods") or []
        normalized.setdefault("readiness", [
            {"name": pod.get("name"), "ready": pod.get("ready")}
            for pod in pods if isinstance(pod, dict)
        ])
    return {
        key: redact(normalized[key])
        for key in OBSERVATION_KEYS.get(environment, ())
        if normalized.get(key) not in (None, "", [], {})
    }


def prepare_runtime_context(runtime_ctx: dict, question: str, environment: str) -> dict:
    """질문과 관련된 관측 summary만 남기고 수집 상태를 명시한다."""
    prepared = deepcopy(runtime_ctx)
    available = _normalize(environment, prepared.get("observations", {}))
    lowered = question.casefold()
    relevant = [
        key for key in available
        if any(keyword in lowered for keyword in KEYWORDS.get(key, (key,)))
    ]
    selected_keys = relevant or list(available)[:3]
    prepared["observations"] = {key: available[key] for key in selected_keys[:5]}

    expected = OBSERVATION_KEYS.get(environment, ())
    missing = [key for key in expected if key not in available]
    supplied_status = prepared.get("collection_status", {})
    state = supplied_status.get("state") or (
        "unavailable" if not available else "partial" if missing else "complete"
    )
    prepared["collection_status"] = {
        "state": state,
        "available": list(available),
        "missing": supplied_status.get("missing", missing),
    }

    log_relevant = any(word in lowered for word in KEYWORDS["logs"])
    prepared["logs"] = redact(prepared.get("logs", []))[-5:] if log_relevant else []
    prepared["recent_user_commands"] = redact(prepared.get("recent_user_commands", []))[-3:]
    return prepared
