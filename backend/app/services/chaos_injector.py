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
        elif chaos_type == "crash_loop":
            self._apply_crash_loop(chaos_id, namespace)
        elif chaos_type == "liveness_probe":
            self._apply_liveness_probe(chaos_id, namespace)
        elif chaos_type == "configmap_misconfig":
            self._apply_configmap_misconfig(chaos_id, namespace)
        elif chaos_type == "init_container_failure":
            self._apply_init_container_failure(chaos_id, namespace)
        elif chaos_type == "node_selector_mismatch":
            self._apply_node_selector_mismatch(chaos_id, namespace)
        elif chaos_type == "compound_probe_cascade":
            self._apply_compound_probe_cascade(chaos_id, namespace)
        elif chaos_type == "compound_crash_service":
            self._apply_compound_crash_service(chaos_id, namespace)
        elif chaos_type == "wrong_image_registry":
            self._apply_wrong_image_registry(chaos_id, namespace)
        elif chaos_type == "secret_ref_missing":
            self._apply_secret_ref_missing(chaos_id, namespace)
        elif chaos_type == "pvc_unbound":
            self._apply_pvc_unbound(chaos_id, namespace)
        elif chaos_type == "cpu_throttle":
            self._apply_cpu_throttle(chaos_id, namespace)
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
        from kubernetes import client
        from kubernetes.client.rest import ApiException  # type: ignore[attr-defined]

        try:
            self._apps_api.delete_namespaced_deployment(name="webapp", namespace=namespace)
        except ApiException as e:
            if e.status != 404:
                raise
        try:
            self._core_api.delete_namespaced_service(name="webapp-svc", namespace=namespace)
        except ApiException as e:
            if e.status != 404:
                raise

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
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{"name": "nginx", "command": ["sh", "-c", "exit 1"]}]
                        }
                    }
                }
            },
        )

    def _apply_liveness_probe(self, _chaos_id: str, namespace: str):
        # livenessProbe에 존재하지 않는 경로 주입 → probe 실패 → container kill & restart 반복
        # readinessProbe 실패와 차이: liveness는 container를 직접 재시작시킴 (restart count 증가)
        # 사용자 Fix: kubectl patch deployment/nginx -p '{"spec":{"template":{"spec":{"containers":[{"name":"nginx","livenessProbe":null}]}}}}'
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "nginx",
                                "livenessProbe": {
                                    "httpGet": {
                                        "path": "/healthz-notexist",
                                        "port": 80,
                                    },
                                    "initialDelaySeconds": 5,
                                    "periodSeconds": 5,
                                    "failureThreshold": 1,
                                },
                            }]
                        }
                    }
                }
            },
        )

    def _apply_configmap_misconfig(self, _chaos_id: str, namespace: str):
        # nginx.conf 문법 오류가 있는 ConfigMap을 마운트 → nginx config test 실패 → CrashLoopBackOff
        # 사용자 Fix: kubectl edit configmap nginx-broken-config 으로 세미콜론/닫는 괄호 수정
        #            또는 kubectl patch deployment nginx 로 volume/volumeMount 제거 후 rollout restart
        from kubernetes import client
        from kubernetes.client.rest import ApiException  # type: ignore[attr-defined]

        cm_name = "nginx-broken-config"
        try:
            self._core_api.delete_namespaced_config_map(name=cm_name, namespace=namespace)
        except ApiException as e:
            if e.status != 404:
                raise

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
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={
                "spec": {
                    "template": {
                        "spec": {
                            "volumes": [{"name": cm_name, "configMap": {"name": cm_name}}],
                            "containers": [{
                                "name": "nginx",
                                "volumeMounts": [{
                                    "name": cm_name,
                                    "mountPath": "/etc/nginx/nginx.conf",
                                    "subPath": "nginx.conf",
                                }],
                            }],
                        }
                    }
                }
            },
        )

    def _apply_init_container_failure(self, _chaos_id: str, namespace: str):
        # initContainer가 항상 실패 → Pod Init:CrashLoopBackOff 상태
        # readinessProbe/livenessProbe 실패와 달리 메인 컨테이너 자체가 시작되지 않음
        # 사용자 Fix: kubectl patch deployment nginx 로 initContainers 제거
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={
                "spec": {
                    "template": {
                        "spec": {
                            "initContainers": [{
                                "name": "init-check",
                                "image": "busybox:1.35",
                                "command": ["sh", "-c", "echo 'prerequisite check failed'; exit 1"],
                            }]
                        }
                    }
                }
            },
        )

    def _apply_node_selector_mismatch(self, _chaos_id: str, namespace: str):
        # 존재하지 않는 nodeSelector 추가 → 스케줄링 불가 → Pod Pending 상태
        # CrashLoop/Error가 아니라 아예 스케줄링이 안 되는 전혀 다른 증상
        # 사용자 Fix: kubectl patch deployment nginx -p '{"spec":{"template":{"spec":{"nodeSelector":null}}}}'
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={
                "spec": {
                    "template": {
                        "spec": {
                            "nodeSelector": {"disk": "ssd-nonexistent"},
                        }
                    }
                }
            },
        )

    def _apply_compound_probe_cascade(self, _chaos_id: str, namespace: str):
        # [cascade 복합 장애] wrongtag + readinessProbe 동시 주입
        # Phase 1 증상: ImagePullBackOff → 이미지 수정
        # Phase 2 드러남: 이미지 고치고 pod 뜨면 readinessProbe 실패로 여전히 Not Ready
        # 두 번 fix 필요 + 두 번째 문제는 첫 번째 해결 전까지 보이지 않음
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "nginx",
                                "image": "nginx:wrongtag",
                                "readinessProbe": {
                                    "httpGet": {"path": "/healthz-notexist", "port": 80},
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

    def _apply_wrong_image_registry(self, _chaos_id: str, namespace: str):
        # 접근 불가한 private registry 이미지로 패치 → unauthorized ImagePullBackOff
        # image_pull_error(태그 오류)와 다름: Events에 "unauthorized" 메시지
        # 사용자 Fix: kubectl set image deployment/nginx nginx=nginx:latest
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={"spec": {"template": {"spec": {"containers": [
                {"name": "nginx", "image": "private.registry.internal/nginx:latest"}
            ]}}}},
        )

    def _apply_secret_ref_missing(self, _chaos_id: str, namespace: str):
        # 존재하지 않는 Secret을 envFrom으로 참조 → CreateContainerConfigError
        # Pod가 Pending/ContainerCreating에서 멈춤 (이미지 오류와 다른 증상)
        # 사용자 Fix: kubectl create secret generic missing-app-secret --from-literal=key=value
        #            또는 kubectl patch deployment nginx 로 envFrom 제거
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={"spec": {"template": {"spec": {"containers": [
                {"name": "nginx", "envFrom": [{"secretRef": {"name": "missing-app-secret"}}]}
            ]}}}},
        )

    def _apply_pvc_unbound(self, _chaos_id: str, namespace: str):
        # 존재하지 않는 storageClass의 PVC 생성 + 마운트 → Pod Pending (볼륨 바인딩 대기)
        # nodeSelector 실패(스케줄러)와 달리 스토리지 프로비저닝 실패
        # 사용자 Fix: PVC 삭제 후 deployment에서 volume/volumeMount 제거, 또는 올바른 PVC 생성
        from kubernetes import client
        from kubernetes.client.rest import ApiException  # type: ignore[attr-defined]

        pvc_name = "nginx-data"
        try:
            self._core_api.delete_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
        except ApiException as e:
            if e.status != 404:
                raise

        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(name=pvc_name, namespace=namespace),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                storage_class_name="nonexistent-storage",
                resources=client.V1ResourceRequirements(requests={"storage": "1Gi"}),
            ),
        )
        self._core_api.create_namespaced_persistent_volume_claim(namespace=namespace, body=pvc)

        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={"spec": {"template": {"spec": {
                "volumes": [{"name": pvc_name, "persistentVolumeClaim": {"claimName": pvc_name}}],
                "containers": [{"name": "nginx", "volumeMounts": [{"name": pvc_name, "mountPath": "/data"}]}],
            }}}},
        )

    def _apply_cpu_throttle(self, _chaos_id: str, namespace: str):
        # CPU limit을 1m으로 극도로 제한 + 빡빡한 readinessProbe → 0/1 Not Ready
        # OOMKilled와 달리 메모리 문제가 아닌 CPU 리소스 설정 문제
        # 사용자 Fix: kubectl patch deployment nginx 로 resources.limits.cpu 상향 + readinessProbe 제거
        self._apps_api.patch_namespaced_deployment(
            name="nginx",
            namespace=namespace,
            body={"spec": {"template": {"spec": {"containers": [{
                "name": "nginx",
                "resources": {
                    "requests": {"cpu": "1m"},
                    "limits": {"cpu": "1m"},
                },
                "readinessProbe": {
                    "httpGet": {"path": "/", "port": 80},
                    "initialDelaySeconds": 2,
                    "periodSeconds": 5,
                    "timeoutSeconds": 1,
                    "failureThreshold": 2,
                },
            }]}}}},
        )

    def _apply_compound_crash_service(self, chaos_id: str, namespace: str):
        # [parallel 복합 장애] crash_loop + service_misconfig 동시 주입
        # 두 문제가 완전히 독립적: nginx 고쳐도 webapp-svc는 별도 조사 필요
        # 조사 경로가 갈림: 하나는 Deployment, 다른 하나는 Service/Endpoints
        self._apply_crash_loop(chaos_id, namespace)
        self._apply_service_misconfig(chaos_id, namespace)

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
            elif chaos_type == "crash_loop":
                self._apps_api.patch_namespaced_deployment(
                    name="nginx", namespace=namespace,
                    body={"spec": {"template": {"spec": {"containers": [{"name": "nginx", "command": None}]}}}},
                )
            elif chaos_type == "liveness_probe":
                self._apps_api.patch_namespaced_deployment(
                    name="nginx", namespace=namespace,
                    body={"spec": {"template": {"spec": {"containers": [{"name": "nginx", "livenessProbe": None}]}}}},
                )
            elif chaos_type == "configmap_misconfig":
                from kubernetes.client.rest import ApiException as _ApiEx  # type: ignore[attr-defined]
                cm_name = "nginx-broken-config"
                dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
                spec = dep.spec.template.spec
                if spec.volumes:
                    spec.volumes = [v for v in spec.volumes if v.name != cm_name] or None
                for c in spec.containers:
                    if c.name == "nginx" and c.volume_mounts:
                        c.volume_mounts = [vm for vm in c.volume_mounts if vm.name != cm_name] or None
                self._apps_api.replace_namespaced_deployment(name="nginx", namespace=namespace, body=dep)
                try:
                    self._core_api.delete_namespaced_config_map(name=cm_name, namespace=namespace)
                except _ApiEx as e:
                    if e.status != 404:
                        raise
            elif chaos_type == "init_container_failure":
                # initContainers 제거: strategic merge patch는 배열 삭제가 불안정 → replace 사용
                dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
                dep.spec.template.spec.init_containers = None
                self._apps_api.replace_namespaced_deployment(name="nginx", namespace=namespace, body=dep)
            elif chaos_type == "node_selector_mismatch":
                # nodeSelector 제거: replace 사용
                dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
                dep.spec.template.spec.node_selector = None
                self._apps_api.replace_namespaced_deployment(name="nginx", namespace=namespace, body=dep)
            elif chaos_type == "compound_probe_cascade":
                # 이미지 복구 + readinessProbe 제거
                self._apps_api.patch_namespaced_deployment(
                    name="nginx", namespace=namespace,
                    body={"spec": {"template": {"spec": {"containers": [
                        {"name": "nginx", "image": "nginx:latest", "readinessProbe": None}
                    ]}}}},
                )
            elif chaos_type == "compound_crash_service":
                from kubernetes.client.rest import ApiException as _ApiEx  # type: ignore[attr-defined]
                self._apps_api.patch_namespaced_deployment(
                    name="nginx", namespace=namespace,
                    body={"spec": {"template": {"spec": {"containers": [{"name": "nginx", "command": None}]}}}},
                )
                for delete_fn, name in [
                    (self._apps_api.delete_namespaced_deployment, "webapp"),
                    (self._core_api.delete_namespaced_service, "webapp-svc"),
                ]:
                    try:
                        delete_fn(name=name, namespace=namespace)
                    except _ApiEx as e:
                        if e.status != 404:
                            raise
            elif chaos_type == "wrong_image_registry":
                self._apps_api.patch_namespaced_deployment(
                    name="nginx", namespace=namespace,
                    body={"spec": {"template": {"spec": {"containers": [{"name": "nginx", "image": "nginx:latest"}]}}}},
                )
            elif chaos_type == "secret_ref_missing":
                dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
                for c in dep.spec.template.spec.containers:
                    if c.name == "nginx":
                        c.env_from = None
                self._apps_api.replace_namespaced_deployment(name="nginx", namespace=namespace, body=dep)
            elif chaos_type == "pvc_unbound":
                from kubernetes.client.rest import ApiException as _ApiEx  # type: ignore[attr-defined]
                pvc_name = "nginx-data"
                dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
                spec = dep.spec.template.spec
                if spec.volumes:
                    spec.volumes = [v for v in spec.volumes if v.name != pvc_name] or None
                for c in spec.containers:
                    if c.name == "nginx" and c.volume_mounts:
                        c.volume_mounts = [vm for vm in c.volume_mounts if vm.name != pvc_name] or None
                self._apps_api.replace_namespaced_deployment(name="nginx", namespace=namespace, body=dep)
                try:
                    self._core_api.delete_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
                except _ApiEx as e:
                    if e.status != 404:
                        raise
            elif chaos_type == "cpu_throttle":
                self._apps_api.patch_namespaced_deployment(
                    name="nginx", namespace=namespace,
                    body={"spec": {"template": {"spec": {"containers": [{
                        "name": "nginx",
                        "resources": {"requests": {"cpu": "100m", "memory": "64Mi"}, "limits": {"cpu": "500m", "memory": "128Mi"}},
                        "readinessProbe": None,
                    }]}}}},
                )

            del self._active_chaos[chaos_id]
            print(f"[Chaos Mesh] Reverted: {chaos_id}")
            return True
        except Exception as e:
            print(f"[Chaos Mesh] Revert failed: {chaos_id} - {e}")
            return False
