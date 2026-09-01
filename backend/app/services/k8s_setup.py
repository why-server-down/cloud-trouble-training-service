import logging
import asyncio

logger = logging.getLogger(__name__)

from kubernetes import client, config
from kubernetes.client.rest import ApiException


class K8sSetupService:
    """사용자 전용 K8s 네임스페이스 및 기본 Pod 관리."""

    def __init__(self):
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()

        self._core_api = client.CoreV1Api()
        self._apps_api = client.AppsV1Api()

    async def setup_user_namespace(self, namespace: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._setup_sync(namespace))

    def _setup_sync(self, namespace: str) -> None:
        self._ensure_namespace(namespace)
        self._ensure_nginx_deployment(namespace)
        self._ensure_nginx_service(namespace)

    def _ensure_namespace(self, namespace: str) -> None:
        try:
            self._core_api.read_namespace(name=namespace)
        except ApiException as e:
            if e.status == 404:
                self._core_api.create_namespace(
                    body=client.V1Namespace(
                        metadata=client.V1ObjectMeta(name=namespace)
                    )
                )
                logger.info(f"[K8s] 네임스페이스 생성: {namespace}")
            else:
                raise

    def _ensure_nginx_deployment(self, namespace: str) -> None:
        try:
            self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
            logger.info(f"[K8s] nginx 이미 존재: {namespace}")
        except ApiException as e:
            if e.status == 404:
                deployment = client.V1Deployment(
                    metadata=client.V1ObjectMeta(name="nginx", namespace=namespace),
                    spec=client.V1DeploymentSpec(
                        replicas=1,
                        selector=client.V1LabelSelector(
                            match_labels={"app": "nginx"}
                        ),
                        template=client.V1PodTemplateSpec(
                            metadata=client.V1ObjectMeta(labels={"app": "nginx"}),
                            spec=client.V1PodSpec(
                                containers=[
                                    client.V1Container(
                                        name="nginx",
                                        image="nginx:latest",
                                        ports=[client.V1ContainerPort(container_port=80)],
                                        resources=client.V1ResourceRequirements(
                                            requests={"memory": "64Mi", "cpu": "50m"},
                                            limits={"memory": "128Mi", "cpu": "100m"},
                                        ),
                                    )
                                ]
                            ),
                        ),
                    ),
                )
                self._apps_api.create_namespaced_deployment(
                    namespace=namespace, body=deployment
                )
                logger.info(f"[K8s] nginx 배포 완료: {namespace}")
            else:
                raise

    def _ensure_nginx_service(self, namespace: str) -> None:
        try:
            self._core_api.read_namespaced_service(name="nginx-svc", namespace=namespace)
            logger.info(f"[K8s] nginx-svc 이미 존재: {namespace}")
        except ApiException as e:
            if e.status == 404:
                service = client.V1Service(
                    metadata=client.V1ObjectMeta(name="nginx-svc", namespace=namespace),
                    spec=client.V1ServiceSpec(
                        selector={"app": "nginx"},
                        ports=[client.V1ServicePort(port=80, target_port=80)],
                    ),
                )
                self._core_api.create_namespaced_service(namespace=namespace, body=service)
                logger.info(f"[K8s] nginx-svc 생성 완료: {namespace}")
            else:
                raise

    async def teardown_user_namespace(self, namespace: str) -> None:
        """사용자 계정 전체 정리에만 사용한다.

        개별 터미널 세션 종료는 SandboxService.cleanup()으로 처리한다.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._teardown_sync(namespace))

    def _teardown_sync(self, namespace: str) -> None:
        try:
            self._core_api.delete_namespace(name=namespace)
            logger.info(f"[K8s] 네임스페이스 삭제: {namespace}")
        except ApiException as e:
            if e.status != 404:
                raise


_k8s_setup_service: K8sSetupService | None = None


def get_k8s_setup_service() -> K8sSetupService:
    global _k8s_setup_service
    if _k8s_setup_service is None:
        _k8s_setup_service = K8sSetupService()
    return _k8s_setup_service
