"""
AI 튜터 서비스 - ai-data 모듈을 FastAPI 백엔드와 연결하는 어댑터
"""

import sys
import os
import asyncio
import logging
import time
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ai.observability import (
    record_ai_call, record_ai_stage, record_retrieval, record_tutor_result,
)

logger = logging.getLogger(__name__)

# ai-data 경로를 Python path에 추가
_AI_DATA_PATH_CANDIDATES = (
    os.getenv("AI_DATA_DIR"),
    os.path.abspath("/app/ai-data"),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../ai-data")),
)
_AI_DATA_PATH = next(
    (path for path in _AI_DATA_PATH_CANDIDATES if path and os.path.exists(path)),
    _AI_DATA_PATH_CANDIDATES[-1],
)
if _AI_DATA_PATH not in sys.path:
    sys.path.insert(0, _AI_DATA_PATH)


class TutorService:
    """
    AI 튜터 서비스
    - openai/gemini 모드: ai-data의 AITutorEngine 사용 (RAG + LLM)
    - mock 모드: 간단한 고정 응답 (OpenAI 키 없을 때)
    """

    def __init__(self):
        self._engine = None
        self._initialized = False

    def _init_engine(self):
        if self._initialized:
            return
        self._initialized = True

        if settings.AI_BACKEND not in ("openai", "gemini"):
            return

        if settings.AI_BACKEND == "gemini":
            if not settings.GEMINI_API_KEY:
                return
        else:
            if not settings.OPENAI_API_KEY:
                return

        try:
            from ai_engine import AITutorEngine
            from config import AISettings

            ai_settings = AISettings.from_backend_settings(settings)
            self._engine = AITutorEngine(
                use_rag=True,
                settings=ai_settings,
            )
        except Exception:
            logger.exception("AI tutor engine initialization failed; using mock fallback")
            self._engine = None

    async def get_hint(
        self,
        user_question: str,
        attempt_id: uuid.UUID,
        hint_level: int,
        mission_name: str,
        mission_level: int,
        chaos_type: str,
        namespace: str,
        db: AsyncSession | None = None,
        scenario_id: uuid.UUID | None = None,
    ):
        from app.schemas import TutorResult

        total_started = time.perf_counter()
        self._init_engine()

        # 같은 attempt의 최근 user/assistant 대화쌍 로드 (세션 간 연속성)
        conversation_history = await self._load_conversation(attempt_id, db)

        # DB attempt가 결정한 환경과 sandbox 범위에서 RuntimeContext 수집
        runtime_ctx: dict | None = None
        runtime_factory = None
        attempt_environment = "kubernetes"
        if db is not None:
            try:
                from app.services.runtime_context import (
                    get_runtime_context_collector,
                    format_k8s_state,
                    format_recent_commands,
                    format_events,
                )
                from app.models import MissionAttempt
                result = await db.execute(
                    select(MissionAttempt).where(MissionAttempt.id == attempt_id)
                )
                attempt = result.scalar_one_or_none()
                user_id = attempt.user_id if attempt else None
                attempt_environment = (
                    attempt.environment if attempt and attempt.environment else "kubernetes"
                )

                if user_id:
                    from app.services.sandbox_service import get_sandbox_service

                    sandbox = get_sandbox_service().reference_for(
                        user_id=user_id,
                        namespace=namespace,
                        environment=attempt_environment,
                    )
                    collector = get_runtime_context_collector()
                    runtime_factory = lambda: collector.collect(
                        user_id=user_id, namespace=namespace, db=db,
                        scenario_title=mission_name, difficulty=str(mission_level),
                        scenario_id=scenario_id, environment=attempt_environment,
                        sandbox=sandbox,
                    )
            except Exception:
                logger.exception("AI tutor runtime context collection failed")

        if self._engine is None:
            response = TutorResult(
                message=self._mock_response(user_question, hint_level, chaos_type),
                hint_level=hint_level,
                environment=attempt_environment,
                fallback_used=True,
                error_code="mock_backend",
            )
        else:
            retrieval_request = self._retrieval_request(
                user_question, hint_level, chaos_type, attempt_environment
            )
            runtime_result, retrieval_result = await asyncio.gather(
                self._collect_runtime_with_timeout(
                    runtime_factory, attempt_environment, hint_level
                ),
                self._retrieve_with_timeout(
                    retrieval_request, attempt_environment, hint_level
                ),
            )
            runtime_ctx, context_ms, context_error = runtime_result
            retrieval, retrieval_ms, retrieval_error = retrieval_result
            response = await self._call_engine(
                user_question=user_question,
                hint_level=hint_level,
                mission_name=mission_name,
                mission_level=mission_level,
                chaos_type=chaos_type,
                namespace=namespace,
                conversation_history=conversation_history,
                attempt_id=str(attempt_id),
                runtime_ctx=runtime_ctx,
                fault_type=chaos_type,
                environment=attempt_environment,
                retrieval_result=retrieval,
            )
            breakdown = dict(response.latency_breakdown or {})
            breakdown.update({
                "context_ms": context_ms,
                "retrieval_ms": retrieval_ms,
                "total_ms": (time.perf_counter() - total_started) * 1000,
            })
            response.latency_breakdown = breakdown
            response.latency_ms = round(breakdown["total_ms"])
            pipeline_error = retrieval_error or context_error
            if pipeline_error and not response.error_code:
                response.error_code = pipeline_error
                response.fallback_used = True
            record_ai_stage(
                provider=settings.AI_BACKEND, model=self._engine.model,
                environment=attempt_environment, hint_level=hint_level,
                stage="total", result="fallback" if response.fallback_used else "success",
                duration_ms=breakdown["total_ms"],
            )

        record_tutor_result(
            provider=settings.AI_BACKEND, environment=attempt_environment,
            result="fallback" if response.fallback_used else "success",
        )

        # TutorMessage DB 저장
        if db is not None:
            await self._save_messages(db, attempt_id, user_question, response.message, hint_level)

        return response

    def _retrieval_request(self, question, hint_level, fault_type, environment):
        from ai_engine import TutorRequest
        return TutorRequest(
            user_question=question, hint_level=hint_level,
            chaos_type=fault_type, environment=environment,
        )

    async def _collect_runtime_with_timeout(self, factory, environment, hint_level):
        if factory is None:
            return None, 0.0, "runtime_unavailable"
        started = time.perf_counter()
        result = "success"
        error = None
        try:
            context = await asyncio.wait_for(
                factory(), timeout=settings.CONTEXT_COLLECTION_TIMEOUT
            )
        except asyncio.TimeoutError:
            context, result, error = None, "timeout", "runtime_timeout"
        except Exception:
            context, result, error = None, "error", "runtime_failed"
            logger.exception("AI tutor runtime context collection failed")
        elapsed = (time.perf_counter() - started) * 1000
        record_ai_stage(
            provider=settings.AI_BACKEND, model=self._engine.model,
            environment=environment, hint_level=hint_level,
            stage="context", result=result, duration_ms=elapsed,
        )
        return context, elapsed, error

    async def _retrieve_with_timeout(self, request, environment, hint_level):
        started = time.perf_counter()
        result = "success"
        error = None
        try:
            retrieval = await asyncio.wait_for(
                asyncio.to_thread(self._engine.retrieve, request),
                timeout=settings.RAG_SEARCH_TIMEOUT,
            )
            if retrieval.error_code:
                result, error = "fallback", retrieval.error_code
        except asyncio.TimeoutError:
            from ai_engine import RetrievalResult
            retrieval = RetrievalResult([], [], 0.0, error_code="retrieval_timeout")
            result, error = "timeout", "retrieval_timeout"
        except Exception:
            from ai_engine import RetrievalResult
            retrieval = RetrievalResult([], [], 0.0, error_code="retrieval_failed")
            result, error = "error", "retrieval_failed"
            logger.exception("AI tutor retrieval failed")
        elapsed = (time.perf_counter() - started) * 1000
        contamination = sum(
            source.get("environment") not in (None, environment)
            for source in retrieval.sources
        )
        retrieval_result = (
            result if result != "success"
            else "empty" if not retrieval.sources
            else "success"
        )
        record_retrieval(
            provider=settings.AI_BACKEND, environment=environment,
            result=retrieval_result, result_count=len(retrieval.sources),
            contamination_count=contamination,
        )
        record_ai_stage(
            provider=settings.AI_BACKEND, model=self._engine.model,
            environment=environment, hint_level=hint_level,
            stage="retrieval", result=result, duration_ms=elapsed,
        )
        record_ai_stage(
            provider=settings.AI_BACKEND, model=self._engine.model,
            environment=environment, hint_level=hint_level,
            stage="rerank", result=result, duration_ms=retrieval.rerank_ms,
        )
        return retrieval, elapsed, error

    async def _load_conversation(
        self, attempt_id: uuid.UUID, db: AsyncSession | None
    ) -> list[dict]:
        if db is None:
            return []
        try:
            from app.models import TutorMessage
            result = await db.execute(
                select(TutorMessage)
                .where(TutorMessage.attempt_id == attempt_id)
                .order_by(TutorMessage.created_at.desc())
                .limit(10)
            )
            msgs = result.scalars().all()
            return self._conversation_pairs(list(reversed(msgs)))
        except Exception:
            return []

    @staticmethod
    def _conversation_pairs(messages, max_pairs: int = 5, max_chars: int = 2_000) -> list[dict]:
        """시간순 user/assistant pair만 유지하고 최신 pair부터 예산에 맞춘다."""
        pairs = []
        pending_user = None
        for message in messages:
            if message.role == "user":
                pending_user = message
            elif message.role == "assistant" and pending_user is not None:
                pairs.append({
                    "user": str(pending_user.message)[:500],
                    "assistant": str(message.message)[:500],
                    "hint_level": message.hint_level,
                })
                pending_user = None

        selected = []
        used = 0
        for pair in reversed(pairs[-max_pairs:]):
            size = len(pair["user"]) + len(pair["assistant"])
            if selected and used + size > max_chars:
                break
            if size > max_chars:
                pair = {
                    **pair,
                    "user": pair["user"][: max_chars // 2],
                    "assistant": pair["assistant"][: max_chars // 2],
                }
                size = len(pair["user"]) + len(pair["assistant"])
            selected.append(pair)
            used += size
        return list(reversed(selected))

    async def _save_messages(
        self,
        db: AsyncSession,
        attempt_id: uuid.UUID,
        user_question: str,
        assistant_response: str,
        hint_level: int,
    ):
        started = time.perf_counter()
        try:
            from app.models import TutorMessage
            db.add(TutorMessage(
                attempt_id=attempt_id,
                role="user",
                message=user_question,
                hint_level=hint_level,
            ))
            db.add(TutorMessage(
                attempt_id=attempt_id,
                role="assistant",
                message=assistant_response,
                hint_level=hint_level,
            ))
            await db.commit()
        except Exception:
            logger.exception("AI tutor message persistence failed")

    async def _call_engine(
        self,
        user_question: str,
        hint_level: int,
        mission_name: str,
        mission_level: int,
        chaos_type: str,
        namespace: str,
        conversation_history: list[dict],
        attempt_id: str,
        runtime_ctx: dict | None,
        fault_type: str | None = None,
        environment: str = "kubernetes",
        retrieval_result=None,
    ):
        started = time.perf_counter()
        try:
            from ai_engine import TutorRequest
            from prompt_engine import MissionContext, TrainingContext, UserContext

            mission_ctx = MissionContext(
                mission_id=attempt_id,
                mission_name=mission_name,
                mission_level=mission_level,
                chaos_type=chaos_type,
                expected_solution=chaos_type,
            )

            user_ctx = UserContext(
                user_id=attempt_id,
                hint_count=hint_level,
                previous_questions=[],
                conversation_history=conversation_history,
            )
            runtime_ctx = runtime_ctx or {
                "environment": environment, "scope": {"namespace": namespace},
                "mission": {}, "observations": {}, "recent_user_commands": [],
                "metrics": {}, "logs": [],
            }
            from app.ai.runtime_observations import prepare_runtime_context
            runtime_ctx = prepare_runtime_context(runtime_ctx, user_question, environment)
            training_ctx = TrainingContext(
                environment=environment,
                scope=runtime_ctx.get("scope", {"namespace": namespace}),
                mission={**runtime_ctx.get("mission", {}), **mission_ctx.__dict__},
                observations=runtime_ctx.get("observations", {}),
                recent_commands=runtime_ctx.get("recent_user_commands", []),
                metrics=runtime_ctx.get("metrics", {}),
                logs=runtime_ctx.get("logs", []),
                user=user_ctx.__dict__,
                collection_status=runtime_ctx.get("collection_status", {}),
            )

            request = TutorRequest(
                user_question=user_question,
                hint_level=hint_level,
                mission_ctx=mission_ctx,
                user_ctx=user_ctx,
                chaos_type=fault_type,
                environment=environment,
                training_ctx=training_ctx,
            )

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._engine.get_response, request,
                    retrieval_result=retrieval_result,
                ),
                timeout=settings.OPENAI_TIMEOUT,
            )
            llm_ms = response.latency_breakdown.get("llm_ms", response.latency_ms)
            record_ai_stage(
                provider=settings.AI_BACKEND, model=self._engine.model,
                environment=environment, hint_level=hint_level,
                stage="llm", result="fallback" if response.fallback_used else "success",
                duration_ms=llm_ms,
            )
            record_ai_call(
                provider=settings.AI_BACKEND,
                purpose="tutor",
                result="fallback" if response.fallback_used else "success",
                duration_seconds=time.perf_counter() - started,
                token_usage=response.token_usage,
                model=self._engine.model,
            )
            from app.schemas import TutorResult
            return TutorResult(
                message=response.message,
                hint_level=response.hint_level,
                environment=response.environment,
                sources=response.sources,
                observations_used=response.observations_used,
                token_usage=response.token_usage,
                latency_ms=response.latency_ms,
                fallback_used=response.fallback_used,
                error_code=response.error_code,
                latency_breakdown=response.latency_breakdown,
            )

        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - started) * 1000
            record_ai_stage(
                provider=settings.AI_BACKEND, model=self._engine.model,
                environment=environment, hint_level=hint_level,
                stage="llm", result="timeout", duration_ms=elapsed,
            )
            record_ai_call(
                provider=settings.AI_BACKEND, purpose="tutor", result="fallback",
                duration_seconds=elapsed / 1000,
                model=self._engine.model,
            )
            from app.schemas import TutorResult
            return TutorResult(
                message="AI 튜터 응답 시간이 초과되었습니다. 잠시 후 다시 질문해 주세요.",
                hint_level=hint_level, environment=environment,
                fallback_used=True, error_code="provider_timeout",
                latency_ms=round(elapsed), latency_breakdown={"llm_ms": elapsed},
            )
        except Exception:
            record_ai_call(
                provider=settings.AI_BACKEND,
                purpose="tutor",
                result="fallback",
                duration_seconds=time.perf_counter() - started,
                model=self._engine.model,
            )
            logger.exception("AI tutor adapter call failed; using safe fallback")
            from app.schemas import TutorResult
            return TutorResult(
                message="현재 AI 튜터 응답을 생성하지 못했습니다. 잠시 후 다시 질문해 주세요.",
                hint_level=hint_level,
                environment=environment,
                fallback_used=True,
                error_code="adapter_failed",
            )

    def _get_pod_status_fallback(self, namespace: str) -> tuple[str, str]:
        """RuntimeContextCollector 실패 시 직접 K8s 조회 fallback."""
        try:
            from kubernetes import client, config
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()

            core_api = client.CoreV1Api()
            pods = core_api.list_namespaced_pod(namespace=namespace)
            if not pods.items:
                return "Pod 없음", "네임스페이스에 Pod가 존재하지 않습니다"

            status_lines = []
            for pod in pods.items:
                phase = pod.status.phase or "Unknown"
                for cs in (pod.status.container_statuses or []):
                    if cs.state.waiting:
                        phase = cs.state.waiting.reason or "Waiting"
                    elif cs.state.terminated:
                        phase = f"Terminated({cs.state.terminated.reason or ''})"
                status_lines.append(f"{pod.metadata.name}: {phase}")

            events = core_api.list_namespaced_event(namespace=namespace)
            recent = []
            for ev in sorted(
                events.items,
                key=lambda e: e.last_timestamp.isoformat() if e.last_timestamp else "",
                reverse=True,
            )[:5]:
                if ev.message:
                    recent.append(f"- {ev.reason}: {ev.message[:100]}")

            return "\n".join(status_lines), "\n".join(recent) if recent else "이벤트 없음"
        except Exception as e:
            return "조회 실패", f"K8s API 오류: {e}"

    def _mock_response(self, question: str, hint_level: int, chaos_type: str) -> str:
        scenarios = {
            "pod_failure": {
                0: "Pod가 갑자기 사라지거나 재시작되는 상황이에요. 클러스터에서 어떤 Pod들이 있는지 먼저 확인해볼까요?",
                1: "Pod 상태가 이상해 보이나요? Running이 아닌 Pod가 있다면, 그 Pod의 상세 정보를 어떻게 볼 수 있을까요?",
                2: "`kubectl get pods`로 비정상 Pod를 찾고, `kubectl describe pod <이름>`의 Events 섹션에서 왜 죽었는지 확인해보세요.",
                3: "1. `kubectl get pods` 로 CrashLoopBackOff 또는 Error 상태 Pod 확인\n2. `kubectl describe pod <이름>` 으로 종료 이유 확인\n3. `kubectl delete pod <이름>` 으로 재시작 유도",
            },
            "memory_stress": {
                0: "서버가 느려지거나 응답이 없는 상황이에요. 리소스 측면에서 뭔가 이상한 게 있을 것 같은데, 어디서 확인할 수 있을까요?",
                1: "메모리가 과하게 사용되고 있을 수 있어요. Pod의 리소스 사용량을 볼 수 있는 명령어가 있을까요?",
                2: "`kubectl top pods`로 메모리 사용량 확인 후, 과부하 Pod를 `kubectl describe`로 상세 조회해보세요. OOMKilled 메시지가 보이나요?",
                3: "1. `kubectl top pods` 로 메모리 과다 사용 Pod 확인\n2. `kubectl describe pod <이름>` 에서 OOMKilled 확인\n3. Pod의 memory limit 조정 또는 재시작",
            },
            "service_misconfig": {
                0: "웹페이지에 접속이 안 되는 상황이에요. 요청이 어떤 경로로 흘러가는지 생각해보면, 어디서 끊겼을 것 같나요?",
                1: "Service와 Pod가 제대로 연결되어 있는지 확인이 필요해요. Service의 selector와 Pod의 label이 일치하는지 어떻게 확인할 수 있을까요?",
                2: "`kubectl get svc`로 Service 확인 후, `kubectl describe svc <이름>`에서 Endpoints가 비어있는지 확인해보세요.",
                3: "1. `kubectl get svc` 로 Service 목록 확인\n2. `kubectl describe svc <이름>` 에서 Endpoints 확인\n3. `kubectl get pods --show-labels` 로 label 비교\n4. Service selector 또는 Pod label 수정",
            },
            "network_latency": {
                0: "Pod는 Running인데 서비스 트래픽을 못 받는 상황이에요. Pod가 Running이어도 트래픽을 받으려면 또 다른 조건이 필요한데, 뭔지 알고 있나요?",
                1: "Readiness Probe라는 개념이 있어요. Pod가 실제로 요청을 처리할 준비가 됐는지 확인하는 건강검진이에요. nginx의 Readiness Probe 설정이 어떻게 되어 있는지 확인해볼까요?",
                2: "`kubectl describe pod <이름>`의 Conditions 섹션에서 Ready 상태와 Readiness probe 실패 메시지를 확인해보세요. probe가 어떤 경로를 체크하고 있나요?",
                3: "1. `kubectl describe pod <이름>` 으로 Readiness probe 실패 경로 확인\n2. `kubectl patch deployment nginx -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"readinessProbe\":null}]}}}}'` 로 probe 제거\n3. 또는 `kubectl edit deployment nginx` 로 readinessProbe 섹션 삭제",
            },
        }

        scenario = scenarios.get(chaos_type, {
            0: "현재 상황을 파악해보세요. 어떤 명령어로 클러스터 상태를 확인할 수 있을까요?",
            1: "Pod 상태를 자세히 확인해볼까요? `kubectl describe`가 도움이 될 수 있어요.",
            2: "`kubectl describe pod <이름>`의 Events 섹션에서 에러 메시지를 찾아보세요.",
            3: f"1. `kubectl get pods` 로 문제 Pod 확인\n2. `kubectl describe pod <이름>` 으로 원인 파악\n3. 상황에 맞게 수정 후 정상화 확인",
        })
        return scenario.get(hint_level, scenario[0])

    def clear_history(self, attempt_id: uuid.UUID):
        pass  # 이제 DB가 단일 진실 공급원


# 싱글톤
_tutor_service: Optional[TutorService] = None


def get_tutor_service() -> TutorService:
    global _tutor_service
    if _tutor_service is None:
        _tutor_service = TutorService()
    return _tutor_service
