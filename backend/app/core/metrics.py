"""Prometheus 메트릭.

**label 에 고카디널리티 값을 넣지 않는다.** user ID, namespace, 명령 원문,
시나리오 제목을 label 로 쓰면 시계열이 사용자 수만큼 늘어나 저장소가 터진다.
민감정보가 메트릭에 남는 문제도 있다.
"""
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    ["method", "path", "code"],
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
)
MISSION_COMPLETIONS = Counter(
    "mission_completion_total",
    "Completed mission attempts.",
    ["mission_level"],
)

# ── 샌드박스 ──────────────────────────────────────────────────────────────
SANDBOX_PROVISION = Counter(
    "sandbox_provision_total",
    "Sandbox provisioning attempts.",
    ["environment", "result"],
)
SANDBOX_PROVISION_DURATION = Histogram(
    "sandbox_provision_duration_seconds",
    "Sandbox provisioning duration.",
    ["environment"],
    buckets=(1, 5, 10, 20, 30, 60, 120),
)

# ── 터미널 명령 ───────────────────────────────────────────────────────────
# category 는 서브커맨드 수준까지만 쓴다(get / patch / ps …). 원문은 label 에 넣지 않는다.
COMMAND_EXECUTIONS = Counter(
    "command_execution_total",
    "Terminal commands executed in sandboxes.",
    ["environment", "category", "result"],
)
COMMAND_DURATION = Histogram(
    "command_duration_seconds",
    "Terminal command duration.",
    ["environment"],
)

# ── 장애 주입·복구 ────────────────────────────────────────────────────────
CHAOS_OPERATIONS = Counter(
    "chaos_operation_total",
    "Chaos inject/revert operations.",
    ["environment", "operation", "result"],
)
CHAOS_DURATION = Histogram(
    "chaos_operation_duration_seconds",
    "Chaos operation duration.",
    ["environment", "operation"],
)

# ── 검증 ─────────────────────────────────────────────────────────────────
VALIDATION_CHECKS = Counter(
    "validation_check_total",
    "Resolution checks.",
    ["environment", "result"],
)
VALIDATION_DURATION = Histogram(
    "validation_duration_seconds",
    "Resolution check duration.",
    ["environment"],
)

# ── AI 호출 ──────────────────────────────────────────────────────────────
# 프롬프트·응답 본문은 label 에도 값에도 담지 않는다.
AI_CALLS = Counter(
    "ai_call_total",
    "LLM calls by provider and purpose.",
    ["provider", "purpose", "result"],
)
AI_CALL_DURATION = Histogram(
    "ai_call_duration_seconds",
    "LLM call duration.",
    ["provider", "purpose"],
)
AI_TOKENS = Counter(
    "ai_token_total",
    "LLM tokens consumed.",
    ["provider", "purpose", "kind"],
)
AI_STAGE_DURATION = Histogram(
    "ai_stage_duration_seconds",
    "Tutor pipeline stage duration.",
    ["provider", "model", "environment", "hint_level", "stage", "result"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0),
)

# ── 진행 상태 ─────────────────────────────────────────────────────────────
ACTIVE_SESSIONS = Gauge(
    "active_terminal_sessions",
    "Active terminal sessions.",
    ["environment"],
)
ACTIVE_ATTEMPTS = Gauge(
    "active_mission_attempts",
    "Mission attempts in progress.",
    ["environment"],
)
RETENTION_DELETIONS = Counter(
    "retention_deleted_total",
    "Records deleted by the retention policy.",
    # 테이블 이름만 label 로 쓴다. 사용자·attempt 식별자는 넣지 않는다.
    ["table"],
)
CLEANUP_FAILURES = Counter(
    "cleanup_failure_total",
    "Cleanup operations that did not complete.",
    ["environment", "kind"],
)


def command_category(argv: list[str]) -> str:
    """명령을 저카디널리티 범주로 줄인다.

    `kubectl get pods -n user-abc` → `kubectl:get`
    사용자 입력이 그대로 label 이 되면 시계열이 무한히 늘어난다.
    """
    if not argv:
        return "unknown"
    binary = argv[0]
    if len(argv) > 1 and not argv[1].startswith("-"):
        return f"{binary}:{argv[1]}"
    return binary
