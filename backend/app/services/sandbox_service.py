"""환경별 훈련 샌드박스의 생성과 정리를 담당한다."""

import asyncio
import hashlib
import pathlib
import logging
import time
from dataclasses import dataclass
from uuid import UUID

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from app.core.config import settings
from app.core.metrics import SANDBOX_PROVISION, SANDBOX_PROVISION_DURATION
from app.core.environments import DOCKER, LINUX, EnvironmentId, KUBERNETES
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
    LINUX_CONTAINER = "shell"
    LINUX_WORKDIR_VOLUME = "afterfail-workdir"
    LINUX_SUPERVISOR_VOLUME = "afterfail-supervisor"
    LINUX_SUPERVISOR_DIR = "/opt/afterfail"
    LINUX_SUPERVISOR_FILE = "supervisor.sh"
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
        started = time.perf_counter()
        try:
            reference = await loop.run_in_executor(
                None,
                lambda: self._ensure_sync(namespace, sandbox_id, environment),
            )
        except Exception:
            SANDBOX_PROVISION.labels(environment, "error").inc()
            await loop.run_in_executor(
                None,
                lambda: self._cleanup_sync(namespace, sandbox_id),
            )
            raise

        SANDBOX_PROVISION.labels(environment, "ok").inc()
        SANDBOX_PROVISION_DURATION.labels(environment).observe(
            time.perf_counter() - started
        )
        return reference

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
        """DB 세션 값으로 서버가 신뢰할 수 있는 샌드박스 참조를 복원한다.

        컨테이너 이름은 환경마다 다르다. 여기서 고정값을 쓰면 Docker 샌드박스에
        exec 할 때 "container toolbox is not valid for pod ..." 로 실패한다.
        """
        sandbox_id = self.stable_identifier(user_id, environment)
        return SandboxRef(
            id=sandbox_id,
            namespace=namespace,
            pod_name=self._resource_name(sandbox_id),
            container_name=self.container_name_for(environment),
            environment=environment,
        )

    @classmethod
    def container_name_for(cls, environment: str) -> str:
        return cls._CONTAINER_NAMES.get(environment, cls.TOOLBOX_CONTAINER)

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

    def _provision_kubernetes(self, namespace: str, name: str, labels: dict) -> str:  # noqa: D401
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

    def exec_in_sandbox(self, sandbox: "SandboxRef", argv: list[str]) -> str:
        """샌드박스 안에서 argv 를 실행하고 출력을 돌려준다.

        실행 대상은 서버가 만든 SandboxRef 로만 지정된다.
        """
        return self._exec_in_sandbox(
            sandbox.namespace, sandbox.pod_name, sandbox.container_name, argv
        )

    @staticmethod
    def _supervisor_script() -> str:
        path = (
            pathlib.Path(__file__).parent / "sandbox_assets" / "linux_supervisor.sh"
        )
        return path.read_text()

    def _ensure_supervisor_config(self, namespace: str, name: str, labels: dict) -> None:
        """supervisor 스크립트를 ConfigMap 으로 넣는다.

        이미지에 스크립트를 굽지 않는 이유: 커스텀 이미지 빌드와 레지스트리가 필요해진다.
        내용이 바뀌면 갱신한다.
        """
        body = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=name, labels=labels),
            data={self.LINUX_SUPERVISOR_FILE: self._supervisor_script()},
        )
        try:
            existing = self._core_api.read_namespaced_config_map(name, namespace)
        except ApiException as exc:
            if not self._is_not_found(exc):
                raise
            self._core_api.create_namespaced_config_map(namespace, body)
            return

        if existing.data != body.data:
            self._core_api.replace_namespaced_config_map(name, namespace, body)

    def _provision_linux(self, namespace: str, name: str, labels: dict) -> str:
        """Linux 샌드박스 Pod.

        호스트 자원을 일절 붙이지 않는다. 장애는 컨테이너 cgroup 과
        ephemeral storage 범위 안에서만 재현된다.
          - host PID / host network / host filesystem 을 mount 하지 않는다
          - ServiceAccount 토큰을 마운트하지 않아 Kubernetes API 에 접근할 수 없다
          - privileged 를 쓰지 않는다(Docker 환경과 달리 데몬이 필요 없다)
          - CPU/메모리/ephemeral-storage 상한과 PID 상한을 건다
        """
        self._ensure_supervisor_config(namespace, name, labels)
        try:
            self._core_api.read_namespaced_pod(name, namespace)
            return self.LINUX_CONTAINER
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
                    host_pid=False,
                    host_network=False,
                    host_ipc=False,
                    containers=[
                        client.V1Container(
                            name=self.LINUX_CONTAINER,
                            image=settings.SANDBOX_LINUX_IMAGE,
                            # exec 으로 띄운 백그라운드 프로세스는 세션 종료와 함께
                            # 정리된다. 장애 워크로드는 PID 1 인 supervisor 가 띄운다.
                            command=[
                                "/bin/sh",
                                f"{self.LINUX_SUPERVISOR_DIR}/{self.LINUX_SUPERVISOR_FILE}",
                            ],
                            env=[
                                client.V1EnvVar(
                                    name="AFTERFAIL_WORKDIR",
                                    value=settings.SANDBOX_LINUX_WORKDIR,
                                )
                            ],
                            security_context=client.V1SecurityContext(
                                privileged=False,
                                allow_privilege_escalation=False,
                            ),
                            resources=client.V1ResourceRequirements(
                                requests={
                                    "cpu": "50m",
                                    "memory": "64Mi",
                                    "ephemeral-storage": "256Mi",
                                },
                                limits={
                                    "cpu": settings.SANDBOX_LINUX_CPU_LIMIT,
                                    "memory": settings.SANDBOX_LINUX_MEMORY_LIMIT,
                                    "ephemeral-storage": settings.SANDBOX_LINUX_STORAGE_LIMIT,
                                },
                            ),
                            volume_mounts=[
                                client.V1VolumeMount(
                                    name=self.LINUX_WORKDIR_VOLUME,
                                    mount_path=settings.SANDBOX_LINUX_WORKDIR,
                                ),
                                client.V1VolumeMount(
                                    name=self.LINUX_SUPERVISOR_VOLUME,
                                    mount_path=self.LINUX_SUPERVISOR_DIR,
                                    read_only=True,
                                ),
                            ],
                        )
                    ],
                    volumes=[
                        # tmpfs 로 마운트해야 크기 상한이 컨테이너 안 df 에 보인다.
                        # ephemeral-storage 상한은 kubelet 검사용이라 df 에 나타나지 않아
                        # 사용자가 디스크 압박을 관측할 수 없다.
                        client.V1Volume(
                            name=self.LINUX_WORKDIR_VOLUME,
                            empty_dir=client.V1EmptyDirVolumeSource(
                                medium="Memory",
                                size_limit=settings.SANDBOX_LINUX_WORKDIR_SIZE,
                            ),
                        ),
                        client.V1Volume(
                            name=self.LINUX_SUPERVISOR_VOLUME,
                            config_map=client.V1ConfigMapVolumeSource(name=name),
                        ),
                    ],
                ),
            ),
        )
        return self.LINUX_CONTAINER

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
    LINUX: SandboxService._provision_linux,
}

SandboxService._CONTAINER_NAMES = {
    KUBERNETES: SandboxService.TOOLBOX_CONTAINER,
    DOCKER: SandboxService.DIND_CONTAINER,
    LINUX: SandboxService.LINUX_CONTAINER,
}
