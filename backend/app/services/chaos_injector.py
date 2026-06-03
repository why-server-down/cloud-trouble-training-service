import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChaosResult:
    success: bool
    chaos_id: str
    message: str


class BaseChaosInjector(ABC):
    @abstractmethod
    async def inject(self, chaos_type: str, namespace: str) -> ChaosResult:
        pass

    @abstractmethod
    async def revert(self, chaos_id: str) -> bool:
        pass


class MockChaosInjector(BaseChaosInjector):
    """Docker 개발 환경용 Mock 구현. 실제 장애 주입 없이 시뮬레이션."""

    def __init__(self, delay: float = 0.5):
        self._delay = delay
        self._active_chaos: dict[str, dict] = {}

    async def inject(self, chaos_type: str, namespace: str) -> ChaosResult:
        await asyncio.sleep(self._delay)
        chaos_id = f"mock-{chaos_type}-{uuid.uuid4().hex[:8]}"
        self._active_chaos[chaos_id] = {"type": chaos_type, "namespace": namespace}
        print(f"[MOCK] Chaos injected: {chaos_type} -> {namespace} (id={chaos_id})")
        return ChaosResult(
            success=True,
            chaos_id=chaos_id,
            message=f"[MOCK] {chaos_type} injected into {namespace}",
        )

    async def revert(self, chaos_id: str) -> bool:
        if chaos_id in self._active_chaos:
            del self._active_chaos[chaos_id]
            print(f"[MOCK] Chaos reverted: {chaos_id}")
            return True
        return False


class ChaosMeshInjector(BaseChaosInjector):
    """Chaos Mesh 기반 실제 장애 주입 구현."""

    CHAOS_GROUP = "chaos-mesh.org"
    CHAOS_VERSION = "v1alpha1"
    CHAOS_NAMESPACE = "chaos-testing"

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
        chaos_id = f"{chaos_type.replace('_', '-')}-{uuid.uuid4().hex[:8]}"

        if chaos_type == "pod_failure":
            self._apply_pod_chaos(chaos_id, namespace)
        elif chaos_type == "memory_stress":
            self._apply_stress_chaos(chaos_id, namespace)
        elif chaos_type == "network_latency":
            self._apply_network_chaos(chaos_id, namespace)
        elif chaos_type == "service_misconfig":
            self._apply_service_misconfig(chaos_id, namespace)
        else:
            raise ValueError(f"Unknown chaos_type: {chaos_type}")

        self._active_chaos[chaos_id] = {"type": chaos_type, "namespace": namespace}
        print(f"[Chaos Mesh] Injected: {chaos_type} -> {namespace} (id={chaos_id})")
        return ChaosResult(success=True, chaos_id=chaos_id, message=f"{chaos_type} injected into {namespace}")

    def _apply_pod_chaos(self, _chaos_id: str, namespace: str):
        # nginx 이미지를 존재하지 않는 태그로 패치 → ImagePullBackOff 유발
        # 사용자 Fix: kubectl set image deployment/nginx nginx=nginx:latest -n {namespace}
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{"name": "nginx", "image": "nginx:wrongtag"}]
                        }
                    }
                }
            },
        )

    def _apply_stress_chaos(self, chaos_id: str, namespace: str):
        # nginx 메모리 limit을 10Mi로 낮춘 뒤 StressChaos로 메모리 압박 → OOMKilled 유발
        # 사용자 Fix: kubectl patch deployment/nginx 으로 memory limit 상향 조정
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "nginx",
                                "resources": {
                                    "requests": {"memory": "6Mi"},
                                    "limits": {"memory": "6Mi"},
                                },
                            }]
                        }
                    }
                }
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
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "nginx",
                                "readinessProbe": {
                                    "httpGet": {
                                        "path": "/healthz-notexist",
                                        "port": 80,
                                    },
                                    "initialDelaySeconds": 5,
                                    "periodSeconds": 10,
                                    "failureThreshold": 3,
                                },
                            }]
                        }
                    }
                }
            },
        )

    def _apply_service_misconfig(self, chaos_id: str, namespace: str):
        # webapp Deployment 생성 (label: app=webapp)
        from kubernetes import client
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

    async def revert(self, chaos_id: str) -> bool:
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None, lambda: self._revert_sync(chaos_id)
            )
        except Exception:
            return False

    def _revert_sync(self, chaos_id: str) -> bool:
        info = self._active_chaos.get(chaos_id)
        if not info:
            return False

        chaos_type = info["type"]
        namespace = info["namespace"]

        try:
            if chaos_type == "pod_failure":
                # 이미지를 정상으로 복구
                self._apps_api.patch_namespaced_deployment(
                    name="nginx",
                    namespace=namespace,
                    body={"spec": {"template": {"spec": {"containers": [{"name": "nginx", "image": "nginx:latest"}]}}}},
                )
            elif chaos_type == "memory_stress":
                # StressChaos 삭제 + 메모리 limit 복구
                self._custom_api.delete_namespaced_custom_object(
                    group=self.CHAOS_GROUP, version=self.CHAOS_VERSION,
                    namespace=self.CHAOS_NAMESPACE, plural="stresschaos", name=chaos_id,
                )
                self._apps_api.patch_namespaced_deployment(
                    name="nginx",
                    namespace=namespace,
                    body={"spec": {"template": {"spec": {"containers": [{"name": "nginx", "resources": {"requests": {"memory": "64Mi"}, "limits": {"memory": "128Mi"}}}]}}}},
                )
            elif chaos_type == "network_latency":
                # readiness probe 제거하여 복구
                self._apps_api.patch_namespaced_deployment(
                    name="nginx",
                    namespace=namespace,
                    body={"spec": {"template": {"spec": {"containers": [{"name": "nginx", "readinessProbe": None}]}}}},
                )
            elif chaos_type == "service_misconfig":
                self._apps_api.delete_namespaced_deployment(name="webapp", namespace=namespace)
                self._core_api.delete_namespaced_service(name="webapp-svc", namespace=namespace)

            del self._active_chaos[chaos_id]
            print(f"[Chaos Mesh] Reverted: {chaos_id}")
            return True
        except Exception as e:
            print(f"[Chaos Mesh] Revert failed: {chaos_id} - {e}")
            return False
