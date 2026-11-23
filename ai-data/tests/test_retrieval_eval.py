import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from evals.run_retrieval_eval import DEFAULT_DATASET, load_cases, run
from ingest import load_all_documents


AI_DATA_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE = AI_DATA_DIR / "knowledge-base"
REQUIRED_ENVIRONMENTS = {"kubernetes", "docker", "linux"}


def test_retrieval_dataset_has_sixty_balanced_unique_cases():
    cases = load_cases(DEFAULT_DATASET)
    counts = Counter(case["environment"] for case in cases)
    styles = Counter(case["query_style"] for case in cases)

    assert len(cases) >= 60
    assert set(counts) == REQUIRED_ENVIRONMENTS
    assert all(count >= 20 for count in counts.values())
    assert len({case["id"] for case in cases}) == len(cases)
    assert styles["korean"] / len(cases) >= 0.70
    assert styles["english_command"] / len(cases) >= 0.30


def test_expected_sources_exist_and_match_case_environment():
    source_environments = {
        document.metadata["source_id"]: set(document.metadata["environments"])
        for document in load_all_documents(KNOWLEDGE_BASE)
    }

    for case in load_cases(DEFAULT_DATASET):
        assert case["query"]
        assert case["expected_source_ids"]
        for source_id in case["expected_source_ids"]:
            assert source_id in source_environments
            assert source_environments[source_id].intersection(
                {case["environment"], "general"}
            )


def test_retrieval_eval_meets_quality_gate_and_reports_all_metrics():
    report = run(DEFAULT_DATASET)

    assert report["success"] is True
    assert report["retrieval"] == {
        "top_k": 5,
        "candidate_limit": 20,
        "min_similarity": 0,
    }
    assert set(report["by_environment"]) == REQUIRED_ENVIRONMENTS
    for metrics in [report["overall"], *report["by_environment"].values()]:
        assert metrics["recall_at_5"] >= 0.85
        assert metrics["environment_contamination"] < 0.01
        assert metrics["empty_retrieval_rate"] == 0
        assert 0 <= metrics["recall_at_1"] <= metrics["recall_at_3"] <= metrics["recall_at_5"]
        assert 0 <= metrics["mrr"] <= 1
        assert metrics["latency_ms_p50"] <= metrics["latency_ms_p95"]


def test_retrieval_eval_cli_output_is_json(tmp_path):
    output = tmp_path / "report.json"
    runner = AI_DATA_DIR / "evals" / "run_retrieval_eval.py"
    result = subprocess.run(
        [sys.executable, str(runner), "--output", str(output)],
        cwd=AI_DATA_DIR,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["success"] is True
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["success"] is True
