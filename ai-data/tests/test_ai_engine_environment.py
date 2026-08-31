from types import SimpleNamespace

from ai_engine import AITutorEngine, TutorRequest
from config import AISettings
from tests.fakes import DeterministicFakeOpenAI


class _PromptEngine:
    def generate_prompt(self, **kwargs):
        return "SYSTEM\n=== USER QUESTION ==="


class _RAG:
    def __init__(self):
        self.calls = []

    def search_knowledge(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return [
            SimpleNamespace(
                source="docker.md",
                content="Docker network diagnostic",
            )
        ]


def test_tutor_engine_passes_request_environment_to_rag():
    engine = object.__new__(AITutorEngine)
    engine.settings = AISettings(AI_BACKEND="mock")
    engine.model = "fake-model"
    engine.use_rag = True
    engine.prompt_engine = _PromptEngine()
    engine.rag_service = _RAG()
    engine.client = DeterministicFakeOpenAI()

    response = engine.get_response(
        TutorRequest(
            user_question="컨테이너 네트워크를 무엇부터 볼까요?",
            hint_level=1,
            chaos_type="container_network_disconnect",
            environment="docker",
        )
    )

    assert engine.rag_service.calls == [
        (
            "컨테이너 네트워크를 무엇부터 볼까요?",
            {
                "environment": "docker",
                "fault_type": "container_network_disconnect",
            },
        )
    ]
    assert response.sources == ["docker.md"]


def test_tutor_request_keeps_kubernetes_default_for_existing_callers():
    request = TutorRequest(user_question="Pod 상태는요?")

    assert request.environment == "kubernetes"
