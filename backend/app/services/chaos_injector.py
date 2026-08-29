import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core import environments
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ChaosResult:
    success: bool
    chaos_id: str
    message: str


class BaseChaosInjector(ABC):
    """장애 주입기 공통 인터페이스.

    environment: 이 주입기가 담당하는 훈련 환경.
    docker/linux 환경 구현체는 후속 브랜치에서 이 클래스를 상속해 추가한다.
    """

    environment: str = environments.KUBERNETES

    @abstractmethod
    async def inject(self, chaos_type: str, namespace: str) -> ChaosResult:
        pass

    @abstractmethod
    async def revert(self, chaos_id: str, namespace: str) -> bool:
        """주입한 장애를 되돌린다.

        namespace 를 인자로 받는 이유: 서버가 재시작되면 프로세스 메모리의
        주입 이력이 사라진다. chaos_id 와 namespace 만으로 복구할 수 있어야
        DB 에 저장된 attempt.chaos_id 로 뒷정리가 가능하다.
        """

    @staticmethod
    def chaos_type_from_id(chaos_id: str) -> str | None:
        """chaos_id 에서 chaos_type 을 복원한다.

        inject 가 만드는 형식은 `{chaos-type}-{uuid8}` 이다.
        (예: `compound-probe-cascade-a1b2c3d4` -> `compound_probe_cascade`)
        """
        if not chaos_id:
            return None
        head, _, tail = chaos_id.rpartition("-")
        if not head or not tail:
            return None
        return head.replace("-", "_")

    def supported_chaos_types(self) -> frozenset[str] | None:
        """주입 가능한 chaos_type 집합. None이면 타입 제한 없음(Mock 등)."""
        return None

    def supports(self, chaos_type: str) -> bool:
        supported = self.supported_chaos_types()
        return supported is None or chaos_type in supported


class MockChaosInjector(BaseChaosInjector):
    """Docker 개발 환경용 Mock 구현. 실제 장애 주입 없이 시뮬레이션."""

    def __init__(
        self,
        delay: float = 0.5,
        environment: str = environments.KUBERNETES,
    ):
        self._delay = delay
        self.environment = environment
        self._active_chaos: dict[str, dict] = {}

    async def inject(self, chaos_type: str, namespace: str) -> ChaosResult:
        await asyncio.sleep(self._delay)
        # chaos_type 을 복원할 수 있는 형식을 실제 주입기와 동일하게 유지한다.
        chaos_id = f"{chaos_type.replace('_', '-')}-{uuid.uuid4().hex[:8]}"
        self._active_chaos[chaos_id] = {"type": chaos_type, "namespace": namespace}
        logger.info(
            "mock chaos injected",
            extra={"chaos_type": chaos_type, "namespace": namespace, "chaos_id": chaos_id},
        )
        return ChaosResult(
            success=True,
            chaos_id=chaos_id,
            message=f"[MOCK] {chaos_type} injected into {namespace}",
        )

    async def revert(self, chaos_id: str, namespace: str) -> bool:
        # 실제 리소스를 만들지 않으므로 프로세스 메모리에 없어도 성공으로 본다.
        # (서버 재시작 뒤 DB 의 chaos_id 로 정리하는 경로를 막지 않기 위함)
        self._active_chaos.pop(chaos_id, None)
        logger.info("mock chaos reverted", extra={"chaos_id": chaos_id, "namespace": namespace})
        return True


