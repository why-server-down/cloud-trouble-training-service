import inspect

from app.services import scenario_service


def test_scenario_service_passes_request_environment_to_generation_input():
    source = inspect.getsource(scenario_service.ScenarioService.start_random)
    assert "environment=environment" in source
    assert "allowed_fault_types(environment)" in source


def test_scenario_service_uses_safe_candidate_selector_and_randomize_contract():
    source = inspect.getsource(scenario_service.ScenarioService.start_random)
    assert "randomize=randomize" in source
    assert "select_candidate(valid, gen_input)" in source
    assert "max(valid" not in source


def test_recent_fault_history_is_filtered_by_environment():
    source = inspect.getsource(scenario_service.ScenarioService._get_recent_fault_types)
    assert "GeneratedScenario.environment == environment" in source


def test_sandbox_fault_type_is_not_replaced_with_kubernetes_default():
    source = inspect.getsource(scenario_service.ScenarioService.start_random)
    assert "FAULT_TYPE_TO_CHAOS_TYPE.get(plan.fault_type, plan.fault_type)" in source
