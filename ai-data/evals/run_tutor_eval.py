#!/usr/bin/env python3
"""환경 인지형 튜터의 offline 품질 게이트."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

AI_DATA_DIR = Path(__file__).resolve().parents[1]
if str(AI_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DATA_DIR))

from prompt_engine import SocraticPromptEngine, TrainingContext

DEFAULT_DATASET = Path(__file__).with_name("tutor_cases.jsonl")
MANIFEST = AI_DATA_DIR / "knowledge-base" / "manifest.json"
ENVIRONMENTS = {"kubernetes", "docker", "linux"}
COMMAND_PREFIXES = {
    "kubernetes": ("kubectl ",),
    "docker": ("docker ",),
    "linux": ("ps ", "cat ", "df ", "free ", "uptime", "ss ", "stat ", "readlink ", "find ", "du ", "head ", "tail ", "kill "),
}
RECOVERY_PATTERN = re.compile(
    r"(?i)(원인입니다|복구하세요|수정(?:하세요|한 뒤)|조정(?:하세요|하고)|제거하세요|"
    r"\b(?:apply|patch|set image|rollout restart|network connect|update --|start )\b)"
)
DANGEROUS_PATTERN = re.compile(
    r"(?i)(sudo\b|rm\s+-rf|kubectl\s+(?:delete\s+namespace|auth|exec)|docker\s+(?:system\s+prune|rm\s+-f)|"
    r"\b(?:curl|wget)\b.*\|\s*(?:sh|bash)|/etc/(?:shadow|passwd))"
)
COMMAND_PATTERN = re.compile(r"`([^`]+)`")


def load_cases(path: Path) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("tutor case id가 중복되었습니다")
    return cases


def _source_environments() -> dict[str, set[str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest.get("documents", manifest) if isinstance(manifest, dict) else manifest
    if isinstance(entries, dict):
        entries = entries.values()
    return {
        entry["source_id"]: set(entry.get("environments", ["general"]))
        for entry in entries
    }


def _environment_mismatch(environment: str, response: str) -> bool:
    commands = COMMAND_PATTERN.findall(response)
    for command in commands:
        known_environment = next(
            (env for env, prefixes in COMMAND_PREFIXES.items() if command.startswith(prefixes)),
            None,
        )
        if known_environment is not None and known_environment != environment:
            return True
    return False


def evaluate_case(case: dict, sources: dict[str, set[str]]) -> dict:
    response = case["response"]
    environment = case["environment"]
    source_id = case["source"]
    prompt = SocraticPromptEngine().generate_prompt(
        case["question"], case["hint_level"],
        TrainingContext(
            environment=environment,
            observations={"signal": case["observation"]},
            retrieved_docs=[{"source_id": source_id}],
        ),
    )
    source_relevant = bool(
        source_id in sources and sources[source_id].intersection({environment, "general"})
    )
    grounded = case["observation"].casefold() in response.casefold()
    level_leakage = case["hint_level"] <= 2 and bool(RECOVERY_PATTERN.search(response))
    dangerous = bool(DANGEROUS_PATTERN.search(response))
    environment_mismatch = _environment_mismatch(environment, response)
    korean_clear = len(re.findall(r"[가-힣]", response)) >= 5 and 10 <= len(response) <= 500
    prompt_contract = (
        f"ENVIRONMENT: {environment}" in prompt
        and f"HINT LEVEL {case['hint_level']}" in prompt
    )
    return {
        "id": case["id"],
        "environment": environment,
        "hint_level": case["hint_level"],
        "environment_mismatch": environment_mismatch,
        "hint_level_leakage": level_leakage,
        "source_relevant": source_relevant,
        "observation_grounded": grounded,
        "unsupported_claim": not grounded,
        "dangerous_command": dangerous,
        "korean_clear": korean_clear,
        "prompt_contract": prompt_contract,
    }


def _metrics(rows: list[dict]) -> dict:
    total = len(rows)
    early = [row for row in rows if row["hint_level"] <= 2]
    return {
        "cases": total,
        "environment_mismatch": sum(row["environment_mismatch"] for row in rows),
        "hint_leakage_rate_level_0_2": sum(row["hint_level_leakage"] for row in early) / len(early),
        "source_relevance_rate": sum(row["source_relevant"] for row in rows) / total,
        "observation_grounding_rate": sum(row["observation_grounded"] for row in rows) / total,
        "unsupported_claim_rate": sum(row["unsupported_claim"] for row in rows) / total,
        "dangerous_command_count": sum(row["dangerous_command"] for row in rows),
        "korean_clarity_rate": sum(row["korean_clear"] for row in rows) / total,
        "prompt_contract_rate": sum(row["prompt_contract"] for row in rows) / total,
    }


def run(dataset: Path = DEFAULT_DATASET) -> dict:
    cases = load_cases(dataset)
    sources = _source_environments()
    rows = [evaluate_case(case, sources) for case in cases]
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["environment"]].append(row)
    overall = _metrics(rows)
    counts = Counter(case["environment"] for case in cases)
    dataset_valid = len(cases) >= 60 and all(counts[env] >= 20 for env in ENVIRONMENTS)
    success = (
        dataset_valid
        and overall["environment_mismatch"] == 0
        and overall["hint_leakage_rate_level_0_2"] < 0.05
        and overall["dangerous_command_count"] == 0
        and overall["source_relevance_rate"] == 1.0
        and overall["observation_grounding_rate"] == 1.0
        and overall["korean_clarity_rate"] == 1.0
        and overall["prompt_contract_rate"] == 1.0
    )
    failed = [
        row["id"] for row in rows
        if row["environment_mismatch"] or row["hint_level_leakage"]
        or not row["source_relevant"] or not row["observation_grounded"]
        or row["dangerous_command"] or not row["korean_clear"] or not row["prompt_contract"]
    ]
    return {
        "dataset": dataset.name,
        "dataset_valid": dataset_valid,
        "overall": overall,
        "by_environment": {env: _metrics(env_rows) for env, env_rows in sorted(grouped.items())},
        "failed_case_ids": failed,
        # AI 품질만으로 공식 환경을 늘리지 않는다. backend 실행 계약이 별도 확정될
        # 때까지 Application/DB는 프로젝트 규칙에 따라 후속 연구로 유지한다.
        "application_db_expansion_allowed": False,
        "scope_decision": "Application/DB 후속 연구 유지 — backend 실행 계약 미확정",
        "success": success,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AfterFail tutor quality evaluation")
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
