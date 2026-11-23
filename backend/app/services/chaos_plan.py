"""
ChaosPlan - AI 생성 fault를 안전한 실행 계획으로 컴파일.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

# 환경별 허용 fault type.
# AI 가 다른 환경의 장애를 생성하면 그 환경 injector 가 처리할 수 없다.
# 이 표가 AI 에게 전달되는 목록이자 컴파일 단계의 거절 기준이다.
FAULT_TYPES_BY_ENVIRONMENT: dict[str, set[str]] = {
    "docker": {
        "docker_network_disconnect",
        "docker_container_stopped",
        "docker_cpu_throttle",
    },
    "linux": {
        "linux_disk_pressure",
        "linux_cpu_saturation",
        "linux_process_flood",
    },
}


def allowed_fault_types(environment: str) -> set[str]:
    """그 환경에서 생성 가능한 fault type. AI 프롬프트와 컴파일 검증이 함께 쓴다."""
    if environment in FAULT_TYPES_BY_ENVIRONMENT:
        return set(FAULT_TYPES_BY_ENVIRONMENT[environment])
    return set(ALLOWED_FAULT_TYPES)


ALLOWED_FAULT_TYPES = {
    "image_pull_error",
    "crash_loop",
    "oom_killed",
    "service_selector_mismatch",
    "network_latency",
    "probe_failure",
    "configmap_misconfig",
    "liveness_probe_failure",
    "init_container_failure",
    "node_selector_mismatch",
    "compound_probe_cascade",
    "compound_crash_service",
    "wrong_image_registry",
    "secret_ref_missing",
    "pvc_unbound",
    "cpu_throttle",
    # 정적 미션 레거시 타입 (alias)
    "pod_failure",
    "memory_stress",
    "service_misconfig",
}

# AI fault_type → chaos_injector.inject() chaos_type 매핑
FAULT_TYPE_TO_CHAOS_TYPE: dict[str, str] = {
    "image_pull_error":        "pod_failure",           # nginx:wrongtag → ImagePullBackOff
    "pod_failure":             "pod_failure",
    "crash_loop":              "crash_loop",             # exit 1 command → CrashLoopBackOff
    "probe_failure":           "network_latency",        # readinessProbe 실패 → endpoint 제외
    "network_latency":         "network_latency",
    "oom_killed":              "memory_stress",          # memory limit 6Mi → OOMKilled
    "memory_stress":           "memory_stress",
    "service_selector_mismatch": "service_misconfig",
    "service_misconfig":       "service_misconfig",
    "configmap_misconfig":     "configmap_misconfig",    # broken nginx.conf → CrashLoop
    "liveness_probe_failure":  "liveness_probe",         # livenessProbe 실패 → container restart
    "init_container_failure":  "init_container_failure", # initContainer exit1 → Init:CrashLoop
    "node_selector_mismatch":  "node_selector_mismatch", # 불가능한 nodeSelector → Pending
    "compound_probe_cascade":  "compound_probe_cascade", # wrongtag+readiness cascade
    "compound_crash_service":  "compound_crash_service", # crash_loop+service parallel
    "wrong_image_registry":    "wrong_image_registry",   # private registry → unauthorized
    "secret_ref_missing":      "secret_ref_missing",     # envFrom secretRef 없는 Secret
    "pvc_unbound":             "pvc_unbound",            # nonexistent storageClass PVC → Pending
    "cpu_throttle":            "cpu_throttle",           # CPU 1m + 빡빡한 readinessProbe
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

    def compile(
        self, scenario: dict, namespace: str, environment: str = "kubernetes"
    ) -> ChaosPlan:
        fault = scenario.get("fault", {})
        fault_type = fault.get("type", "")

        allowed = allowed_fault_types(environment)
        if fault_type not in allowed:
            # 다른 환경의 장애를 그 환경 injector 가 처리할 수 없다.
            raise ChaosPlanCompileError(
                f"'{environment}' 환경에서 허용되지 않는 fault type: {fault_type}"
            )

        if not RESOURCE_NAME_PATTERN.match(namespace):
            raise ChaosPlanCompileError(f"유효하지 않은 namespace: {namespace}")

        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        plan = ChaosPlan(id=plan_id, namespace=namespace, fault_type=fault_type)
        if environment == "kubernetes":
            self._build_steps(plan, fault, namespace)
        else:
            # docker/linux 장애는 injector 가 고정된 절차로 주입한다.
            # AI 가 임의 step 을 끼워 넣을 여지를 두지 않는다.
            plan.steps.append(
                ChaosStep(
                    kind="sandbox_signal",
                    resource="workload",
                    name=fault_type,
                    namespace=namespace,
                )
            )

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

        if fault_type in ("image_pull_error", "pod_failure"):
            # nginx:wrongtag → ImagePullBackOff
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

        elif fault_type == "crash_loop":
            # exit 1 command → 즉시 종료 → CrashLoopBackOff
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "command": ["sh", "-c", "exit 1"]}]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "command": None}]}}}},
            ))

        elif fault_type in ("oom_killed", "memory_stress"):
            # memory limit 6Mi → OOMKilled
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
            # webapp-svc selector 불일치 → endpoints 0
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

        elif fault_type in ("network_latency", "probe_failure"):
            # readinessProbe 경로 오류 → Pod Not Ready → endpoint 제외
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "readinessProbe": {"httpGet": {"path": "/healthz-notexist", "port": 80}, "initialDelaySeconds": 5, "periodSeconds": 10, "failureThreshold": 3}}]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "readinessProbe": None}]}}}},
            ))

        elif fault_type == "liveness_probe_failure":
            # livenessProbe 경로 오류 → probe 실패 → container 재시작 반복
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "livenessProbe": {"httpGet": {"path": "/healthz-notexist", "port": 80}, "initialDelaySeconds": 5, "periodSeconds": 5, "failureThreshold": 1}}]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "livenessProbe": None}]}}}},
            ))

        elif fault_type == "configmap_misconfig":
            # broken nginx.conf ConfigMap 마운트 → nginx config test 실패 → CrashLoop
            cm_name = "nginx-broken-config"
            plan.steps.append(ChaosStep(
                kind="k8s_create", resource="configmap", name=cm_name, namespace=namespace,
                spec={"data": {"nginx.conf": "<broken nginx config>"}},
            ))
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"volumeMounts": [{"name": cm_name, "mountPath": "/etc/nginx/nginx.conf"}]},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"volumeMounts": []},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_delete", resource="configmap", name=cm_name, namespace=namespace,
            ))

        elif fault_type == "init_container_failure":
            # initContainer exit1 → Init:CrashLoopBackOff (메인 컨테이너 시작 전에 실패)
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"initContainers": [
                    {"name": "init-check", "image": "busybox:1.35", "command": ["sh", "-c", "exit 1"]}
                ]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"initContainers": None}}}},
            ))

        elif fault_type == "node_selector_mismatch":
            # 불가능한 nodeSelector → 스케줄링 실패 → Pending (Running/CrashLoop과 전혀 다른 증상)
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"nodeSelector": {"disk": "ssd-nonexistent"}}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"nodeSelector": None}}}},
            ))

        elif fault_type == "compound_probe_cascade":
            # [cascade] wrongtag + readinessProbe 동시 주입
            # 이미지 고치면 pod 뜨지만 readinessProbe가 숨어있다가 드러남 → 두 번 fix 필요
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [
                    {"name": target_name, "image": "nginx:wrongtag",
                     "readinessProbe": {"httpGet": {"path": "/healthz-notexist", "port": 80},
                                       "initialDelaySeconds": 5, "periodSeconds": 10, "failureThreshold": 3}}
                ]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [
                    {"name": target_name, "image": "nginx:latest", "readinessProbe": None}
                ]}}}},
            ))

        elif fault_type == "wrong_image_registry":
            wrong_image = params.get("wrong_image", "private.registry.internal/nginx:latest")
            original_image = params.get("original_image", "nginx:latest")
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "image": wrong_image}]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{"name": target_name, "image": original_image}]}}}},
            ))

        elif fault_type == "secret_ref_missing":
            secret_name = params.get("secret_name", "missing-app-secret")
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [
                    {"name": target_name, "envFrom": [{"secretRef": {"name": secret_name}}]}
                ]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [
                    {"name": target_name, "envFrom": None}
                ]}}}},
            ))

        elif fault_type == "pvc_unbound":
            pvc_name = "nginx-data"
            plan.steps.append(ChaosStep(
                kind="k8s_create", resource="pvc", name=pvc_name, namespace=namespace,
                spec={"storageClassName": "nonexistent-storage", "accessModes": ["ReadWriteOnce"], "storage": "1Gi"},
            ))
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {
                    "volumes": [{"name": pvc_name, "persistentVolumeClaim": {"claimName": pvc_name}}],
                    "containers": [{"name": target_name, "volumeMounts": [{"name": pvc_name, "mountPath": "/data"}]}],
                }}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"volumes": None, "containers": [{"name": target_name, "volumeMounts": None}]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_delete", resource="pvc", name=pvc_name, namespace=namespace,
            ))

        elif fault_type == "cpu_throttle":
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{
                    "name": target_name,
                    "resources": {"requests": {"cpu": "1m"}, "limits": {"cpu": "1m"}},
                    "readinessProbe": {"httpGet": {"path": "/", "port": 80}, "initialDelaySeconds": 2, "periodSeconds": 5, "timeoutSeconds": 1, "failureThreshold": 2},
                }]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [{
                    "name": target_name,
                    "resources": {"requests": {"cpu": "100m", "memory": "64Mi"}, "limits": {"cpu": "500m", "memory": "128Mi"}},
                    "readinessProbe": None,
                }]}}}},
            ))

        elif fault_type == "compound_crash_service":
            # [parallel] crash_loop + service_misconfig 동시 주입
            # 두 문제가 완전히 독립적 → 각각 별도 조사 + fix 필요
            plan.steps.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [
                    {"name": target_name, "command": ["sh", "-c", "exit 1"]}
                ]}}}},
            ))
            plan.steps.append(ChaosStep(
                kind="k8s_create", resource="service", name="webapp-svc", namespace=namespace,
                spec={"selector": {"app": "webapp-broken"}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_patch", resource="deployment", name=target_name, namespace=namespace,
                patch={"spec": {"template": {"spec": {"containers": [
                    {"name": target_name, "command": None}
                ]}}}},
            ))
            plan.rollback.append(ChaosStep(
                kind="k8s_delete", resource="service", name="webapp-svc", namespace=namespace,
            ))
