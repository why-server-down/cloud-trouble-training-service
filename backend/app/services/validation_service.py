from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import asyncio
import re

import httpx


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


class MissionValidationQueries:
    NGINX_ROLLOUT_HEALTHY = """
        kube_deployment_status_replicas_updated{{namespace="{namespace}",deployment="nginx"}}
          == kube_deployment_spec_replicas{{namespace="{namespace}",deployment="nginx"}}
        and kube_deployment_status_replicas_available{{namespace="{namespace}",deployment="nginx"}}
          == kube_deployment_spec_replicas{{namespace="{namespace}",deployment="nginx"}}
        and kube_deployment_status_replicas_unavailable{{namespace="{namespace}",deployment="nginx"}} == 0
    """

    QUERIES = {
        "pod_failure": NGINX_ROLLOUT_HEALTHY,
        "memory_stress": f"""
            {NGINX_ROLLOUT_HEALTHY}
            and on() (min(kube_pod_container_resource_limits{{
                namespace="{{namespace}}",container="nginx",resource="memory"
            }}) > 10 * 1024 * 1024)
        """,
        "service_misconfig": """
            sum(kube_endpoint_address{
                namespace="{namespace}",endpoint="webapp-svc",ready="true"
            }) > 0
        """,
        "network_latency": """
            sum(increase(prober_probe_total{
                namespace="{namespace}",probe_type="Liveness",result="successful"
            }[1m])) > 0
        """,
    }

    @classmethod
    def get_query(cls, chaos_type: str, namespace: str) -> str:
        template = cls.QUERIES.get(chaos_type)
        if not template:
            raise ValueError(f"Unknown chaos_type: {chaos_type}")
        if not re.fullmatch(r"[a-z0-9-]+", namespace):
            raise ValueError("Invalid namespace")
        query = template.replace("{namespace}", namespace)
        return " ".join(query.replace("{{", "{").replace("}}", "}").split())


class PrometheusClient:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def query(self, query: str) -> dict:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{self._base_url}/api/v1/query",
                params={"query": query},
            )
            response.raise_for_status()
            return response.json()


class PrometheusValidationService(BaseValidationService):
    def __init__(self, base_url: str):
        self._prometheus = PrometheusClient(base_url)

    async def check_resolution(self, chaos_type: str, namespace: str) -> ValidationResult:
        try:
            query = MissionValidationQueries.get_query(chaos_type, namespace)
            result = await self._prometheus.query(query)
            if self._is_resolved(result):
                return ValidationResult(is_resolved=True, message=SUCCESS_MESSAGE)
        except Exception as e:
            print(f"[Validation] Prometheus query failed for {chaos_type} in {namespace}: {e}")
        return ValidationResult(is_resolved=False, message=RETRY_MESSAGE)

    @staticmethod
    def _is_resolved(result: dict) -> bool:
        if result.get("status") != "success":
            return False
        values = result.get("data", {}).get("result", [])
        return bool(values) and all(float(item["value"][1]) > 0 for item in values)


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
        # nginx-svc에 ready 엔드포인트가 존재하면 readiness probe가 정상화된 것
        try:
            ep = self._core_api.read_namespaced_endpoints(name="nginx-svc", namespace=namespace)
            for subset in (ep.subsets or []):
                if subset.addresses:
                    return ValidationResult(is_resolved=True, message=SUCCESS_MESSAGE)
            return self._retry()
        except Exception as e:
            print(f"[Validation] Failed to inspect endpoints in {namespace}: {e}")
            return self._retry()

