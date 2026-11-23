#!/usr/bin/env python3
"""retrieval/tutor/scenario offline 평가를 기준 보고서와 비교한다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .run_evals import run as run_contracts
    from .run_retrieval_eval import run as run_retrieval
    from .run_scenario_eval import run as run_scenario
    from .run_tutor_eval import run as run_tutor
except ImportError:  # 직접 script 실행
    from run_evals import run as run_contracts
    from run_retrieval_eval import run as run_retrieval
    from run_scenario_eval import run as run_scenario
    from run_tutor_eval import run as run_tutor

EVAL_DIR = Path(__file__).resolve().parent
MAX_REGRESSION = 0.03
HIGHER_IS_BETTER = {
    "retrieval": ("recall_at_5", "mrr"),
    "tutor": (
        "source_relevance_rate", "observation_grounding_rate",
        "korean_clarity_rate", "prompt_contract_rate",
    ),
    "scenario": (
        "schema_validity", "environment_match", "allowed_fault_match",
        "compiler_success", "observation_availability",
        "validation_executability",
    ),
}


def _load_baseline(name: str, baseline_dir: Path) -> dict:
    return json.loads((baseline_dir / f"{name}_report.json").read_text(encoding="utf-8"))


def evaluate_reports(reports: dict[str, dict], baseline_dir: Path = EVAL_DIR) -> dict:
    failures = []
    comparisons = []
    for name, metrics in HIGHER_IS_BETTER.items():
        report = reports[name]
        baseline = _load_baseline(name, baseline_dir)
        if not report.get("success"):
            failures.append(f"{name}:quality_gate")
        for metric in metrics:
            current = float(report["overall"][metric])
            previous = float(baseline["overall"][metric])
            drop = previous - current
            passed = drop <= MAX_REGRESSION + 1e-12
            comparisons.append({
                "suite": name, "metric": metric, "baseline": previous,
                "current": current, "drop": drop, "passed": passed,
            })
            if not passed:
                failures.append(f"{name}:{metric}:regression")

    if reports["retrieval"]["overall"]["environment_contamination"] > 0:
        failures.append("retrieval:environment_contamination")
    if reports["scenario"]["overall"]["unsafe_accepted_count"] > 0:
        failures.append("scenario:unsafe_acceptance")
    if not reports["contracts"].get("success"):
        failures.append("contracts:offline")
    return {
        "success": not failures,
        "max_regression_percentage_points": MAX_REGRESSION * 100,
        "failures": failures,
        "comparisons": comparisons,
        "suites": {
            name: {"success": report.get("success", False)}
            for name, report in reports.items()
        },
    }


def run(baseline_dir: Path = EVAL_DIR) -> dict:
    reports = {
        "contracts": run_contracts(EVAL_DIR / "offline_cases.json"),
        "retrieval": run_retrieval(),
        "tutor": run_tutor(),
        "scenario": run_scenario(),
    }
    return evaluate_reports(reports, baseline_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AfterFail AI offline regression gate")
    parser.add_argument("--baseline-dir", type=Path, default=EVAL_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run(args.baseline_dir)
    except Exception as exc:
        report = {"success": False, "failures": [f"runner:{type(exc).__name__}"]}
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
