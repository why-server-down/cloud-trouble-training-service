import pytest

from app.services.validation_service import (
    K8sValidationService,
    MockValidationService,
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
