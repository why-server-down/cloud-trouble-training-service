import json
import subprocess
import sys
from pathlib import Path

from evals.run_evals import DEFAULT_DATASET, run


AI_DATA_DIR = Path(__file__).resolve().parents[1]
RUNNER = AI_DATA_DIR / "evals" / "run_evals.py"


def test_offline_eval_dataset_passes():
    summary = run(DEFAULT_DATASET)

    assert summary["success"] is True
    assert summary["failed"] == 0
    assert summary["total"] == 3


def test_runner_prints_json_and_returns_zero_without_network():
    result = subprocess.run(
        [sys.executable, str(RUNNER)],
        cwd=AI_DATA_DIR,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0
    summary = json.loads(result.stdout)
    assert summary["success"] is True
    assert summary["passed"] == summary["total"]


def test_runner_returns_nonzero_and_json_for_failed_case(tmp_path):
    dataset = tmp_path / "failed.json"
    dataset.write_text(
        json.dumps(
            {
                "version": "test",
                "cases": [
                    {
                        "id": "intentional-failure",
                        "kind": "json_parse",
                        "input": "{}",
                        "expected": {"environment": "kubernetes"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(RUNNER), "--dataset", str(dataset)],
        cwd=AI_DATA_DIR,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["failed"] == 1