class ChaosMeshInjector(BaseChaosInjector):
    """Chaos Mesh 기반 실제 장애 주입 구현.

    chaos_type별 (주입, 복구) 핸들러는 클래스 하단 _CHAOS_HANDLERS 레지스트리에 등록한다.
    새 장애 타입 추가 시: _apply_*/_revert_* 메서드 작성 후 레지스트리에 한 줄 추가.
    """

    CHAOS_GROUP = "chaos-mesh.org"
    CHAOS_VERSION = "v1alpha1"

    @property
    def CHAOS_NAMESPACE(self) -> str:
        return settings.CHAOS_MESH_NAMESPACE

    def __init__(self):
        from kubernetes import client, config
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()

        self._custom_api = client.CustomObjectsApi()
        self._core_api = client.CoreV1Api()
        self._apps_api = client.AppsV1Api()
        self._active_chaos: dict[str, dict] = {}

    def supported_chaos_types(self) -> frozenset[str]:
        return frozenset(self._CHAOS_HANDLERS)

    async def inject(self, chaos_type: str, namespace: str) -> ChaosResult:
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None, lambda: self._inject_sync(chaos_type, namespace)
            )
        except Exception as e:
            return ChaosResult(
                success=False,
                chaos_id=f"error-{uuid.uuid4().hex[:8]}",
                message=str(e),
            )

    def _inject_sync(self, chaos_type: str, namespace: str) -> ChaosResult:
        handlers = self._CHAOS_HANDLERS.get(chaos_type)
        if handlers is None:
            raise ValueError(f"Unknown chaos_type: {chaos_type}")
        apply_handler, _ = handlers

        chaos_id = f"{chaos_type.replace('_', '-')}-{uuid.uuid4().hex[:8]}"
        try:
            apply_handler(self, chaos_id, namespace)
        except Exception:
            # 주입은 여러 단계를 밟는다. 중간에 실패하면 앞 단계가 그대로 남아
            # "아무도 시작하지 않았는데 깨져 있는" 환경이 된다. 되돌리고 올린다.
            _, revert_handler = handlers
            try:
                revert_handler(self, chaos_id, namespace)
            except Exception:
                logger.exception(
                    "partial chaos rollback failed",
                    extra={"chaos_id": chaos_id, "namespace": namespace},
                )
            raise

        self._active_chaos[chaos_id] = {"type": chaos_type, "namespace": namespace}
        logger.info(
            "chaos injected",
            extra={"chaos_type": chaos_type, "namespace": namespace, "chaos_id": chaos_id},
        )
        return ChaosResult(success=True, chaos_id=chaos_id, message=f"{chaos_type} injected into {namespace}")

    # --- 공통 헬퍼 ---

    def _patch_nginx_pod_spec(self, namespace: str, pod_spec: dict):
        """nginx Deployment의 pod template spec에 strategic merge patch."""
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={"spec": {"template": {"spec": pod_spec}}},
        )

    def _patch_nginx_container(self, namespace: str, **fields):
        """nginx 컨테이너 필드 patch. fields에 None을 주면 해당 필드 제거."""
        self._patch_nginx_pod_spec(namespace, {"containers": [{"name": "nginx", **fields}]})

    @staticmethod
    def _delete_ignore_404(delete_fn, *, name: str, namespace: str):
        from kubernetes.client.rest import ApiException  # type: ignore[attr-defined]
        try:
            delete_fn(name=name, namespace=namespace)
        except ApiException as e:
            if e.status != 404:
                raise

    def _remove_nginx_volume(self, namespace: str, volume_name: str):
        """nginx Deployment에서 특정 volume/volumeMount 제거.

        strategic merge patch는 배열 원소 삭제가 불안정하므로 read-modify-replace 사용.
        """
        dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
        spec = dep.spec.template.spec
        if spec.volumes:
            spec.volumes = [v for v in spec.volumes if v.name != volume_name] or None
        for c in spec.containers:
            if c.name == "nginx" and c.volume_mounts:
                c.volume_mounts = [vm for vm in c.volume_mounts if vm.name != volume_name] or None
        self._apps_api.replace_namespaced_deployment(name="nginx", namespace=namespace, body=dep)

    # --- 주입 핸들러 ---

    def _apply_pod_chaos(self, _chaos_id: str, namespace: str):
        # nginx 이미지를 존재하지 않는 태그로 패치 → ImagePullBackOff 유발
        # 사용자 Fix: kubectl set image deployment/nginx nginx=nginx:latest -n {namespace}
        self._patch_nginx_container(namespace, image="nginx:wrongtag")

    def _apply_stress_chaos(self, chaos_id: str, namespace: str):
        # nginx 메모리 limit을 6Mi로 낮춘 뒤 StressChaos로 메모리 압박 → OOMKilled 유발
        # 사용자 Fix: kubectl patch deployment/nginx 으로 memory limit 상향 조정
        self._patch_nginx_container(
            namespace,
            resources={
                "requests": {"memory": "6Mi"},
                "limits": {"memory": "6Mi"},
            },
        )
        body = {
            "apiVersion": f"{self.CHAOS_GROUP}/{self.CHAOS_VERSION}",
            "kind": "StressChaos",
            "metadata": {"name": chaos_id, "namespace": self.CHAOS_NAMESPACE},
            "spec": {
                "mode": "all",
                "selector": {"namespaces": [namespace]},
                "stressors": {
                    "memory": {"workers": 1, "size": "64MB"}
                },
                "duration": "30m",
            },
        }
        self._custom_api.create_namespaced_custom_object(
            group=self.CHAOS_GROUP,
            version=self.CHAOS_VERSION,
            namespace=self.CHAOS_NAMESPACE,
            plural="stresschaos",
            body=body,
        )

    def _apply_network_chaos(self, _chaos_id: str, namespace: str):
        # Readiness Probe 실패 주입: 존재하지 않는 경로 체크 → Pod Ready 0/1 → 서비스 엔드포인트 제외
        # 사용자 Fix: kubectl patch deployment nginx 로 readinessProbe 제거 또는 경로 수정
        #
        # 전략을 먼저 바꾸는 이유: RollingUpdate 기본값(maxSurge 25%)에서는 새 Pod 가
        # Ready 가 되지 못하면 기존 Ready Pod 가 그대로 남는다. 그러면 엔드포인트가
        # 유지되어 서비스가 정상 동작하고, 사용자는 아무 장애도 겪지 않는다.
        # maxSurge=0 / maxUnavailable=1 로 두어야 기존 Pod 가 먼저 내려가고
        # NotReady 인 새 Pod 만 남아 실제로 서비스가 끊긴다.
        self._set_rollout_strategy(namespace, max_unavailable=1, max_surge=0)
        self._patch_nginx_container(
            namespace,
            readinessProbe={
                "httpGet": {
                    "path": "/healthz-notexist",
                    "port": 80,
                },
                "initialDelaySeconds": 5,
                "periodSeconds": 10,
                "failureThreshold": 3,
            },
        )

    def _set_rollout_strategy(self, namespace: str, *, max_unavailable, max_surge) -> None:
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={
                "spec": {
                    "strategy": {
                        "type": "RollingUpdate",
                        "rollingUpdate": {
                            "maxUnavailable": max_unavailable,
                            "maxSurge": max_surge,
                        },
                    }
                }
            },
        )

    def _apply_service_misconfig(self, _chaos_id: str, namespace: str):
        from kubernetes import client

        self._delete_ignore_404(self._apps_api.delete_namespaced_deployment, name="webapp", namespace=namespace)
        self._delete_ignore_404(self._core_api.delete_namespaced_service, name="webapp-svc", namespace=namespace)

        # webapp Deployment 생성 (label: app=webapp)
        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(name="webapp", namespace=namespace),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": "webapp"}),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "webapp"}),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="nginx",
                                image="nginx:latest",
                                ports=[client.V1ContainerPort(container_port=80)],
                            )
                        ]
                    ),
                ),
            ),
        )
        self._apps_api.create_namespaced_deployment(namespace=namespace, body=deployment)

        # Service selector를 의도적으로 잘못된 값으로 생성
        service = client.V1Service(
            metadata=client.V1ObjectMeta(name="webapp-svc", namespace=namespace),
            spec=client.V1ServiceSpec(
                selector={"app": "webapp-broken"},  # 잘못된 selector
                ports=[client.V1ServicePort(port=80, target_port=80)],
            ),
        )
        self._core_api.create_namespaced_service(namespace=namespace, body=service)

    def _apply_crash_loop(self, _chaos_id: str, namespace: str):
        # 컨테이너 command를 exit 1로 교체 → 즉시 종료 → CrashLoopBackOff
        # 사용자 Fix: kubectl patch deployment/nginx -p '{"spec":{"template":{"spec":{"containers":[{"name":"nginx","command":null}]}}}}'
        self._patch_nginx_container(namespace, command=["sh", "-c", "exit 1"])

    def _apply_liveness_probe(self, _chaos_id: str, namespace: str):
        # livenessProbe에 존재하지 않는 경로 주입 → probe 실패 → container kill & restart 반복
        # readinessProbe 실패와 차이: liveness는 container를 직접 재시작시킴 (restart count 증가)
        # 사용자 Fix: kubectl patch deployment/nginx -p '{"spec":{"template":{"spec":{"containers":[{"name":"nginx","livenessProbe":null}]}}}}'
        self._patch_nginx_container(
            namespace,
            livenessProbe={
                "httpGet": {
                    "path": "/healthz-notexist",
                    "port": 80,
                },
                "initialDelaySeconds": 5,
                "periodSeconds": 5,
                "failureThreshold": 1,
            },
        )

    def _apply_configmap_misconfig(self, _chaos_id: str, namespace: str):
        # nginx.conf 문법 오류가 있는 ConfigMap을 마운트 → nginx config test 실패 → CrashLoopBackOff
        # 사용자 Fix: kubectl edit configmap nginx-broken-config 으로 세미콜론/닫는 괄호 수정
        #            또는 kubectl patch deployment nginx 로 volume/volumeMount 제거 후 rollout restart
        from kubernetes import client

        cm_name = "nginx-broken-config"
        self._delete_ignore_404(self._core_api.delete_namespaced_config_map, name=cm_name, namespace=namespace)

        broken_conf = (
            "worker_processes 1;\n"
            "events { worker_connections 1024; }\n"
            "http {\n"
            "    server {\n"
            "        listen 80\n"
            "        server_name localhost\n"
            "        location / {\n"
            "            root /usr/share/nginx/html\n"
            "            index index.html index.htm\n"
            "        }\n"
            "    \n"
            "\n"
        )
        self._core_api.create_namespaced_config_map(
            namespace=namespace,
            body=client.V1ConfigMap(
                metadata=client.V1ObjectMeta(name=cm_name, namespace=namespace),
                data={"nginx.conf": broken_conf},
            ),
        )
        self._patch_nginx_pod_spec(
            namespace,
            {
                "volumes": [{"name": cm_name, "configMap": {"name": cm_name}}],
                "containers": [{
                    "name": "nginx",
                    "volumeMounts": [{
                        "name": cm_name,
                        "mountPath": "/etc/nginx/nginx.conf",
                        "subPath": "nginx.conf",
                    }],
                }],
            },
        )

    def _apply_init_container_failure(self, _chaos_id: str, namespace: str):
        # initContainer가 항상 실패 → Pod Init:CrashLoopBackOff 상태
        # readinessProbe/livenessProbe 실패와 달리 메인 컨테이너 자체가 시작되지 않음
        # 사용자 Fix: kubectl patch deployment nginx 로 initContainers 제거
        self._patch_nginx_pod_spec(
            namespace,
            {
                "initContainers": [{
                    "name": "init-check",
                    "image": "busybox:1.35",
                    "command": ["sh", "-c", "echo 'prerequisite check failed'; exit 1"],
                }]
            },
        )

    def _apply_node_selector_mismatch(self, _chaos_id: str, namespace: str):
        # 존재하지 않는 nodeSelector 추가 → 스케줄링 불가 → Pod Pending 상태
        # CrashLoop/Error가 아니라 아예 스케줄링이 안 되는 전혀 다른 증상
        # 사용자 Fix: kubectl patch deployment nginx -p '{"spec":{"template":{"spec":{"nodeSelector":null}}}}'
        self._patch_nginx_pod_spec(namespace, {"nodeSelector": {"disk": "ssd-nonexistent"}})

    def _apply_compound_probe_cascade(self, _chaos_id: str, namespace: str):
        # [cascade 복합 장애] wrongtag + readinessProbe 동시 주입
        # Phase 1 증상: ImagePullBackOff → 이미지 수정
        # Phase 2 드러남: 이미지 고치고 pod 뜨면 readinessProbe 실패로 여전히 Not Ready
        # 두 번 fix 필요 + 두 번째 문제는 첫 번째 해결 전까지 보이지 않음
        self._patch_nginx_container(
            namespace,
            image="nginx:wrongtag",
            readinessProbe={
                "httpGet": {"path": "/healthz-notexist", "port": 80},
                "initialDelaySeconds": 5,
                "periodSeconds": 10,
                "failureThreshold": 3,
            },
        )

    def _apply_wrong_image_registry(self, _chaos_id: str, namespace: str):
        # 접근 불가한 private registry 이미지로 패치 → unauthorized ImagePullBackOff
        # image_pull_error(태그 오류)와 다름: Events에 "unauthorized" 메시지
        # 사용자 Fix: kubectl set image deployment/nginx nginx=nginx:latest
        self._patch_nginx_container(namespace, image="private.registry.internal/nginx:latest")

    def _apply_secret_ref_missing(self, _chaos_id: str, namespace: str):
        # 존재하지 않는 Secret을 envFrom으로 참조 → CreateContainerConfigError
        # Pod가 Pending/ContainerCreating에서 멈춤 (이미지 오류와 다른 증상)
        # 사용자 Fix: kubectl create secret generic missing-app-secret --from-literal=key=value
        #            또는 kubectl patch deployment nginx 로 envFrom 제거
        self._patch_nginx_container(namespace, envFrom=[{"secretRef": {"name": "missing-app-secret"}}])

    def _apply_pvc_unbound(self, _chaos_id: str, namespace: str):
        # 존재하지 않는 storageClass의 PVC 생성 + 마운트 → Pod Pending (볼륨 바인딩 대기)
        # nodeSelector 실패(스케줄러)와 달리 스토리지 프로비저닝 실패
        # 사용자 Fix: PVC 삭제 후 deployment에서 volume/volumeMount 제거, 또는 올바른 PVC 생성
        from kubernetes import client

        pvc_name = "nginx-data"
        self._delete_ignore_404(
            self._core_api.delete_namespaced_persistent_volume_claim, name=pvc_name, namespace=namespace
        )

        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(name=pvc_name, namespace=namespace),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                storage_class_name="nonexistent-storage",
                resources=client.V1ResourceRequirements(requests={"storage": "1Gi"}),
            ),
        )
        self._core_api.create_namespaced_persistent_volume_claim(namespace=namespace, body=pvc)

        self._patch_nginx_pod_spec(
            namespace,
            {
                "volumes": [{"name": pvc_name, "persistentVolumeClaim": {"claimName": pvc_name}}],
                "containers": [{"name": "nginx", "volumeMounts": [{"name": pvc_name, "mountPath": "/data"}]}],
            },
        )

    def _apply_cpu_throttle(self, _chaos_id: str, namespace: str):
        # CPU limit을 1m으로 극도로 제한 + 빡빡한 readinessProbe → 0/1 Not Ready
        # OOMKilled와 달리 메모리 문제가 아닌 CPU 리소스 설정 문제
        # 사용자 Fix: kubectl patch deployment nginx 로 resources.limits.cpu 상향 + readinessProbe 제거
        self._patch_nginx_container(
            namespace,
            resources={
                "requests": {"cpu": "1m"},
                "limits": {"cpu": "1m"},
            },
            readinessProbe={
                "httpGet": {"path": "/", "port": 80},
                "initialDelaySeconds": 2,
                "periodSeconds": 5,
                "timeoutSeconds": 1,
                "failureThreshold": 2,
            },
        )

    def _apply_compound_crash_service(self, _chaos_id: str, namespace: str):
        # [parallel 복합 장애] crash_loop + service_misconfig 동시 주입
        # 두 문제가 완전히 독립적: nginx 고쳐도 webapp-svc는 별도 조사 필요
        # 조사 경로가 갈림: 하나는 Deployment, 다른 하나는 Service/Endpoints
        self._apply_crash_loop(_chaos_id, namespace)
        self._apply_service_misconfig(_chaos_id, namespace)

    # --- 복구 ---

    async def revert(self, chaos_id: str, namespace: str) -> bool:
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None, lambda: self._revert_sync(chaos_id, namespace)
            )
        except Exception:
            return False

    def _revert_sync(self, chaos_id: str, namespace: str) -> bool:
        """chaos_id 와 namespace 만으로 복구한다.

        프로세스 메모리의 주입 이력은 보조 정보로만 쓴다. 서버가 재시작되면
        사라지므로, 그 경우에도 chaos_id 에서 chaos_type 을 복원해 되돌린다.
        """
        info = self._active_chaos.get(chaos_id) or {}
        chaos_type = info.get("type") or self.chaos_type_from_id(chaos_id)
        if not chaos_type:
            logger.warning("cannot resolve chaos type", extra={"chaos_id": chaos_id})
            return False

        handlers = self._CHAOS_HANDLERS.get(chaos_type)
        if handlers is None:
            logger.warning(
                "unknown chaos type on revert",
                extra={"chaos_id": chaos_id, "chaos_type": chaos_type},
            )
            return False

        try:
            _, revert_handler = handlers
            revert_handler(self, chaos_id, namespace)
            self._active_chaos.pop(chaos_id, None)
            logger.info(
                "chaos reverted",
                extra={"chaos_id": chaos_id, "namespace": namespace, "chaos_type": chaos_type},
            )
            return True
        except Exception:
            logger.exception(
                "chaos revert failed",
                extra={"chaos_id": chaos_id, "namespace": namespace},
            )
            return False

    # --- 복구 핸들러 ---

    def _revert_pod_failure(self, _chaos_id: str, namespace: str):
        # 이미지를 정상으로 복구
        self._patch_nginx_container(namespace, image="nginx:latest")

    def _revert_memory_stress(self, chaos_id: str, namespace: str):
        # StressChaos 삭제 + 메모리 limit 복구
        self._custom_api.delete_namespaced_custom_object(
            group=self.CHAOS_GROUP, version=self.CHAOS_VERSION,
            namespace=self.CHAOS_NAMESPACE, plural="stresschaos", name=chaos_id,
        )
        self._patch_nginx_container(
            namespace,
            resources={"requests": {"memory": "64Mi"}, "limits": {"memory": "128Mi"}},
        )

    def _revert_network_latency(self, _chaos_id: str, namespace: str):
        # readiness probe 제거하여 복구하고, 주입 시 바꾼 롤아웃 전략도 기본값으로 되돌린다.
        self._patch_nginx_container(namespace, readinessProbe=None)
        self._set_rollout_strategy(namespace, max_unavailable="25%", max_surge="25%")

    def _revert_service_misconfig(self, _chaos_id: str, namespace: str):
        self._apps_api.delete_namespaced_deployment(name="webapp", namespace=namespace)
        self._core_api.delete_namespaced_service(name="webapp-svc", namespace=namespace)

    def _revert_crash_loop(self, _chaos_id: str, namespace: str):
        self._patch_nginx_container(namespace, command=None)

    def _revert_liveness_probe(self, _chaos_id: str, namespace: str):
        self._patch_nginx_container(namespace, livenessProbe=None)

    def _revert_configmap_misconfig(self, _chaos_id: str, namespace: str):
        cm_name = "nginx-broken-config"
        self._remove_nginx_volume(namespace, cm_name)
        self._delete_ignore_404(self._core_api.delete_namespaced_config_map, name=cm_name, namespace=namespace)

    def _revert_init_container_failure(self, _chaos_id: str, namespace: str):
        # initContainers 제거: strategic merge patch는 배열 삭제가 불안정 → replace 사용
        dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
        dep.spec.template.spec.init_containers = None
        self._apps_api.replace_namespaced_deployment(name="nginx", namespace=namespace, body=dep)

    def _revert_node_selector_mismatch(self, _chaos_id: str, namespace: str):
        # nodeSelector 제거: replace 사용
        dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
        dep.spec.template.spec.node_selector = None
        self._apps_api.replace_namespaced_deployment(name="nginx", namespace=namespace, body=dep)

    def _revert_compound_probe_cascade(self, _chaos_id: str, namespace: str):
        # 이미지 복구 + readinessProbe 제거
        self._patch_nginx_container(namespace, image="nginx:latest", readinessProbe=None)

    def _revert_compound_crash_service(self, _chaos_id: str, namespace: str):
        self._patch_nginx_container(namespace, command=None)
        self._delete_ignore_404(self._apps_api.delete_namespaced_deployment, name="webapp", namespace=namespace)
        self._delete_ignore_404(self._core_api.delete_namespaced_service, name="webapp-svc", namespace=namespace)

    def _revert_wrong_image_registry(self, _chaos_id: str, namespace: str):
        self._patch_nginx_container(namespace, image="nginx:latest")

    def _revert_secret_ref_missing(self, _chaos_id: str, namespace: str):
        dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
        for c in dep.spec.template.spec.containers:
            if c.name == "nginx":
                c.env_from = None
        self._apps_api.replace_namespaced_deployment(name="nginx", namespace=namespace, body=dep)

    def _revert_pvc_unbound(self, _chaos_id: str, namespace: str):
        pvc_name = "nginx-data"
        self._remove_nginx_volume(namespace, pvc_name)
        self._delete_ignore_404(
            self._core_api.delete_namespaced_persistent_volume_claim, name=pvc_name, namespace=namespace
        )

    def _revert_cpu_throttle(self, _chaos_id: str, namespace: str):
        self._patch_nginx_container(
            namespace,
            resources={"requests": {"cpu": "100m", "memory": "64Mi"}, "limits": {"cpu": "500m", "memory": "128Mi"}},
            readinessProbe=None,
        )

    # chaos_type → (주입 핸들러, 복구 핸들러) 레지스트리
    _CHAOS_HANDLERS = {
        "pod_failure": (_apply_pod_chaos, _revert_pod_failure),
        "memory_stress": (_apply_stress_chaos, _revert_memory_stress),
        "network_latency": (_apply_network_chaos, _revert_network_latency),
        "service_misconfig": (_apply_service_misconfig, _revert_service_misconfig),
        "crash_loop": (_apply_crash_loop, _revert_crash_loop),
        "liveness_probe": (_apply_liveness_probe, _revert_liveness_probe),
        "configmap_misconfig": (_apply_configmap_misconfig, _revert_configmap_misconfig),
        "init_container_failure": (_apply_init_container_failure, _revert_init_container_failure),
        "node_selector_mismatch": (_apply_node_selector_mismatch, _revert_node_selector_mismatch),
        "compound_probe_cascade": (_apply_compound_probe_cascade, _revert_compound_probe_cascade),
        "compound_crash_service": (_apply_compound_crash_service, _revert_compound_crash_service),
        "wrong_image_registry": (_apply_wrong_image_registry, _revert_wrong_image_registry),
        "secret_ref_missing": (_apply_secret_ref_missing, _revert_secret_ref_missing),
        "pvc_unbound": (_apply_pvc_unbound, _revert_pvc_unbound),
        "cpu_throttle": (_apply_cpu_throttle, _revert_cpu_throttle),
    }
