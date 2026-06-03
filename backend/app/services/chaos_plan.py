"""
ChaosPlan - AI 생성 fault를 안전한 실행 계획으로 컴파일.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

ALLOWED_FAULT_TYPES = {
    "image_pull_error",
    "crash_loop",
    "oom_killed",
    "service_selector_mismatch",
    "network_latency",
    "probe_failure",
    "configmap_misconfig",
    # 정적 미션 레거시 타입 (alias)
    "pod_failure",
    "memory_stress",
    "service_misconfig",
}

# AI fault_type → 기존 chaos_injector.inject() chaos_type 매핑
FAULT_TYPE_TO_CHAOS_TYPE: dict[str, str] = {
    "image_pull_error": "pod_failure",
    "pod_failure": "pod_failure",
    "crash_loop": "pod_failure",
    "probe_failure": "pod_failure",
    "oom_killed": "memory_stress",
    "memory_stress": "memory_stress",
    "service_selector_mismatch": "service_misconfig",
    "service_misconfig": "service_misconfig",
    "network_latency": "network_latency",
    "configmap_misconfig": "pod_failure",
}

RESOURCE_NAME_PATTERN = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")

MAX_LATENCY_MS = 5000
MAX_STRESS_MB = 512
MAX_STEPS = 4


@dataclass
class ChaosStep:
    kind: str        # k8s_patch | chaos_mesh_create | chaos_mesh_delete | k8s_create | k8s_delete
    resource: str    # deployment | service | configmap | networkchaos | stresschaos
    name: str
    namespace: str
    patch: dict | None = None
    spec: dict | None = None


@dataclass
class ChaosPlan:
    id: str
    namespace: str
    fault_type: str
    steps: list[ChaosStep] = field(default_factory=list)
    rollback: list[ChaosStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "fault_type": self.fault_type,
            "steps": [s.__dict__ for s in self.steps],
            "rollback": [s.__dict__ for s in self.rollback],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChaosPlan":
        plan = cls(id=data["id"], namespace=data["namespace"], fault_type=data["fault_type"])
        plan.steps = [ChaosStep(**s) for s in data.get("steps", [])]
        plan.rollback = [ChaosStep(**s) for s in data.get("rollback", [])]
        return plan


class ChaosPlanCompileError(Exception):
    pass


class ChaosPlanCompiler:
    """AI 생성 scenario fault JSON → 검증된 ChaosPlan."""

    def compile(self, scenario: dict, namespace: str) -> ChaosPlan:
        fault = scenario.get("fault", {})
        fault_type = fault.get("type", "")

        if fault_type not in ALLOWED_FAULT_TYPES:
            raise ChaosPlanCompileError(f"허용되지 않는 fault type: {fault_type}")

        if not RESOURCE_NAME_PATTERN.match(namespace):
            raise ChaosPlanCompileError(f"유효하지 않은 namespace: {namespace}")

        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        plan = ChaosPlan(id=plan_id, namespace=namespace, fault_type=fault_type)
        self._build_steps(plan, fault, namespace)

        if len(plan.steps) > MAX_STEPS:
            raise ChaosPlanCompileError(f"최대 {MAX_STEPS}개 step만 허용됩니다")

        return plan

    def _build_steps(self, plan: ChaosPlan, fault: dict, namespace: str):
        fault_type = fault["type"]
        params = fault.get("parameters", {})
        target = fault.get("target", {})
        target_name = target.get("name", "nginx")

        if not RESOURCE_NAME_PATTERN.match(target_name):
            raise ChaosPlanCompileError(f"유효하지 않은 리소스 이름: {target_name}")

        if fault_type in ("image_pull_error", "pod_failure", "crash_loop", "probe_failure", "configmap_misconfig"):
            wrong_image = params.get("wrong_image", "nginx:wrongtag")
            original_image = params.get("original_image", "nginx:latest")
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "image": wrong_image}]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "image": original_image}]}}}},
            ))

        elif fault_type in ("oom_killed", "memory_stress"):
            memory_limit = params.get("memory_limit", "6Mi")
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "resources": {"requests": {"memory": memory_limit}, "limits": {"memory": memory_limit}}}]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "resources": {"requests": {"memory": "64Mi"}, "limits": {"memory": "128Mi"}}}]}}}},
            ))

        elif fault_type in ("service_selector_mismatch", "service_misconfig"):
            svc_name = target.get("name", "webapp-svc")
            if not RESOURCE_NAME_PATTERN.match(svc_name):
                raise ChaosPlanCompileError(f"유효하지 않은 서비스 이름: {svc_name}")
            wrong_selector = params.get("wrong_selector", {"app": f"{svc_name}-broken"})
            original_selector = params.get("expected_selector", {"app": target_name})
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="service", name=svc_name, namespace=namespace,
                patch={"spec": {"selector": wrong_selector}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="service", name=svc_name, namespace=namespace,
                patch={"spec": {"selector": original_selector}},
            ))

        elif fault_type == "network_latency":
            latency_ms = int(params.get("latency_ms", 2000))
            if latency_ms > MAX_LATENCY_MS:
                raise ChaosPlanCompileError(f"latency 상한 초과: {latency_ms}ms > {MAX_LATENCY_MS}ms")
            chaos_name = f"latency-{plan.id[:8]}"
            plan.steps.append(ChaosStep(
                kind="chaos_mesh_create", resource="networkchaos", name=chaos_name, namespace=namespace,
                spec={
                    "action": "delay", "mode": "all",
                    "selector": {"namespaces": [namespace]},
                    "delay": {"latency": f"{latency_ms}ms", "correlation": "25", "jitter": "500ms"},
                    "duration": "30m",
                },
            ))
            plan.rollback.append(ChaosStep(
                kind="chaos_mesh_delete", resource="networkchaos", name=chaos_name, namespace=namespace,
            ))
