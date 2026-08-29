"""환경별 훈련 샌드박스의 생성과 정리를 담당한다."""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from uuid import UUID

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from app.core.config import settings
from app.core.environments import DOCKER, EnvironmentId, KUBERNETES
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
    TOOLBOX_CONTAINER = "toolbox"
    DIND_CONTAINER = "dind"
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
        # 이미지·타임아웃은 설정에서 읽는다. 이미지를 하드코딩하면 태그가 사라졌을 때
        # 샌드박스가 뜨지 않고, 배포 환경에서는 immutable tag/digest 로 고정해야 한다.
        # 인스턴스 속성이라 테스트에서 덮어쓸 수 있다.
        self.TOOLBOX_IMAGE = settings.SANDBOX_TOOLBOX_IMAGE
        self.READINESS_TIMEOUT_SECONDS = settings.SANDBOX_READINESS_TIMEOUT_SECONDS
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
        """사용자 샌드박스를 멱등 생성하고 readiness를 기다린다."""
        if environment not in self._PROVISIONERS:
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
        # 환경마다 프로비저너 클래스를 새로 만들지 않는다. 공통 격리 설정은 위에서 끝나고,
        # 아래 분기만 환경별로 다르다.
        provision = self._PROVISIONERS[environment]
        container_name = provision(self, namespace, name, labels)
        self._wait_until_ready(namespace, name)
        return SandboxRef(
            id=sandbox_id,
            namespace=namespace,
            pod_name=name,
            container_name=container_name,
            environment=environment,
        )

    def _provision_kubernetes(self, namespace: str, name: str, labels: dict) -> str:
        self._ensure_service_account(namespace, name, labels)
        self._ensure_role(namespace, name, labels)
        self._ensure_role_binding(namespace, name, labels)
        self._ensure_toolbox_pod(namespace, name, labels)
        return self.TOOLBOX_CONTAINER

    def _provision_docker(self, namespace: str, name: str, labels: dict) -> str:
        # Docker 환경은 Kubernetes API 를 쓰지 않으므로 ServiceAccount/Role 을 붙이지 않는다.
        # 토큰도 마운트하지 않아 클러스터 접근 경로 자체를 없앤다.
        self._ensure_dind_pod(namespace, name, labels)
        return self.DIND_CONTAINER

    def _exec_in_sandbox(self, namespace: str, pod: str, container: str, argv: list[str]) -> str:
        from kubernetes.stream import stream

        return stream(
            self._core_api.connect_get_namespaced_pod_exec,
            pod,
            namespace,
            container=container,
            command=argv,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
        )

    def ensure_training_workload(self, sandbox: SandboxRef) -> None:
        """Docker 샌드박스 안에 훈련 대상 컨테이너를 멱등 생성한다.

        Kubernetes 환경의 nginx Deployment 에 해당하는 역할이다. 이미 있으면
        다시 만들지 않고, 멈춰 있으면 다시 띄운다.
        """
        if sandbox.environment != DOCKER:
            return

        name = settings.SANDBOX_TRAINING_CONTAINER
        existing = self._exec_in_sandbox(
            sandbox.namespace,
            sandbox.pod_name,
            sandbox.container_name,
            ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}} {{.State}}"],
        ).strip()

        if not existing:
            self._exec_in_sandbox(
                sandbox.namespace,
                sandbox.pod_name,
                sandbox.container_name,
                [
                    "docker", "run", "-d",
                    "--name", name,
                    "--restart", "unless-stopped",
                    settings.SANDBOX_TRAINING_IMAGE,
                ],
            )
            return

        if "running" not in existing:
            self._exec_in_sandbox(
                sandbox.namespace,
                sandbox.pod_name,
                sandbox.container_name,
                ["docker", "start", name],
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

    def _ensure_dind_pod(self, namespace: str, name: str, labels: dict) -> None:
        """Docker-in-Docker 샌드박스 Pod.

        privileged 를 쓰는 이유(BE-11 실측):
        rootless DinD(`docker:27-dind-rootless`)를 세 가지 방식으로 시도했으나
        모두 데몬 기동에 실패했다.
          - 기본(rootlesskit builtin): `ip tuntap add name tap0` 실패
          - `DOCKERD_ROOTLESS_ROOTLESSKIT_NET=slirp4netns`: 이미지에 바이너리 없음
          - `NET_ADMIN` + `SYS_ADMIN` capability 추가: sysfs mount 거부, TAP 실패
        같은 클러스터에서 privileged DinD 는 정상 기동했다(docker 27.5.1).

        대신 격리를 다음으로 좁힌다.
          - 사용자 네임스페이스 안에서만 생성되고 기본 deny NetworkPolicy 가 적용된다
          - 호스트 docker.sock 을 마운트하지 않는다(데몬을 컨테이너 안에서 새로 띄운다)
          - ServiceAccount 토큰을 마운트하지 않아 Kubernetes API 에 접근할 수 없다
          - CPU/메모리/ephemeral-storage 상한을 건다
        """
        try:
            self._core_api.read_namespaced_pod(name, namespace)
            return
        except ApiException as exc:
            if not self._is_not_found(exc):
                raise

        self._core_api.create_namespaced_pod(
            namespace,
            client.V1Pod(
                metadata=client.V1ObjectMeta(name=name, labels=labels),
                spec=client.V1PodSpec(
                    automount_service_account_token=False,
                    restart_policy="Always",
                    containers=[
                        client.V1Container(
                            name=self.DIND_CONTAINER,
                            image=settings.SANDBOX_DIND_IMAGE,
                            security_context=client.V1SecurityContext(privileged=True),
                            env=[
                                # TLS 를 끄고 유닉스 소켓만 쓴다. 데몬을 네트워크에 열지 않는다.
                                client.V1EnvVar(name="DOCKER_TLS_CERTDIR", value=""),
                            ],
                            resources=client.V1ResourceRequirements(
                                requests={
                                    "cpu": "100m",
                                    "memory": "256Mi",
                                    "ephemeral-storage": "512Mi",
                                },
                                limits={
                                    "cpu": settings.SANDBOX_DIND_CPU_LIMIT,
                                    "memory": settings.SANDBOX_DIND_MEMORY_LIMIT,
                                    "ephemeral-storage": settings.SANDBOX_DIND_STORAGE_LIMIT,
                                },
                            ),
                            readiness_probe=client.V1Probe(
                                _exec=client.V1ExecAction(command=["docker", "info"]),
                                initial_delay_seconds=5,
                                period_seconds=5,
                                failure_threshold=12,
                            ),
                        )
                    ],
                ),
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


# environment → 프로비저닝 함수. 새 환경은 여기에 등록한다.
SandboxService._PROVISIONERS = {
    KUBERNETES: SandboxService._provision_kubernetes,
    DOCKER: SandboxService._provision_docker,
}
