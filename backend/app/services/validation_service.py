from abc import ABC, abstractmethod
from dataclasses import dataclass, field


RETRY_MESSAGE = "틀렸습니다. 다시 시도해 주세요."
SUCCESS_MESSAGE = "미션을 완료했습니다."


@dataclass
class ValidationResult:
    is_resolved: bool
    message: str
    details: dict | None = field(default=None)


class BaseValidationService(ABC):
    @abstractmethod
    async def check_resolution(self, chaos_type: str, namespace: str) -> ValidationResult:
        pass


class MockValidationService(BaseValidationService):
    """Docker 개발 환경용 Mock 구현. debug/resolve 엔드포인트로 수동 해결 트리거."""

    def __init__(self, auto_pass: bool = False):
        self._auto_pass = auto_pass
        self._resolved_namespaces: set[str] = set()

    async def check_resolution(self, chaos_type: str, namespace: str) -> ValidationResult:
        if self._auto_pass or namespace in self._resolved_namespaces:
            return ValidationResult(
                is_resolved=True,
                message=SUCCESS_MESSAGE,
            )
        return ValidationResult(
            is_resolved=False,
            message=RETRY_MESSAGE,
        )

    def mark_resolved(self, namespace: str):
        self._resolved_namespaces.add(namespace)

    def reset(self, namespace: str):
        self._resolved_namespaces.discard(namespace)


class K8sValidationService(BaseValidationService):
    """Kubernetes API를 통해 실제 리소스 상태를 점검하여 장애 해결 여부를 판단"""

    def __init__(self):
        from kubernetes import client, config
        try:
            config.load_incluster_config()
        except Exception:
            try:
                config.load_kube_config()
            except Exception:
                # 로컬에 Kubeconfig가 없는 개발 모드 예외 처리
                pass
        self._client = client
        self._core_api = client.CoreV1Api()
        self._apps_api = client.AppsV1Api()

    @staticmethod
    def _retry() -> ValidationResult:
        return ValidationResult(is_resolved=False, message=RETRY_MESSAGE)

    async def check_resolution(self, chaos_type: str, namespace: str) -> ValidationResult:
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, lambda: self._check_resolution_sync(chaos_type, namespace)
            )
            if not result.is_resolved:
                return self._retry()
            return result
        except Exception as e:
            print(f"[Validation] Failed to check {chaos_type} in {namespace}: {e}")
            return self._retry()

    def _check_resolution_sync(self, chaos_type: str, namespace: str) -> ValidationResult:
        if chaos_type == "pod_failure":
            return self._check_pod_failure(namespace)
        elif chaos_type == "memory_stress":
            return self._check_memory_stress(namespace)
        elif chaos_type == "service_misconfig":
            return self._check_service_misconfig(namespace)
        elif chaos_type == "network_latency":
            return self._check_network_latency(namespace)
        else:
            return self._retry()

    def _check_pod_failure(self, namespace: str) -> ValidationResult:
        try:
            dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
            containers = dep.spec.template.spec.containers
            nginx_container = next((c for c in containers if c.name == "nginx"), None)
            if not nginx_container:
                return self._retry()
            if nginx_container.image == "nginx:wrongtag":
                return self._retry()
        except Exception as e:
            print(f"[Validation] Failed to inspect deployment in {namespace}: {e}")
            return self._retry()

        try:
            pods = self._core_api.list_namespaced_pod(namespace=namespace, label_selector="app=nginx")
            if not pods.items:
                return self._retry()
            
            for pod in pods.items:
                if pod.status.phase != "Running":
                    return self._retry()
                
                ready_condition = next((c for c in pod.status.conditions if c.type == "Ready"), None)
                if not ready_condition or ready_condition.status != "True":
                    return self._retry()
            
            return ValidationResult(is_resolved=True, message=SUCCESS_MESSAGE)
        except Exception as e:
            print(f"[Validation] Failed to inspect pods in {namespace}: {e}")
            return self._retry()

    def _check_memory_stress(self, namespace: str) -> ValidationResult:
        try:
            dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
            containers = dep.spec.template.spec.containers
            nginx_container = next((c for c in containers if c.name == "nginx"), None)
            if not nginx_container:
                return self._retry()
            
            limits = nginx_container.resources.limits or {}
            memory_limit = limits.get("memory", "")
            
            if not memory_limit:
                return self._retry()
            
            import re
            match = re.match(r"(\d+)(Mi|Gi|M|G)?", memory_limit)
            if match:
                value = int(match.group(1))
                unit = match.group(2)
                if (unit == "Mi" or not unit) and value <= 10:
                    return self._retry()
            else:
                return self._retry()
        except Exception as e:
            print(f"[Validation] Failed to inspect deployment in {namespace}: {e}")
            return self._retry()

        try:
            pods = self._core_api.list_namespaced_pod(namespace=namespace, label_selector="app=nginx")
            if not pods.items:
                return self._retry()
            for pod in pods.items:
                if pod.status.phase != "Running":
                    return self._retry()
            return ValidationResult(is_resolved=True, message=SUCCESS_MESSAGE)
        except Exception as e:
            print(f"[Validation] Failed to inspect pods in {namespace}: {e}")
            return self._retry()

    def _check_service_misconfig(self, namespace: str) -> ValidationResult:
        try:
            svc = self._core_api.read_namespaced_service(name="webapp-svc", namespace=namespace)
            selector = svc.spec.selector or {}
            if selector.get("app") != "webapp":
                return self._retry()
            return ValidationResult(is_resolved=True, message=SUCCESS_MESSAGE)
        except Exception as e:
            print(f"[Validation] Failed to inspect service in {namespace}: {e}")
            return self._retry()

    def _check_network_latency(self, namespace: str) -> ValidationResult:
        try:
            dep = self._apps_api.read_namespaced_deployment(name="nginx", namespace=namespace)
            containers = dep.spec.template.spec.containers
            nginx_container = next((c for c in containers if c.name == "nginx"), None)
            if not nginx_container:
                return self._retry()
            
            if not nginx_container.liveness_probe:
                return self._retry()
            
            return ValidationResult(is_resolved=True, message=SUCCESS_MESSAGE)
        except Exception as e:
            print(f"[Validation] Failed to inspect deployment in {namespace}: {e}")
            return self._retry()

