from types import SimpleNamespace

from app.services import scenario_service


class _Metric:
    def __init__(self):
        self.labels_seen = []
        self.value = 0

    def labels(self, **labels):
        self.labels_seen.append(labels)
        return self

    def inc(self):
        self.value += 1


def test_validation_agreement_uses_only_bounded_context(monkeypatch):
    metric = _Metric()
    monkeypatch.setattr(scenario_service, "AI_VALIDATION_AGREEMENT", metric)

    scenario_service._record_validation_agreement(
        provider="openai", environment="docker", mechanical=False,
        judgment=SimpleNamespace(resolved=False),
    )
    scenario_service._record_validation_agreement(
        provider="openai", environment="docker", mechanical=False,
        judgment=SimpleNamespace(resolved=True),
    )
    scenario_service._record_validation_agreement(
        provider="openai", environment="docker", mechanical=False,
        judgment=None,
    )

    assert metric.labels_seen == [
        {"provider": "openai", "environment": "docker", "agreement": "agree"},
        {"provider": "openai", "environment": "docker", "agreement": "disagree"},
        {"provider": "openai", "environment": "docker", "agreement": "unavailable"},
    ]
    assert metric.value == 3
