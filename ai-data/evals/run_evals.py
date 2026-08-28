#!/usr/bin/env python3
"""네트워크 없이 실행하는 AI eval runner.

stdout에는 기계가 읽을 수 있는 JSON summary만 출력하며, 실패 case가 있으면 1을 반환한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_DATASET = Path(__file__).with_name("offline_cases.json")


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.casefold()))


def _evaluate_case(case: dict[str, Any]) -> tuple[bool, Any]:
    kind = case["kind"]
    if kind == "json_parse":
        actual = json.loads(case["input"])
        return actual == case["expected"], actual

    if kind == "keyword_retrieval":
        query_tokens = _tokens(case["query"])
        ranked = sorted(
            case["documents"],
            key=lambda document: (
                len(query_tokens & _tokens(document["text"])),
                document["id"],
            ),
            reverse=True,
        )
        actual = ranked[0]["id"] if ranked else None
        return actual == case["expected_id"], actual

    if kind == "metadata_filter":
        allowed = {case["requested_environment"], "general"}
        actual = [
            document["id"]
            for document in case["documents"]
            if allowed.intersection(document["environments"])
        ]
        return actual == case["expected_ids"], actual

    raise ValueError(f"지원하지 않는 eval kind입니다: {kind}")


def run(dataset: Path) -> dict[str, Any]:
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    results = []
    for case in payload.get("cases", []):
        try:
            passed, actual = _evaluate_case(case)
            results.append(
                {"id": case["id"], "kind": case["kind"], "passed": passed, "actual": actual}
            )
        except Exception as exc:
            results.append(
                {
                    "id": case.get("id", "unknown"),
                    "kind": case.get("kind", "unknown"),
                    "passed": False,
                    "error": type(exc).__name__,
                }
            )

    passed = sum(result["passed"] for result in results)
    total = len(results)
    return {
        "dataset_version": payload.get("version", "unknown"),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "success": passed == total and total > 0,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AfterFail offline AI eval runner")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        summary = run(args.dataset)
    except Exception as exc:
        summary = {
            "total": 0,
            "passed": 0,
            "failed": 1,
            "success": False,
            "error": type(exc).__name__,
        }

    serialized = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
