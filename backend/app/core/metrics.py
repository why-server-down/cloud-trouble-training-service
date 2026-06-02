from prometheus_client import Counter, Histogram

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
