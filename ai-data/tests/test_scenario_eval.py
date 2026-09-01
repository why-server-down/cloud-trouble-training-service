import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from evals.run_scenario_eval import DEFAULT_DATASET, load_cases, run


AI_DATA_DIR = Path(__file__).resolve().parents[1]
RUNNER = AI_DATA_DIR / "evals" / "run_scenario_eval.py"


def test_dataset_has_five_cases_per_environment_and_difficulty():
    cases = load_cases(DEFAULT_DATASET)
    assert len(cases) == 60
    counts = Counter((case["environment"], case["difficulty"]) for case in cases)
    assert set(counts.values()) == {5}


def test_scenario_quality_gate_passes():
    report = run()
    assert report["success"] is True
    assert report["overall"]["schema_validity"] >= 0.99
    assert report["overall"]["environment_match"] == 1.0
    assert report["overall"]["compiler_success"] >= 0.95
    assert report["overall"]["unsafe_accepted_count"] == 0
    assert report["failed_case_ids"] == []


def test_runner_outputs_report_and_zero_exit():
    result = subprocess.run(
        [sys.executable, str(RUNNER)], cwd=AI_DATA_DIR,
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["success"] is True
    assert "generation_latency_ms_mean" in report["overall"]
    assert "generation_tokens_total" in report["overall"]


def test_dataset_gate_rejects_missing_environment_difficulty_case(tmp_path):
    cases = load_cases(DEFAULT_DATASET)[1:]
    dataset = tmp_path / "incomplete.jsonl"
    dataset.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases), encoding="utf-8"
    )
    assert run(dataset)["success"] is False
