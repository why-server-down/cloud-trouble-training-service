import pytest

from app.services.validation_service import (
    K8sValidationService,
    MissionValidationQueries,
    MockValidationService,
    PrometheusValidationService,
    RETRY_MESSAGE,
    ValidationResult,
)


@pytest.mark.asyncio
async def test_mock_validation_hides_resolution_details():
    service = MockValidationService()

    result = await service.check_resolution("pod_failure", "user-test")

    assert not result.is_resolved
    assert result.message == RETRY_MESSAGE


@pytest.mark.asyncio
async def test_k8s_validation_hides_resolution_details():
    service = K8sValidationService.__new__(K8sValidationService)
    service._check_resolution_sync = lambda chaos_type, namespace: ValidationResult(
        is_resolved=False,
        message="메모리 제한을 10Mi보다 크게 패치하세요.",
    )

    result = await service.check_resolution("memory_stress", "user-test")

    assert not result.is_resolved
    assert result.message == RETRY_MESSAGE


def test_prometheus_queries_are_scoped_to_namespace():
    query = MissionValidationQueries.get_query("service_misconfig", "user-test")

    assert 'namespace="user-test"' in query
    assert 'endpoint="webapp-svc"' in query


def test_prometheus_query_rejects_invalid_namespace():
    with pytest.raises(ValueError):
        MissionValidationQueries.get_query("pod_failure", 'user-test"} or vector(1)')


def test_prometheus_result_requires_positive_series():
    assert PrometheusValidationService._is_resolved(
        {"status": "success", "data": {"result": [{"value": [0, "1"]}]}}
    )
    assert not PrometheusValidationService._is_resolved(
        {"status": "success", "data": {"result": []}}
    )
    assert not PrometheusValidationService._is_resolved(
        {"status": "success", "data": {"result": [{"value": [0, "0"]}]}}
    )


@pytest.mark.asyncio
async def test_prometheus_validation_hides_query_errors():
    service = PrometheusValidationService("http://prometheus.invalid")

    async def fail(_query):
        raise RuntimeError("query details")

    service._prometheus.query = fail

    result = await service.check_resolution("pod_failure", "user-test")

    assert not result.is_resolved
    assert result.message == RETRY_MESSAGE
