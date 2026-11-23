import sys
from pathlib import Path
from types import SimpleNamespace

AI_DATA = Path(__file__).resolve().parents[1]
if str(AI_DATA) not in sys.path:
    sys.path.insert(0, str(AI_DATA))

import observability_bridge


class _Metric:
    def __init__(self):
        self.labels_seen = []
        self.values = []

    def labels(self, **labels):
        self.labels_seen.append(labels)
        return self

    def inc(self, value=1):
        self.values.append(value)


def test_ingestion_changes_have_only_operation_and_result_labels(monkeypatch):
    metric = _Metric()
    backend = AI_DATA.parent / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    import app.core.metrics
    monkeypatch.setattr(app.core.metrics, "AI_INGESTION_CHANGES", metric)

    observability_bridge.record_ingestion_changes(
        SimpleNamespace(added=2, updated=1, deleted=0),
    )
    observability_bridge.record_ingestion_changes(error=True)

    assert metric.labels_seen == [
        {"operation": "added", "result": "success"},
        {"operation": "updated", "result": "success"},
        {"operation": "sync", "result": "error"},
    ]
    assert metric.values == [2, 1, 1]
