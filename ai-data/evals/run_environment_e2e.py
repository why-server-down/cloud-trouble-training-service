#!/usr/bin/env python3
"""세 환경 production component를 연결한 결정적 offline E2E 평가."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

AI_DATA = Path(__file__).resolve().parents[1]
BACKEND = AI_DATA.parent / "backend"
for path in (BACKEND, AI_DATA):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ai_engine import AITutorEngine, TutorRequest
from config import AISettings
from ingest import attach_chunk_metadata, load_all_documents
from prompt_engine import TrainingContext
from rag_service import RAGService
from tests.fakes import DeterministicFakeOpenAI
from app.ai.scenario_agent import MockScenarioAgent, ScenarioGenerationInput, select_candidate
from app.ai.validation_agent import MockValidationAgent
from app.services.chaos_injector import MockChaosInjector
from app.services.chaos_plan import ChaosPlanCompiler, allowed_fault_types

ENVIRONMENTS = ("kubernetes", "docker", "linux")
RUNS_PER_ENVIRONMENT = 5
SCENARIO_CASES = Path(__file__).with_name("scenario_cases.jsonl")
KNOWLEDGE_BASE = AI_DATA / "knowledge-base"


def _cases() -> dict[str, list[dict]]:
    grouped = {environment: [] for environment in ENVIRONMENTS}
    for line in SCENARIO_CASES.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        if len(grouped[case["environment"]]) < RUNS_PER_ENVIRONMENT:
            grouped[case["environment"]].append(case)
    return grouped


def _engine() -> AITutorEngine:
    settings = AISettings(AI_BACKEND="mock", RAG_MIN_SIMILARITY=0, RAG_TOP_K=5)
    with contextlib.redirect_stdout(io.StringIO()):
        rag = RAGService(collection_name="environment_e2e", use_memory=True, settings=settings)
        documents = attach_chunk_metadata(rag.chunk_documents(load_all_documents(KNOWLEDGE_BASE)))
        rag.ingest_documents(documents)
    engine = AITutorEngine(openai_api_key="offline", use_rag=False, settings=settings)
    engine.client = DeterministicFakeOpenAI()
    engine.use_rag = True
    engine.rag_service = rag
    return engine


async def _run_once(environment: str, case: dict, engine: AITutorEngine) -> dict:
    started = time.perf_counter()
    generation_input = ScenarioGenerationInput(
        difficulty=case["difficulty"], namespace="user-e2e",
        recent_fault_types=case.get("recent_fault_types", []),
        allowed_fault_types=sorted(allowed_fault_types(environment)),
        environment=environment, randomize=True, seed=case["seed"], eval_mode=True,
    )
    selected = select_candidate(MockScenarioAgent().generate(generation_input), generation_input)
    scenario = selected.scenario
    plan = ChaosPlanCompiler().compile(scenario, "user-e2e", environment)
    injector = MockChaosInjector(delay=0, environment=environment)
    injected = await injector.inject(plan.fault_type, "user-e2e")

    observations = {"symptoms": scenario["observability"]["symptoms"]}
    context = TrainingContext(
        environment=environment,
        mission={"title": scenario["title"], "fault_type": plan.fault_type},
        observations=observations,
    )
    tutor_results = []
    for level in range(4):
        response = engine.get_response(TutorRequest(
            user_question=f"{plan.fault_type} 상태에서 무엇을 확인할까요?",
            hint_level=level, chaos_type=plan.fault_type,
            environment=environment, training_ctx=context,
        ))
        contaminated = sum(
            source.get("environment") not in (None, environment)
            for source in response.sources
        )
        tutor_results.append({
            "hint_level": level, "sources": len(response.sources),
            "contaminated_sources": contaminated,
            "latency_ms": response.latency_ms,
            "total_tokens": response.token_usage.get("total_tokens", 0),
            "fallback_used": response.fallback_used,
        })

    advisory = await MockValidationAgent().judge(
        {"fault_type": plan.fault_type, "target_name": "training-target"},
        "user-e2e", {"observations": observations}, environment,
    )
    reverted = await injector.revert(injected.chaos_id, "user-e2e")
    return {
        "id": case["id"], "environment": environment,
        "fault_type": plan.fault_type,
        "scenario_compiled": True, "injected": injected.success,
        "runtime_observed": bool(observations["symptoms"]),
        "hint_levels": [item["hint_level"] for item in tutor_results],
        "sources_recorded": any(item["sources"] for item in tutor_results[1:]),
        "environment_contamination": sum(item["contaminated_sources"] for item in tutor_results),
        "tokens_recorded": sum(item["total_tokens"] for item in tutor_results) > 0,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "advisory_only": advisory.advisory_only,
        "mechanical_recovery": reverted,
    }


async def run() -> dict:
    engine = _engine()
    runs = []
    for environment, cases in _cases().items():
        for case in cases:
            runs.append(await _run_once(environment, case, engine))
    counts = Counter(run["environment"] for run in runs)
    success = (
        all(counts[environment] >= RUNS_PER_ENVIRONMENT for environment in ENVIRONMENTS)
        and all(run["scenario_compiled"] and run["injected"] and run["runtime_observed"]
                and run["hint_levels"] == [0, 1, 2, 3] and run["sources_recorded"]
                and run["environment_contamination"] == 0 and run["tokens_recorded"]
                and run["advisory_only"] and run["mechanical_recovery"] for run in runs)
    )
    return {
        "task": "AI-25", "execution_mode": "offline_production_components",
        "live_infrastructure_verified": False,
        "live_blocker": "Docker credential helper가 PostgreSQL/Qdrant image pull에서 응답하지 않음",
        "runs": len(runs), "by_environment": dict(sorted(counts.items())),
        "environment_contamination_count": sum(run["environment_contamination"] for run in runs),
        "success": success, "results": runs,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AfterFail three-environment E2E eval")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = asyncio.run(run())
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
