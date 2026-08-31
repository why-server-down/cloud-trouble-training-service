import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from evals.run_tutor_eval import DEFAULT_DATASET, load_cases, run


AI_DATA_DIR = Path(__file__).resolve().parents[1]
RUNNER = AI_DATA_DIR / "evals" / "run_tutor_eval.py"


def test_dataset_has_twenty_cases_per_environment_and_all_hint_levels():
    cases = load_cases(DEFAULT_DATASET)
    assert len(cases) >= 60
    assert Counter(case["environment"] for case in cases) == {
        "kubernetes": 20, "docker": 20, "linux": 20,
    }
    for environment in ("kubernetes", "docker", "linux"):
        levels = {case["hint_level"] for case in cases if case["environment"] == environment}
        assert levels == {0, 1, 2, 3}


def test_tutor_quality_gate_passes():
    report = run()
    assert report["success"] is True
    assert report["overall"]["environment_mismatch"] == 0
    assert report["overall"]["hint_leakage_rate_level_0_2"] < 0.05
    assert report["overall"]["dangerous_command_count"] == 0
    assert report["failed_case_ids"] == []
    assert report["application_db_expansion_allowed"] is False


def test_runner_outputs_report_and_zero_exit():
    result = subprocess.run(
        [sys.executable, str(RUNNER)], cwd=AI_DATA_DIR,
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["success"] is True


def test_gate_blocks_environment_mismatch(tmp_path):
    cases = load_cases(DEFAULT_DATASET)
    cases[0]["response"] = "`docker ps`로 확인하세요."
    dataset = tmp_path / "failed.jsonl"
    dataset.write_text("\n".join(json.dumps(case, ensure_ascii=False) for case in cases), encoding="utf-8")
    report = run(dataset)
    assert report["success"] is False
    assert report["overall"]["environment_mismatch"] == 1
    assert report["application_db_expansion_allowed"] is False
