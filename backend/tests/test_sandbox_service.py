import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from kubernetes.client.rest import ApiException

from app.services.sandbox_service import SandboxNotReadyError, SandboxService


def _not_found(*args, **kwargs):
    raise ApiException(status=404)


def _ready_pod():
    return SimpleNamespace(
        status=SimpleNamespace(
            conditions=[SimpleNamespace(type="Ready", status="True")]
        )
    )


def _service():
    core = MagicMock()
    rbac = MagicMock()
    networking = MagicMock()
    setup = MagicMock()
    setup.setup_user_namespace = AsyncMock()

    for method in (
        "read_namespaced_resource_quota",
        "read_namespaced_limit_range",
        "read_namespaced_service_account",
    ):
        getattr(core, method).side_effect = _not_found
    core.read_namespaced_pod.side_effect = [ApiException(status=404), _ready_pod()]
    rbac.read_namespaced_role.side_effect = _not_found
    rbac.read_namespaced_role_binding.side_effect = _not_found
    networking.read_namespaced_network_policy.side_effect = _not_found
    return SandboxService(
        core_api=core,
        rbac_api=rbac,
        networking_api=networking,
        k8s_setup=setup,
    ), core, rbac, networking, setup


class TestSandboxService:
    @pytest.mark.asyncio
    async def test_creates_namespaced_resources_without_raw_user_label(self):
        service, core, rbac, _, setup = _service()
        user_id = uuid.uuid4()

        sandbox = await service.ensure(
            user_id=user_id,
            namespace=f"user-{user_id}",
            environment="kubernetes",
        )

        setup.setup_user_namespace.assert_awaited_once()
        pod = core.create_namespaced_pod.call_args.args[1]
        assert str(user_id) not in pod.metadata.labels.values()
        assert pod.metadata.labels["afterfail.io/sandbox"] == sandbox.id
        assert pod.metadata.labels["afterfail.io/environment"] == "kubernetes"
        assert pod.spec.service_account_name == sandbox.pod_name
        role = rbac.create_namespaced_role.call_args.args[1]
        assert role.metadata.namespace is None

    @pytest.mark.asyncio
    async def test_ensure_is_idempotent_when_resources_exist(self):
        service, core, rbac, networking, _ = _service()
        for method in (
            "read_namespaced_resource_quota",
            "read_namespaced_limit_range",
            "read_namespaced_service_account",
        ):
            getattr(core, method).side_effect = None
        core.read_namespaced_pod.side_effect = None
        core.read_namespaced_pod.return_value = _ready_pod()
        rbac.read_namespaced_role.side_effect = None
        rbac.read_namespaced_role_binding.side_effect = None
        networking.read_namespaced_network_policy.side_effect = None

        await service.ensure(
            user_id=uuid.uuid4(), namespace="user-existing", environment="kubernetes"
        )

        assert not core.create_namespaced_pod.called
        assert not core.create_namespaced_resource_quota.called
        assert not rbac.create_namespaced_role.called

    @pytest.mark.asyncio
    async def test_readiness_failure_cleans_only_session_resources(self):
        service, core, rbac, _, _ = _service()
        service.READINESS_TIMEOUT_SECONDS = 0
        core.read_namespaced_pod.side_effect = _not_found

        with pytest.raises(SandboxNotReadyError):
            await service.ensure(
                user_id=uuid.uuid4(),
                namespace="user-timeout",
                environment="kubernetes",
            )

        core.delete_namespaced_pod.assert_called_once()
        rbac.delete_namespaced_role.assert_called_once()
        assert not hasattr(core, "delete_namespace") or not core.delete_namespace.called

    def test_different_users_have_different_stable_identifiers(self):
        first = SandboxService.stable_identifier(uuid.uuid4(), "kubernetes")
        second = SandboxService.stable_identifier(uuid.uuid4(), "kubernetes")
        assert first != second
        assert len(first) == 16
