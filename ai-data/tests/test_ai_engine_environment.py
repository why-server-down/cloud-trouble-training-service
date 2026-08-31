from types import SimpleNamespace

from ai_engine import AITutorEngine, TutorRequest
from config import AISettings
from tests.fakes import DeterministicFakeOpenAI


class _PromptEngine:
    def __init__(self):
        self.kwargs = None

    def generate_prompt(self, **kwargs):
        self.kwargs = kwargs
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
                similarity=0.91,
                metadata={
                    "title": "Docker Network",
                    "source_id": "docker-network-troubleshooting",
                    "environments": ["docker"],
                },
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
    assert response.sources == [{
        "title": "Docker Network",
        "source_id": "docker-network-troubleshooting",
        "path": "docker.md",
        "environment": "docker",
        "similarity": 0.91,
    }]
    assert engine.prompt_engine.kwargs["training_ctx"].environment == "docker"
    assert engine.prompt_engine.kwargs["training_ctx"].retrieved_docs == [
        {"source": response.sources[0], "content": "Docker network diagnostic"}
    ]


def test_tutor_response_reports_used_observations_and_hides_absolute_path():
    engine = object.__new__(AITutorEngine)
    engine.settings = AISettings(AI_BACKEND="mock")
    engine.model = "fake-model"
    engine.use_rag = True
    engine.prompt_engine = _PromptEngine()
    engine.rag_service = _RAG()
    engine.rag_service.search_knowledge = lambda *args, **kwargs: [
        SimpleNamespace(
            source="/Users/private/secret.md", content="evidence", similarity=0.8,
            metadata={"title": "Safe title", "source_id": "safe-id", "environments": ["linux"]},
        )
    ]
    engine.client = DeterministicFakeOpenAI()

    from prompt_engine import TrainingContext
    response = engine.get_response(TutorRequest(
        user_question="상태는요?", hint_level=1, environment="linux",
        training_ctx=TrainingContext(
            environment="linux", observations={"processes": "pid 1", "disk": ""},
            metrics={"load": 2.0}, recent_commands=["ps"], logs=["service stopped"],
        ),
    ))

    assert response.sources[0]["path"] is None
    assert response.observations_used == ["processes", "metrics.load", "logs", "recent_commands"]


def test_rag_failure_returns_safe_fallback_without_exception_text():
    engine = object.__new__(AITutorEngine)
    engine.settings = AISettings(AI_BACKEND="mock")
    engine.model = "fake-model"
    engine.use_rag = True
    engine.prompt_engine = _PromptEngine()
    engine.rag_service = SimpleNamespace(
        search_knowledge=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("API_KEY=secret traceback"))
    )
    engine.client = DeterministicFakeOpenAI()

    response = engine.get_response(TutorRequest(user_question="도와줘", hint_level=1))

    assert response.fallback_used is True
    assert response.error_code == "retrieval_failed"
    assert response.sources == []
    assert "secret" not in response.message
    assert "traceback" not in response.message


def test_tutor_request_keeps_kubernetes_default_for_existing_callers():
    request = TutorRequest(user_question="Pod 상태는요?")

    assert request.environment == "kubernetes"
