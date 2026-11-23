"""백엔드가 함께 실행될 때만 ingestion 메트릭을 기록한다."""
from __future__ import annotations


def record_ingestion_changes(report=None, *, error: bool = False) -> None:
    try:
        from app.core.metrics import AI_INGESTION_CHANGES
    except ImportError:
        return

    if error:
        AI_INGESTION_CHANGES.labels(operation="sync", result="error").inc()
        return

    for operation in ("added", "updated", "deleted"):
        count = getattr(report, operation, 0)
        if count:
            AI_INGESTION_CHANGES.labels(
                operation=operation, result="success",
            ).inc(count)
