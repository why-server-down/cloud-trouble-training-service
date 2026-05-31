"""
AI 튜터 서비스 - ai-data 모듈을 FastAPI 백엔드와 연결하는 어댑터
"""

import sys
import os
import asyncio
import uuid
from typing import Optional

from app.core.config import settings

# ai-data 경로를 Python path에 추가
_AI_DATA_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../ai-data")
)
if _AI_DATA_PATH not in sys.path:
    sys.path.insert(0, _AI_DATA_PATH)


class ChatMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


class TutorService:
    """
    AI 튜터 서비스
    - openai 모드: ai-data의 AITutorEngine 사용 (RAG + GPT)
    - mock 모드: 간단한 고정 응답 (OpenAI 키 없을 때)
    """

    def __init__(self):
        self._engine = None
        self._chat_history: dict[str, list[str]] = {}  # attempt_id -> 이전 질문 목록
        self._initialized = False

    def _init_engine(self):
        if self._initialized:
            return
        self._initialized = True

        if settings.AI_BACKEND != "openai" or not settings.OPENAI_API_KEY:
            return

        try:
            from ai_engine import AITutorEngine
            self._engine = AITutorEngine(
                openai_api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_MODEL,
                use_rag=True,
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
    ) -> str:
        self._init_engine()

        key = str(attempt_id)
        previous_questions = self._chat_history.get(key, [])

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
                attempt_id=key,
            )

        # 대화 히스토리 저장 (최근 5개만 유지)
        previous_questions.append(user_question)
        self._chat_history[key] = previous_questions[-5:]

        return response

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
            system_ctx = SystemContext(
                namespace=namespace,
                pod_status="Unknown (Mock 환경)",
                pod_logs="(실제 K8s 환경에서는 실시간 로그가 제공됩니다)",
                recent_events="(실제 K8s 환경에서는 이벤트가 제공됩니다)",
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
            )

            # 동기 함수를 비동기로 실행
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._engine.get_response(request)
            )
            return response.message

        except Exception as e:
            return f"AI 튜터 응답 중 오류가 발생했습니다: {str(e)}"

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
                0: "응답이 매우 느린 상황이에요. 네트워크 레벨에서 문제가 생겼을 수 있는데, 어떤 Pod 간 통신이 느린지 확인해볼까요?",
                1: "특정 Pod나 Node에서 네트워크 지연이 발생하고 있을 수 있어요. Pod의 상태와 이벤트를 확인해보면 단서가 있을까요?",
                2: "`kubectl get pods -o wide`로 어떤 Node에 있는지 확인하고, `kubectl describe pod <이름>`의 Events에서 네트워크 관련 메시지를 찾아보세요.",
                3: "1. `kubectl get pods -o wide` 로 Pod 위치 확인\n2. `kubectl describe pod <이름>` 으로 네트워크 이벤트 확인\n3. NetworkChaos 정책 또는 Pod 재배치로 해결",
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
        self._chat_history.pop(str(attempt_id), None)


# 싱글톤
_tutor_service: Optional[TutorService] = None


def get_tutor_service() -> TutorService:
    global _tutor_service
    if _tutor_service is None:
        _tutor_service = TutorService()
    return _tutor_service
