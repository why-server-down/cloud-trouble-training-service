#!/usr/bin/env python3
"""멀티 환경 시나리오 생성기의 offline 품질 게이트."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

AI_DATA_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = AI_DATA_DIR.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ai.scenario_agent import (  # noqa: E402
    MockScenarioAgent,
    OpenAIScenarioAgent,
    ScenarioGenerationInput,
    select_candidate,
)
from app.services.chaos_plan import ChaosPlanCompiler, allowed_fault_types  # noqa: E402

DEFAULT_DATASET = Path(__file__).with_name("scenario_cases.jsonl")
ENVIRONMENTS = {"kubernetes", "docker", "linux"}
DIFFICULTIES = {"beginner", "intermediate", "advanced", "expert"}
VALIDATION_TYPES = {"kubernetes": {"k8s"}, "docker": {"mock"}, "linux": {"mock"}}


def load_cases(path: Path) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("scenario case id가 중복되었습니다")
    return cases


def evaluate_case(case: dict, agent=None) -> dict:
    agent = agent or MockScenarioAgent()
    environment = case["environment"]
    allowed = sorted(allowed_fault_types(environment))
    gen_input = ScenarioGenerationInput(
        difficulty=case["difficulty"],
        namespace="eval-user",
        recent_fault_types=case.get("recent_fault_types", []),
        allowed_fault_types=allowed,
        environment=environment,
        randomize=True,
        seed=case["seed"],
        eval_mode=True,
    )
    started = time.perf_counter()
    generated = agent.generate(gen_input)
    latency_ms = (time.perf_counter() - started) * 1000
    selected = select_candidate(generated, gen_input)
    parsed = OpenAIScenarioAgent("offline-eval")._parse_response(
        json.dumps({"scenarios": [selected.scenario]}, ensure_ascii=False), gen_input
    )[0]
    scenario = parsed.scenario
    schema_valid = not parsed.rejected
    compiler_success = False
    if schema_valid:
        try:
            ChaosPlanCompiler().compile(scenario, "eval-user", environment)
            compiler_success = True
        except Exception:
            pass
    rules = scenario.get("validation", {}).get("rules", [])
    validation_executable = bool(rules) and all(
        rule.get("type") in VALIDATION_TYPES[environment]
        and bool(rule.get("query"))
        and isinstance(rule.get("stability_seconds"), int)
        for rule in rules
    )
    answer_leakage = bool(
        parsed.rejected and parsed.rejection_reason
        and parsed.rejection_reason.startswith("answer_leakage")
    )
    unsafe_accepted = bool(
        not parsed.rejected
        and selected.score_breakdown
        and selected.score_breakdown.get("unsafe_parameter") == -30
    )
    return {
        "id": case["id"],
        "environment": environment,
        "difficulty": case["difficulty"],
        "schema_valid": schema_valid,
        "environment_match": scenario.get("environment") == environment,
        "allowed_fault_match": scenario.get("fault", {}).get("type") in allowed,
        "compiler_success": compiler_success,
        "observation_available": bool(scenario.get("observability", {}).get("symptoms")),
        "validation_executable": validation_executable,
        "answer_leakage": answer_leakage,
        "unsafe_accepted": unsafe_accepted,
        "generation_latency_ms": latency_ms,
        "generation_tokens": int(scenario.get("token_usage", {}).get("total_tokens", 0)),
    }


def _metrics(rows: list[dict]) -> dict:
    total = len(rows)
    latencies = [row["generation_latency_ms"] for row in rows]
    return {
        "cases": total,
        "schema_validity": sum(row["schema_valid"] for row in rows) / total,
        "environment_match": sum(row["environment_match"] for row in rows) / total,
        "allowed_fault_match": sum(row["allowed_fault_match"] for row in rows) / total,
        "compiler_success": sum(row["compiler_success"] for row in rows) / total,
        "observation_availability": sum(row["observation_available"] for row in rows) / total,
        "validation_executability": sum(row["validation_executable"] for row in rows) / total,
        "answer_leakage_count": sum(row["answer_leakage"] for row in rows),
        "unsafe_accepted_count": sum(row["unsafe_accepted"] for row in rows),
        "generation_latency_ms_mean": statistics.fmean(latencies),
        "generation_latency_ms_max": max(latencies),
        "generation_tokens_total": sum(row["generation_tokens"] for row in rows),
    }


def run(dataset: Path = DEFAULT_DATASET, agent=None) -> dict:
    cases = load_cases(dataset)
    rows = [evaluate_case(case, agent=agent) for case in cases]
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["environment"]].append(row)
    combinations = Counter((case["environment"], case["difficulty"]) for case in cases)
    dataset_valid = (
        len(cases) >= 60
        and all(combinations[(env, difficulty)] >= 5 for env in ENVIRONMENTS for difficulty in DIFFICULTIES)
    )
    overall = _metrics(rows)
    success = (
        dataset_valid
        and overall["schema_validity"] >= 0.99
        and overall["environment_match"] == 1.0
        and overall["allowed_fault_match"] == 1.0
        and overall["compiler_success"] >= 0.95
        and overall["observation_availability"] == 1.0
        and overall["validation_executability"] == 1.0
        and overall["answer_leakage_count"] == 0
        and overall["unsafe_accepted_count"] == 0
    )
    failed = [
        row["id"] for row in rows
        if not all((row["schema_valid"], row["environment_match"], row["allowed_fault_match"],
                    row["compiler_success"], row["observation_available"], row["validation_executable"]))
        or row["answer_leakage"] or row["unsafe_accepted"]
    ]
    return {
        "dataset": dataset.name,
        "dataset_valid": dataset_valid,
        "overall": overall,
        "by_environment": {env: _metrics(env_rows) for env, env_rows in sorted(grouped.items())},
        "failed_case_ids": failed,
        "success": success,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AfterFail scenario quality evaluation")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run(args.dataset)
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
