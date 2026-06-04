"""
AI 튜터 서비스 - ai-data 모듈을 FastAPI 백엔드와 연결하는 어댑터
"""

import sys
import os
import asyncio
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

# ai-data 경로를 Python path에 추가
_AI_DATA_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../ai-data")
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

        os.environ["AI_BACKEND"] = settings.AI_BACKEND

        if settings.AI_BACKEND == "gemini":
            if not settings.GEMINI_API_KEY:
                return
            os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY
            os.environ["GEMINI_MODEL"] = settings.GEMINI_MODEL
            os.environ["GEMINI_EMBEDDING_MODEL"] = settings.GEMINI_EMBEDDING_MODEL
            api_key = settings.GEMINI_API_KEY
            model = settings.GEMINI_MODEL
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        else:
            if not settings.OPENAI_API_KEY:
                return
            os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
            api_key = settings.OPENAI_API_KEY
            model = settings.TUTOR_MODEL
            base_url = None

        try:
            from ai_engine import AITutorEngine
            self._engine = AITutorEngine(
                openai_api_key=api_key,
                model=model,
                use_rag=True,
                api_base_url=base_url,
            )
        except Exception as e:
            print(f"[AI Tutor] 엔진 초기화 실패 (Mock 모드로 fallback): {e}")
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
    ) -> str:
        self._init_engine()

        # DB에서 이전 질문 이력 로드 (세션 간 연속성)
        previous_questions = await self._load_previous_questions(attempt_id, db)

        # RuntimeContext 수집 (k8s 환경에서만)
        runtime_ctx: dict | None = None
        if db is not None and settings.VALIDATION_BACKEND == "k8s":
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

                if user_id:
                    collector = get_runtime_context_collector()
                    runtime_ctx = await collector.collect(
                        user_id=user_id,
                        namespace=namespace,
                        db=db,
                        scenario_title=mission_name,
                        scenario_id=scenario_id,
                    )
            except Exception as e:
                print(f"[AI Tutor] RuntimeContext 수집 실패 (무시): {e}")

        if self._engine is None:
            response = self._mock_response(user_question, hint_level, chaos_type)
        else:
            response = await self._call_engine(
                user_question=user_question,
                hint_level=hint_level,
                mission_name=mission_name,
                mission_level=mission_level,
                chaos_type=chaos_type,
                namespace=namespace,
                previous_questions=previous_questions,
                attempt_id=str(attempt_id),
                runtime_ctx=runtime_ctx,
                fault_type=chaos_type,
            )

        # TutorMessage DB 저장
        if db is not None:
            await self._save_messages(db, attempt_id, user_question, response, hint_level)

        return response

    async def _load_previous_questions(
        self, attempt_id: uuid.UUID, db: AsyncSession | None
    ) -> list[str]:
        if db is None:
            return []
        try:
            from app.models import TutorMessage
            result = await db.execute(
                select(TutorMessage)
                .where(
                    TutorMessage.attempt_id == attempt_id,
                    TutorMessage.role == "user",
                )
                .order_by(TutorMessage.created_at.desc())
                .limit(5)
            )
            msgs = result.scalars().all()
            return [m.message for m in reversed(msgs)]
        except Exception:
            return []

    async def _save_messages(
        self,
        db: AsyncSession,
        attempt_id: uuid.UUID,
        user_question: str,
        assistant_response: str,
        hint_level: int,
    ):
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
        except Exception as e:
            print(f"[AI Tutor] TutorMessage 저장 실패 (무시): {e}")

    async def _call_engine(
        self,
        user_question: str,
        hint_level: int,
        mission_name: str,
        mission_level: int,
        chaos_type: str,
        namespace: str,
        previous_questions: list[str],
        attempt_id: str,
        runtime_ctx: dict | None,
        fault_type: str | None = None,
    ) -> str:
        try:
            from ai_engine import TutorRequest
            from prompt_engine import MissionContext, SystemContext, UserContext

            mission_ctx = MissionContext(
                mission_id=attempt_id,
                mission_name=mission_name,
                mission_level=mission_level,
                chaos_type=chaos_type,
                expected_solution=chaos_type,
            )

            if runtime_ctx is not None:
                from app.services.runtime_context import (
                    format_k8s_state, format_recent_commands, format_events
                )
                pod_status = format_k8s_state(runtime_ctx.get("kubernetes_state"))
                pod_logs = format_recent_commands(runtime_ctx.get("recent_user_commands", []))
                recent_events = format_events(runtime_ctx.get("kubernetes_state"))
            elif settings.VALIDATION_BACKEND == "k8s":
                pod_status, recent_events = self._get_pod_status_fallback(namespace)
                pod_logs = "(로그는 kubectl logs <pod-name> 으로 직접 확인하세요)"
            else:
                pod_status = "Unknown (Mock 환경)"
                recent_events = "(실제 K8s 환경에서는 이벤트가 제공됩니다)"
                pod_logs = "(로그는 kubectl logs <pod-name> 으로 직접 확인하세요)"

            system_ctx = SystemContext(
                namespace=namespace,
                pod_status=pod_status,
                pod_logs=pod_logs,
                recent_events=recent_events,
            )
            user_ctx = UserContext(
                user_id=attempt_id,
                hint_count=hint_level,
                previous_questions=previous_questions,
            )

            request = TutorRequest(
                user_question=user_question,
                hint_level=hint_level,
                mission_ctx=mission_ctx,
                system_ctx=system_ctx,
                user_ctx=user_ctx,
                chaos_type=fault_type,
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._engine.get_response(request)
            )
            return response.message

        except Exception as e:
            return f"AI 튜터 응답 중 오류가 발생했습니다: {str(e)}"

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
