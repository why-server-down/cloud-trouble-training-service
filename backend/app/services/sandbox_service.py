"""환경별 훈련 샌드박스의 생성과 정리를 담당한다."""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from uuid import UUID

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from app.core.environments import EnvironmentId, KUBERNETES
from app.services.k8s_setup import K8sSetupService, get_k8s_setup_service

logger = logging.getLogger(__name__)

_MANAGED_BY_LABEL = "afterfail.io/managed-by"
_SANDBOX_LABEL = "afterfail.io/sandbox"
_ENVIRONMENT_LABEL = "afterfail.io/environment"


@dataclass(frozen=True)
class SandboxRef:
    """서버가 확인한 명령 실행 대상."""

    id: str
    namespace: str
    pod_name: str
    container_name: str
    environment: EnvironmentId


class SandboxNotReadyError(RuntimeError):
    """제한 시간 안에 샌드박스가 준비되지 않은 경우."""


class SandboxService:
    TOOLBOX_IMAGE = "bitnami/kubectl:1.29"
    TOOLBOX_CONTAINER = "toolbox"
    READINESS_TIMEOUT_SECONDS = 30.0
    READINESS_POLL_SECONDS = 1.0

    def __init__(
        self,
        *,
        core_api=None,
        rbac_api=None,
        networking_api=None,
        k8s_setup: K8sSetupService | None = None,
    ):
        if core_api is None or rbac_api is None or networking_api is None:
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
        self._core_api = core_api or client.CoreV1Api()
        self._rbac_api = rbac_api or client.RbacAuthorizationV1Api()
        self._networking_api = networking_api or client.NetworkingV1Api()
        self._k8s_setup = k8s_setup or get_k8s_setup_service()

    async def ensure(
        self,
        *,
        user_id: UUID | str,
        namespace: str,
        environment: EnvironmentId = KUBERNETES,
    ) -> SandboxRef:
        """사용자 샌드박스를 멱등 생성하고 toolbox readiness를 기다린다."""
        if environment != KUBERNETES:
            raise ValueError(f"지원하지 않는 샌드박스 환경입니다: {environment}")

        sandbox_id = self.stable_identifier(user_id, environment)
        await self._k8s_setup.setup_user_namespace(namespace)
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None,
                lambda: self._ensure_sync(namespace, sandbox_id, environment),
            )
        except Exception:
            await loop.run_in_executor(
                None,
                lambda: self._cleanup_sync(namespace, sandbox_id),
            )
            raise

    async def cleanup(self, sandbox: SandboxRef) -> None:
        """네임스페이스는 보존하고 해당 샌드박스 리소스만 제거한다."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._cleanup_sync(sandbox.namespace, sandbox.id),
        )

    @staticmethod
    def stable_identifier(user_id: UUID | str, environment: str) -> str:
        raw = f"{user_id}:{environment}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    @staticmethod
    def _resource_name(sandbox_id: str) -> str:
        return f"sandbox-{sandbox_id}"

    def reference_for(
        self,
        *,
        user_id: UUID | str,
        namespace: str,
        environment: EnvironmentId,
    ) -> SandboxRef:
        """DB 세션 값으로 서버가 신뢰할 수 있는 샌드박스 참조를 복원한다."""
        sandbox_id = self.stable_identifier(user_id, environment)
        return SandboxRef(
            id=sandbox_id,
            namespace=namespace,
            pod_name=self._resource_name(sandbox_id),
            container_name=self.TOOLBOX_CONTAINER,
            environment=environment,
        )

    def _ensure_sync(
        self, namespace: str, sandbox_id: str, environment: EnvironmentId
    ) -> SandboxRef:
        name = self._resource_name(sandbox_id)
        labels = {
            _MANAGED_BY_LABEL: "sandbox-service",
            _SANDBOX_LABEL: sandbox_id,
            _ENVIRONMENT_LABEL: environment,
        }
        self._ensure_resource_quota(namespace)
        self._ensure_limit_range(namespace)
        self._ensure_default_deny_network_policy(namespace)
        self._ensure_service_account(namespace, name, labels)
        self._ensure_role(namespace, name, labels)
        self._ensure_role_binding(namespace, name, labels)
        self._ensure_toolbox_pod(namespace, name, labels)
        self._wait_until_ready(namespace, name)
        return SandboxRef(
            id=sandbox_id,
            namespace=namespace,
            pod_name=name,
            container_name=self.TOOLBOX_CONTAINER,
            environment=environment,
        )

    @staticmethod
    def _is_not_found(exc: ApiException) -> bool:
        return exc.status == 404

    def _ensure_resource_quota(self, namespace: str) -> None:
        name = "afterfail-quota"
        try:
            self._core_api.read_namespaced_resource_quota(name, namespace)
        except ApiException as exc:
            if not self._is_not_found(exc):
                raise
            self._core_api.create_namespaced_resource_quota(
                namespace,
                client.V1ResourceQuota(
                    metadata=client.V1ObjectMeta(name=name),
                    spec=client.V1ResourceQuotaSpec(
                        hard={
                            "requests.cpu": "2",
                            "requests.memory": "2Gi",
                            "limits.cpu": "4",
                            "limits.memory": "4Gi",
                            "pods": "10",
                        }
                    ),
                ),
            )

    def _ensure_limit_range(self, namespace: str) -> None:
        name = "afterfail-limits"
        try:
            self._core_api.read_namespaced_limit_range(name, namespace)
        except ApiException as exc:
            if not self._is_not_found(exc):
                raise
            self._core_api.create_namespaced_limit_range(
                namespace,
                client.V1LimitRange(
                    metadata=client.V1ObjectMeta(name=name),
                    spec=client.V1LimitRangeSpec(
                        limits=[
                            client.V1LimitRangeItem(
                                type="Container",
                                default={"cpu": "500m", "memory": "512Mi"},
                                default_request={"cpu": "50m", "memory": "64Mi"},
                            )
                        ]
                    ),
                ),
            )

    def _ensure_default_deny_network_policy(self, namespace: str) -> None:
        name = "afterfail-default-deny-ingress"
        try:
            self._networking_api.read_namespaced_network_policy(name, namespace)
        except ApiException as exc:
            if not self._is_not_found(exc):
                raise
            self._networking_api.create_namespaced_network_policy(
                namespace,
                client.V1NetworkPolicy(
                    metadata=client.V1ObjectMeta(name=name),
                    spec=client.V1NetworkPolicySpec(
                        pod_selector=client.V1LabelSelector(match_labels={}),
                        policy_types=["Ingress"],
                        ingress=[],
                    ),
                ),
            )

    def _ensure_service_account(self, namespace: str, name: str, labels: dict) -> None:
        try:
            self._core_api.read_namespaced_service_account(name, namespace)
        except ApiException as exc:
            if not self._is_not_found(exc):
                raise
            self._core_api.create_namespaced_service_account(
                namespace,
                client.V1ServiceAccount(
                    metadata=client.V1ObjectMeta(name=name, labels=labels)
                ),
            )

    def _ensure_role(self, namespace: str, name: str, labels: dict) -> None:
        try:
            self._rbac_api.read_namespaced_role(name, namespace)
        except ApiException as exc:
            if not self._is_not_found(exc):
                raise
            self._rbac_api.create_namespaced_role(
                namespace,
                client.V1Role(
                    metadata=client.V1ObjectMeta(name=name, labels=labels),
                    rules=[
                        client.V1PolicyRule(
                            api_groups=[""],
                            resources=[
                                "pods",
                                "pods/log",
                                "services",
                                "endpoints",
                                "events",
                                "configmaps",
                                "secrets",
                                "persistentvolumeclaims",
                            ],
                            verbs=["get", "list", "watch", "create", "update", "patch", "delete"],
                        ),
                        client.V1PolicyRule(
                            api_groups=["apps"],
                            resources=["deployments", "replicasets"],
                            verbs=["get", "list", "watch", "update", "patch"],
                        ),
                    ],
                ),
            )

    def _ensure_role_binding(self, namespace: str, name: str, labels: dict) -> None:
        try:
            self._rbac_api.read_namespaced_role_binding(name, namespace)
        except ApiException as exc:
            if not self._is_not_found(exc):
                raise
            self._rbac_api.create_namespaced_role_binding(
                namespace,
                client.V1RoleBinding(
                    metadata=client.V1ObjectMeta(name=name, labels=labels),
                    role_ref=client.V1RoleRef(
                        api_group="rbac.authorization.k8s.io",
                        kind="Role",
                        name=name,
                    ),
                    subjects=[
                        client.RbacV1Subject(
                            kind="ServiceAccount", name=name, namespace=namespace
                        )
                    ],
                ),
            )

    def _ensure_toolbox_pod(self, namespace: str, name: str, labels: dict) -> None:
        try:
            self._core_api.read_namespaced_pod(name, namespace)
        except ApiException as exc:
            if not self._is_not_found(exc):
                raise
            self._core_api.create_namespaced_pod(
                namespace,
                client.V1Pod(
                    metadata=client.V1ObjectMeta(name=name, labels=labels),
                    spec=client.V1PodSpec(
                        service_account_name=name,
                        automount_service_account_token=True,
                        restart_policy="Always",
                        containers=[
                            client.V1Container(
                                name=self.TOOLBOX_CONTAINER,
                                image=self.TOOLBOX_IMAGE,
                                command=["/bin/sh", "-c", "trap : TERM INT; sleep infinity & wait"],
                                resources=client.V1ResourceRequirements(
                                    requests={"cpu": "25m", "memory": "32Mi"},
                                    limits={"cpu": "250m", "memory": "256Mi"},
                                ),
                            )
                        ],
                    ),
                ),
            )

    def _wait_until_ready(self, namespace: str, name: str) -> None:
        deadline = time.monotonic() + self.READINESS_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            pod = self._core_api.read_namespaced_pod(name, namespace)
            conditions = getattr(getattr(pod, "status", None), "conditions", None) or []
            if any(
                condition.type == "Ready" and condition.status == "True"
                for condition in conditions
            ):
                return
            time.sleep(self.READINESS_POLL_SECONDS)
        raise SandboxNotReadyError(
            f"toolbox Pod가 {self.READINESS_TIMEOUT_SECONDS:g}초 안에 준비되지 않았습니다"
        )

    def _cleanup_sync(self, namespace: str, sandbox_id: str) -> None:
        name = self._resource_name(sandbox_id)
        operations = (
            (self._core_api.delete_namespaced_pod, (name, namespace)),
            (self._rbac_api.delete_namespaced_role_binding, (name, namespace)),
            (self._rbac_api.delete_namespaced_role, (name, namespace)),
            (self._core_api.delete_namespaced_service_account, (name, namespace)),
        )
        for operation, args in operations:
            try:
                operation(*args)
            except ApiException as exc:
                if not self._is_not_found(exc):
                    logger.warning(
                        "샌드박스 리소스 정리 실패",
                        extra={"namespace": namespace, "resource": name},
                        exc_info=True,
                    )


_sandbox_service: SandboxService | None = None


def get_sandbox_service() -> SandboxService:
    global _sandbox_service
    if _sandbox_service is None:
        _sandbox_service = SandboxService()
    return _sandbox_service
