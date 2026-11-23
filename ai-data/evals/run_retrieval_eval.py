#!/usr/bin/env python3
"""환경별 hybrid retrieval 품질을 외부 서비스 없이 측정한다."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

AI_DATA_DIR = Path(__file__).resolve().parents[1]
if str(AI_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DATA_DIR))

from config import AISettings
from ingest import attach_chunk_metadata, load_all_documents
from rag_service import RAGService


DEFAULT_DATASET = Path(__file__).with_name("retrieval_cases.jsonl")
KNOWLEDGE_BASE = AI_DATA_DIR / "knowledge-base"


def load_cases(path: Path) -> list[dict]:
    cases = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("retrieval case id가 중복되었습니다")
    return cases


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _metrics(rows: list[dict]) -> dict:
    total = len(rows)
    retrieved = sum(row["retrieved_count"] for row in rows)
    contaminated = sum(row["contaminated_count"] for row in rows)
    latencies = [row["latency_ms"] for row in rows]
    return {
        "cases": total,
        "recall_at_1": sum(row["rank"] == 1 for row in rows) / total,
        "recall_at_3": sum(0 < row["rank"] <= 3 for row in rows) / total,
        "recall_at_5": sum(0 < row["rank"] <= 5 for row in rows) / total,
        "mrr": sum(1 / row["rank"] if row["rank"] else 0 for row in rows) / total,
        "environment_contamination": contaminated / retrieved if retrieved else 0.0,
        "empty_retrieval_rate": sum(row["retrieved_count"] == 0 for row in rows) / total,
        "latency_ms_p50": _percentile(latencies, 0.50),
        "latency_ms_p95": _percentile(latencies, 0.95),
    }


def run(dataset: Path = DEFAULT_DATASET) -> dict:
    cases = load_cases(dataset)
    documents = load_all_documents(KNOWLEDGE_BASE)
    with contextlib.redirect_stdout(io.StringIO()):
        rag = RAGService(
            collection_name="retrieval_eval",
            use_memory=True,
            settings=AISettings(AI_BACKEND="mock", RAG_MIN_SIMILARITY=0, RAG_TOP_K=5),
        )
        chunks = attach_chunk_metadata(rag.chunk_documents(documents))
        rag.ingest_documents(chunks)

    rows = []
    for case in cases:
        started = time.perf_counter()
        results = rag.search_knowledge(
            case["query"],
            environment=case["environment"],
            fault_type=case.get("fault_type"),
            top_k=5,
            min_similarity=0,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        expected = set(case["expected_source_ids"])
        rank = next(
            (
                index
                for index, result in enumerate(results, 1)
                if result.metadata.get("source_id") in expected
            ),
            0,
        )
        contaminated = sum(
            not set(result.metadata.get("environments", []))
            .intersection({case["environment"], "general"})
            for result in results
        )
        rows.append(
            {
                "id": case["id"],
                "environment": case["environment"],
                "rank": rank,
                "retrieved_count": len(results),
                "contaminated_count": contaminated,
                "latency_ms": latency_ms,
            }
        )

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["environment"]].append(row)
    overall = _metrics(rows)
    by_environment = {
        environment: _metrics(environment_rows)
        for environment, environment_rows in sorted(grouped.items())
    }
    success = (
        all(metrics["recall_at_5"] >= 0.85 for metrics in by_environment.values())
        and overall["environment_contamination"] < 0.01
    )
    return {
        "dataset": dataset.name,
        "retrieval": {"top_k": 5, "candidate_limit": 20, "min_similarity": 0},
        "overall": overall,
        "by_environment": by_environment,
        "failed_case_ids": [row["id"] for row in rows if row["rank"] == 0],
        "success": success,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AfterFail retrieval evaluation")
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
