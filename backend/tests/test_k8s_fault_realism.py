"""Kubernetes 미션 장애와 검증이 실클러스터에서 맞게 동작한다 (실클러스터 E2E 에서 찾은 결함).

- memory_stress: nginx 는 limit 6Mi 로도 잘 돌아 증상이 Chaos Mesh StressChaos 에 달려 있었고,
  Chaos Mesh 가 없는 클러스터에서는 주입이 실패하며 limit 6Mi 만 남겼다.
- memory_stress·network_latency 검증: Pod phase·엔드포인트만 봐서 CrashLoopBackOff 나 주입 직후
  상태도 통과했다. 롤아웃이 끝나 모든 replica 가 Ready 여야 통과한다.
- service_misconfig 검증: selector 에 키를 더 붙여 Endpoints 가 비어도 통과했다.
- cpu_throttle(AI 모드): httpGet / 검사는 CPU 1m 으로도 바로 통과해 주입 직후 Ready 가 됐다.
"""
from types import SimpleNamespace as NS

from app.services.chaos_injector import (
    CPU_DEMAND_PROBE_COMMAND, MEMORY_DEMAND_COMMAND, ChaosMeshInjector,
)
from app.services.validation_service import K8sValidationService


class _NoCustomObjects:
    def __getattr__(self, name):
        raise AssertionError("Chaos Mesh CR 에 의존하면 안 된다")


def _injector():
    injector = ChaosMeshInjector.__new__(ChaosMeshInjector)
    patches = []
    injector._apps_api = NS(patch_namespaced_deployment=lambda name, namespace, body: patches.append(body))
    injector._custom_api = _NoCustomObjects()
    return injector, patches


def _container(patch):
    return patch["spec"]["template"]["spec"]["containers"][0]


def test_memory_stress_inject_uses_in_container_demand_without_chaos_mesh():
    injector, patches = _injector()
    injector._apply_stress_chaos("memory-stress-1", "user-1")

    container = _container(patches[-1])
    assert container["command"] == MEMORY_DEMAND_COMMAND
    assert container["resources"]["limits"] == {"memory": "6Mi"}


def test_memory_stress_revert_restores_command_and_limit():
    injector, patches = _injector()
    injector._revert_memory_stress("memory-stress-1", "user-1")

    container = _container(patches[-1])
    assert container["command"] is None
    assert container["resources"]["limits"] == {"memory": "128Mi"}


def test_cpu_throttle_probe_spends_cpu_so_the_tiny_limit_shows():
    injector, patches = _injector()
    injector._apply_cpu_throttle("cpu-throttle-1", "user-1")

    container = _container(patches[-1])
    assert container["resources"]["limits"] == {"cpu": "1m"}
    probe = container["readinessProbe"]
    assert probe["exec"]["command"] == CPU_DEMAND_PROBE_COMMAND
    assert "httpGet" not in probe
    assert probe["timeoutSeconds"] == 1


def _deployment(*, limit="128Mi", updated=1, ready=1, available=1, unavailable=None):
    container = NS(name="nginx", image="nginx:1.29", resources=NS(limits={"memory": limit}))
    return NS(
        metadata=NS(generation=3),
        spec=NS(replicas=1, template=NS(spec=NS(containers=[container]))),
        status=NS(
            observed_generation=3, updated_replicas=updated, ready_replicas=ready,
            available_replicas=available, unavailable_replicas=unavailable,
        ),
    )


def _validator(*, deployment=None, endpoints=None, selector=None):
    validator = K8sValidationService.__new__(K8sValidationService)
    validator._apps_api = NS(read_namespaced_deployment=lambda name, namespace: deployment)
    validator._core_api = NS(
        read_namespaced_endpoints=lambda name, namespace: endpoints,
        read_namespaced_service=lambda name, namespace: NS(spec=NS(selector=selector)),
    )
    return validator


def test_memory_stress_needs_finished_rollout_not_just_raised_limit():
    # limit 은 올렸지만 새 Pod 가 아직 반복 종료 중(unavailable 1)이면 통과하지 않는다.
    crashing = _validator(deployment=_deployment(limit="20Mi", ready=0, available=0, unavailable=1))
    assert not crashing._check_memory_stress("user-1").is_resolved

    healthy = _validator(deployment=_deployment(limit="128Mi"))
    assert healthy._check_memory_stress("user-1").is_resolved


def test_network_latency_ignores_endpoints_while_rollout_is_unfinished():
    endpoints = NS(subsets=[NS(addresses=[NS(ip="10.0.0.1")])])
    # 주입 직후: 이전 Pod 가 아직 엔드포인트에 있지만 새 Pod 는 NotReady.
    just_injected = _validator(deployment=_deployment(updated=1, ready=0, available=0, unavailable=1), endpoints=endpoints)
    assert not just_injected._check_network_latency("user-1").is_resolved

    fixed = _validator(deployment=_deployment(), endpoints=endpoints)
    assert fixed._check_network_latency("user-1").is_resolved


def test_service_selector_must_match_exactly():
    assert not _validator(selector={"app": "webapp", "tier": "web"})._check_service_misconfig("user-1").is_resolved
    assert _validator(selector={"app": "webapp"})._check_service_misconfig("user-1").is_resolved
