"""주입 전에 대상 환경을 준비한다.

화면은 미션을 시작한 뒤에 터미널 세션을 열고, 네임스페이스·nginx·샌드박스는 그 세션을 만들 때 생긴다.
서버는 시작 요청에서 바로 주입하므로, 처음 미션을 하는 계정은 대상이 없어 시작이 실패했다
('장애 주입 실패: deployments.apps "nginx" not found', 실클러스터에서 확인).
"""
import pytest

from app.core import environments
from app.services import k8s_setup
from app.services.chaos_injector import ChaosMeshInjector
from app.services.linux_chaos_injector import PROCESS_FLOOD, LinuxChaosInjector
from tests.test_linux_chaos_injector import _FakeSandboxService

USER = "1d44cf19-2d75-4330-b3df-21a1a12efe9e"
NAMESPACE = f"user-{USER}"


@pytest.mark.asyncio
async def test_linux_inject_ensures_sandbox_first():
    sandboxes = _FakeSandboxService()
    injector = LinuxChaosInjector(sandbox_service=sandboxes)

    result = await injector.inject(PROCESS_FLOOD, NAMESPACE)

    assert result.success
    assert sandboxes.ensured == [(USER, NAMESPACE, environments.LINUX)]


@pytest.mark.asyncio
async def test_kubernetes_inject_sets_up_namespace_before_patching(monkeypatch):
    order = []

    class _Setup:
        async def setup_user_namespace(self, namespace):
            order.append(("setup", namespace))

    monkeypatch.setattr(k8s_setup, "get_k8s_setup_service", lambda: _Setup())

    injector = ChaosMeshInjector.__new__(ChaosMeshInjector)
    injector._active_chaos = {}
    injector._CHAOS_HANDLERS = {
        "pod_failure": (lambda self, chaos_id, ns: order.append(("apply", ns)), lambda *a: None)
    }

    result = await injector.inject("pod_failure", NAMESPACE)

    assert result.success
    assert order == [("setup", NAMESPACE), ("apply", NAMESPACE)]
