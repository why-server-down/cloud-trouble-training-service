import copy
import json
import subprocess
import sys
from pathlib import Path

from evals.run_regression_gate import EVAL_DIR, evaluate_reports

AI_DATA_DIR = Path(__file__).resolve().parents[1]
RUNNER = EVAL_DIR / "run_regression_gate.py"


def _reports():
    reports = {
        name: json.loads((EVAL_DIR / f"{name}_report.json").read_text(encoding="utf-8"))
        for name in ("retrieval", "tutor", "scenario")
    }
    reports["retrieval"]["success"] = (
        reports["retrieval"].get("decision", {}).get("result") == "pass"
    )
    reports["contracts"] = {"success": True}
    return reports


def test_baseline_reports_pass_regression_gate():
    report = evaluate_reports(_reports())
    assert report["success"] is True
    assert report["failures"] == []


def test_more_than_three_percentage_point_drop_fails():
    reports = _reports()
    reports["retrieval"]["overall"]["recall_at_5"] -= 0.031
    report = evaluate_reports(reports)
    assert report["success"] is False
    assert "retrieval:recall_at_5:regression" in report["failures"]


def test_any_contamination_or_unsafe_acceptance_fails():
    reports = copy.deepcopy(_reports())
    reports["retrieval"]["overall"]["environment_contamination"] = 0.0001
    reports["scenario"]["overall"]["unsafe_accepted_count"] = 1
    failures = evaluate_reports(reports)["failures"]
    assert "retrieval:environment_contamination" in failures
    assert "scenario:unsafe_acceptance" in failures


def test_regression_runner_is_offline_and_machine_readable():
    result = subprocess.run(
        [sys.executable, str(RUNNER)], cwd=AI_DATA_DIR,
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["success"] is True
