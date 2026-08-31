"""AI 시나리오 실행 계약 (BE-20).

가장 중요한 계약: **mechanical validation 이 점수를 승인하는 유일한 기준이다.**
LLM 판정은 advisory 로만 저장되고 mechanical false 를 true 로 뒤집지 못한다.
"""
import inspect

import pytest

from app.core import environments
from app.schemas import TutorResult, ValidationJudgment
from app.services import scenario_service as scenario_module
from app.services.chaos_plan import (
    ChaosPlanCompileError,
    ChaosPlanCompiler,
    allowed_fault_types,
)

NS = "user-abc"


class TestAllowedFaultTypesPerEnvironment:
    """AI 에 전달되는 목록이자 컴파일 단계의 거절 기준이다."""

    def test_each_environment_has_its_own_set(self):
        k8s = allowed_fault_types(environments.KUBERNETES)
        docker = allowed_fault_types(environments.DOCKER)
        linux = allowed_fault_types(environments.LINUX)
        assert not (docker & k8s)
        assert not (linux & k8s)
        assert not (docker & linux)

    def test_docker_types_match_the_injector(self):
        from app.services.docker_chaos_injector import DockerChaosInjector

        supported = DockerChaosInjector.__new__(DockerChaosInjector).supported_chaos_types()
        assert allowed_fault_types(environments.DOCKER) == set(supported)

    def test_linux_types_match_the_injector(self):
        from app.services.linux_chaos_injector import LinuxChaosInjector

        supported = LinuxChaosInjector.__new__(LinuxChaosInjector).supported_chaos_types()
        assert allowed_fault_types(environments.LINUX) == set(supported)


class TestCompilerRejectsForeignFaults:
    """인수 조건: AI 가 허용되지 않은 fault 를 생성하면 reject."""

    def _compile(self, fault_type, environment):
        return ChaosPlanCompiler().compile(
            {"fault": {"type": fault_type, "target": {"name": "nginx"}}},
            NS,
            environment=environment,
        )

    def test_kubernetes_fault_rejected_in_docker(self):
        with pytest.raises(ChaosPlanCompileError) as exc:
            self._compile("image_pull_error", environments.DOCKER)
        assert "docker" in str(exc.value)

    def test_docker_fault_rejected_in_kubernetes(self):
        with pytest.raises(ChaosPlanCompileError):
            self._compile("docker_container_stopped", environments.KUBERNETES)

    def test_linux_fault_rejected_in_docker(self):
        with pytest.raises(ChaosPlanCompileError):
            self._compile("linux_disk_pressure", environments.DOCKER)

    def test_unknown_fault_rejected_everywhere(self):
        for environment in environments.SUPPORTED_ENVIRONMENTS:
            with pytest.raises(ChaosPlanCompileError):
                self._compile("rm_minus_rf", environment)

    def test_matching_fault_compiles(self):
        plan = self._compile("docker_container_stopped", environments.DOCKER)
        assert plan.fault_type == "docker_container_stopped"
        assert plan.steps, "주입기가 실행할 step 이 있어야 한다"

    def test_non_kubernetes_plans_do_not_take_ai_steps(self):
        """docker/linux 는 injector 가 고정 절차로 주입한다.

        AI 가 임의 step 을 끼워 넣을 여지를 두지 않는다.
        """
        plan = self._compile("linux_cpu_saturation", environments.LINUX)
        assert len(plan.steps) == 1
        assert plan.steps[0].name == "linux_cpu_saturation"
        assert plan.steps[0].kind == "sandbox_signal"


class TestMechanicalValidationIsTheOnlyApproval:
    """인수 조건: LLM 오판으로 완료 처리되지 않는다."""

    def test_llm_judgment_never_overwrites_resolved(self):
        """이전 구현은 confidence >= 0.7 이면 resolved 를 LLM 값으로 덮어썼다.

        그러면 사용자가 고치지 않았는데도 완료 처리된다.
        """
        source = inspect.getsource(scenario_module.ScenarioService.check_and_complete)
        assert "resolved = ai_judgment.resolved" not in source

    def test_judgment_is_stored_as_advisory(self):
        source = inspect.getsource(scenario_module.ScenarioService.check_and_complete)
        assert '"advisory_only": True' in source

    def test_validation_judgment_schema_is_advisory_by_default(self):
        judgment = ValidationJudgment(resolved=True, reason="looks fixed", confidence=1.0)
        assert judgment.advisory_only is True


class TestValidationResultRecord:
    """last_validation_result 에 environment / rules / timings 를 남긴다."""

    def test_record_includes_environment_and_timing(self):
        source = inspect.getsource(scenario_module.ScenarioService.check_and_complete)
        for key in ('"environment"', '"duration_ms"', '"rules"', '"checked_at"'):
            assert key in source


class TestEnvironmentMismatchIsRejected:
    def test_start_random_checks_generated_environment(self):
        """미구현 환경 요청을 다른 환경 시나리오로 대체하지 않는다."""
        source = inspect.getsource(scenario_module.ScenarioService.start_random)
        assert "generated_environment" in source
        assert "일치하지 않습니다" in source


class TestAiContracts:
    """AI 담당이 이 형태로 결과를 돌려준다."""

    def test_tutor_result_carries_operational_fields(self):
        result = TutorResult(
            message="힌트",
            environment="linux",
            sources=[{"title": "docs"}],
            observations_used=["processes"],
            token_usage={"total": 120},
            latency_ms=850,
        )
        assert result.environment == "linux"
        assert result.sources[0].title == "docs"
        assert result.token_usage == {"total": 120}

    def test_tutor_source_preserves_safe_retrieval_metadata(self):
        from app.schemas import TutorSource

        source = TutorSource(
            title="Docker Network",
            source_id="docker-network-troubleshooting",
            path="07-docker/network-troubleshooting.md",
            environment="docker",
            similarity=0.91,
        )
        assert source.environment == "docker"
        assert source.similarity == 0.91

    def test_tutor_result_rejects_unknown_environment(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TutorResult(message="x", environment="application")

    def test_tutor_source_does_not_require_external_url(self):
        """외부 링크를 그대로 렌더링하지 않는다. 안전한 경로만 넘긴다."""
        fields = set(TutorSource_fields())
        assert "url" not in fields


def TutorSource_fields():
    from app.schemas import TutorSource

    return TutorSource.model_fields.keys()
