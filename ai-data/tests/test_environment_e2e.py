import asyncio
import json
import subprocess
import sys
from pathlib import Path

from evals.run_environment_e2e import run

AI_DATA = Path(__file__).resolve().parents[1]
RUNNER = AI_DATA / "evals" / "run_environment_e2e.py"


def test_three_environment_e2e_runs_five_times_each():
    report = asyncio.run(run())
    assert report["success"] is True
    assert report["runs"] == 15
    assert report["by_environment"] == {
        "docker": 5, "kubernetes": 5, "linux": 5,
    }
    assert report["environment_contamination_count"] == 0
    assert all(result["hint_levels"] == [0, 1, 2, 3] for result in report["results"])


def test_e2e_cli_writes_machine_readable_report(tmp_path):
    output = tmp_path / "e2e.json"
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--output", str(output)],
        cwd=AI_DATA, capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["success"] is True
    assert json.loads(output.read_text(encoding="utf-8"))["runs"] == 15
