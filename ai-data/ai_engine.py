"""
AI Tutor Engine
Main interface for AI tutoring functionality
Integrates RAG, Prompt Engineering, and LLM
"""

import inspect
import os
import time
from typing import Dict, Optional
from dataclasses import asdict, dataclass
import openai

from config import AISettings, config
from context_safety import enforce_token_budget, redact_text
from rag_service import RAGService
from prompt_engine import (
    SocraticPromptEngine,
    MissionContext,
    SystemContext,
    TrainingContext,
    UserContext,
)

@dataclass
class TutorRequest:
    """Request to AI tutor"""
    user_question: str
    hint_level: int = 0
    mission_ctx: Optional[MissionContext] = None
    system_ctx: Optional[SystemContext] = None
    user_ctx: Optional[UserContext] = None
    chaos_type: Optional[str] = None
    environment: str = "kubernetes"
    training_ctx: Optional[TrainingContext] = None


@dataclass
class TutorResponse:
    """Response from AI tutor"""
    message: str
    hint_level: int
    sources: list
    token_usage: Dict
    environment: str = "kubernetes"
    observations_used: list[str] = None
    latency_ms: int = 0
    fallback_used: bool = False
    error_code: Optional[str] = None
    latency_breakdown: Dict[str, float] = None

    def __post_init__(self):
        if self.observations_used is None:
            self.observations_used = []
        if self.latency_breakdown is None:
            self.latency_breakdown = {}


@dataclass
class RetrievalResult:
    sources: list
    context: list
    latency_ms: float
    rerank_ms: float = 0.0
    error_code: Optional[str] = None


class AITutorEngine:
    """
    Main AI Tutor Engine
    Coordinates RAG, prompt generation, and LLM calls
    """
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        model: Optional[str] = None,
        use_rag: bool = True,
        api_base_url: Optional[str] = None,
        settings: Optional[AISettings] = None,
    ):
        """
        Initialize AI Tutor Engine

        Args:
            openai_api_key: API key (OpenAI or Gemini)
            model: Model name
            use_rag: Whether to use RAG for knowledge retrieval
            api_base_url: Custom base URL (Gemini OpenAI-compatible endpoint 등)
        """
        self.settings = settings or config
        self.api_key = openai_api_key or self.settings.provider_api_key
        self.model = model or self.settings.tutor_model
        self.use_rag = use_rag
        api_base_url = api_base_url or self.settings.api_base_url

        # OpenAI-compatible client (Gemini은 base_url만 다름)
        client_kwargs = {"api_key": self.api_key}
        if api_base_url:
            client_kwargs["base_url"] = api_base_url
        self.client = openai.OpenAI(**client_kwargs)

        # Initialize components
        self.prompt_engine = SocraticPromptEngine()

        if self.use_rag:
            self.rag_service = RAGService(settings=self.settings)
    
    def get_response(
        self,
        request: TutorRequest,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        retrieval_result: Optional[RetrievalResult] = None,
    ) -> TutorResponse:
        """
        Get AI tutor response
        
        Args:
            request: Tutor request with question and context
            max_tokens: Maximum tokens in response
            temperature: LLM temperature (0-1)
        
        Returns:
            TutorResponse with message and metadata
        """
        started = time.perf_counter()
        if max_tokens is None:
            max_tokens = self.settings.OPENAI_MAX_TOKENS
        max_tokens = max(1, min(max_tokens, self.settings.AI_MAX_COMPLETION_TOKENS))
        if temperature is None:
            temperature = self.settings.OPENAI_TEMPERATURE

        # Augment with RAG if enabled and hint level >= 1
        retrieval_result = retrieval_result or self.retrieve(request)
        sources = retrieval_result.sources
        retrieved_context = retrieval_result.context

        training_ctx = request.training_ctx
        if training_ctx is not None:
            training_ctx = TrainingContext(**{
                **training_ctx.__dict__,
                "environment": request.environment,
                "retrieved_docs": retrieved_context,
            })
        else:
            training_ctx = TrainingContext(
                environment=request.environment,
                mission=asdict(request.mission_ctx) if request.mission_ctx else {},
                observations=asdict(request.system_ctx) if request.system_ctx else {},
                retrieved_docs=retrieved_context,
                user=asdict(request.user_ctx) if request.user_ctx else {},
            )

        prompt = self.prompt_engine.generate_prompt(
            user_question=request.user_question,
            hint_level=request.hint_level,
            training_ctx=training_ctx,
            mission_ctx=request.mission_ctx,
            system_ctx=request.system_ctx,
            user_ctx=request.user_ctx,
        )
        prompt = enforce_token_budget(prompt, self.settings.AI_MAX_CONTEXT_TOKENS)
        
        # Call LLM
        llm_started = time.perf_counter()
        try:
            response = self._create_with_retry(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "구조화된 USER QUESTION 데이터에 대해 튜터 지침대로 답하세요."}
                ],
                max_tokens=max_tokens, temperature=temperature,
                timeout=self.settings.OPENAI_TIMEOUT,
            )
            
            message = redact_text(response.choices[0].message.content or "")
            token_usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
        except Exception:
            return self._fallback_response(request, started, "provider_failed")
        llm_ms = (time.perf_counter() - llm_started) * 1000
        total_ms = (time.perf_counter() - started) * 1000
        return TutorResponse(
            message=message,
            hint_level=request.hint_level,
            sources=sources,
            token_usage=token_usage,
            environment=request.environment,
            observations_used=self._observation_keys(training_ctx),
            latency_ms=int(total_ms),
            latency_breakdown={
                "retrieval_ms": retrieval_result.latency_ms,
                "rerank_ms": retrieval_result.rerank_ms,
                "llm_ms": llm_ms,
                "total_ms": total_ms,
            },
            fallback_used=bool(retrieval_result.error_code),
            error_code=retrieval_result.error_code,
        )

    def retrieve(self, request: TutorRequest) -> RetrievalResult:
        """동기 RAG 단계를 LLM 호출과 분리해 adapter가 thread로 병렬 실행할 수 있게 한다."""
        started = time.perf_counter()
        if not self.use_rag or request.hint_level < 1:
            return RetrievalResult([], [], 0.0)
        try:
            timing = {}
            search = self.rag_service.search_knowledge
            kwargs = {
                "environment": request.environment,
                "fault_type": request.chaos_type,
            }
            if "timing" in inspect.signature(search).parameters:
                kwargs["timing"] = timing
            retrieved_docs = search(request.user_question, **kwargs)
        except Exception:
            return RetrievalResult(
                [], [], (time.perf_counter() - started) * 1000,
                error_code="retrieval_failed",
            )
        retrieved_docs = retrieved_docs[: self.settings.AI_MAX_RETRIEVED_CHUNKS]
        sources = [self._safe_source(doc, request.environment) for doc in retrieved_docs]
        context = [
            {"source": source, "content": doc.content}
            for source, doc in zip(sources, retrieved_docs)
        ]
        return RetrievalResult(
            sources, context, (time.perf_counter() - started) * 1000,
            rerank_ms=timing.get("rerank_ms", 0.0),
        )

    def _create_with_retry(self, **kwargs):
        """Rate limit/connection만 최대 설정 횟수까지 재시도한다."""
        attempts = max(1, min(3, self.settings.AI_PROVIDER_MAX_ATTEMPTS))
        for attempt in range(attempts):
            try:
                return self.client.chat.completions.create(**kwargs)
            except (openai.RateLimitError, openai.APIConnectionError):
                if attempt + 1 >= attempts:
                    raise
                time.sleep(min(0.25, 0.05 * (2 ** attempt)))

    @staticmethod
    def _safe_source(document, environment: str) -> dict:
        metadata = document.metadata or {}
        path = document.source
        if not path or os.path.isabs(path) or ".." in path.replace("\\", "/").split("/"):
            path = None
        source_id = metadata.get("source_id")
        if source_id and (os.path.isabs(str(source_id)) or "/" in str(source_id) or "\\" in str(source_id)):
            source_id = None
        title = metadata.get("title")
        if not title or os.path.isabs(str(title)):
            title = source_id or "Knowledge document"
        environments = metadata.get("environments") or []
        source_environment = environment if environment in environments else (
            environments[0] if len(environments) == 1 and environments[0] != "general" else None
        )
        return {
            "title": title,
            "source_id": source_id,
            "path": path,
            "environment": source_environment,
            "similarity": round(float(document.similarity), 6),
        }

    @staticmethod
    def _observation_keys(context: TrainingContext) -> list[str]:
        keys = [key for key, value in context.observations.items() if value not in (None, "", [], {})]
        keys.extend(
            f"metrics.{key}" for key, value in context.metrics.items()
            if value not in (None, "", [], {})
        )
        if context.logs:
            keys.append("logs")
        if context.recent_commands:
            keys.append("recent_commands")
        return keys

    def _fallback_response(self, request: TutorRequest, started: float, code: str) -> TutorResponse:
        return TutorResponse(
            message="현재 AI 튜터 응답을 생성하지 못했습니다. 관측된 상태와 최근 명령을 다시 확인한 뒤 잠시 후 질문해 주세요.",
            hint_level=request.hint_level,
            sources=[],
            token_usage={},
            environment=request.environment,
            observations_used=[],
            latency_ms=int((time.perf_counter() - started) * 1000),
            fallback_used=True,
            error_code=code,
            latency_breakdown={"total_ms": (time.perf_counter() - started) * 1000},
        )
    
    def initialize_knowledge_base(self, force_reload: bool = False):
        """
        Initialize or reload knowledge base
        
        Args:
            force_reload: If True, clear and reload all documents
        """
        if not self.use_rag:
            print("RAG is disabled")
            return
        
        stats = self.rag_service.get_collection_stats()
        
        if stats['document_count'] > 0 and not force_reload:
            print(f"Knowledge base already initialized with {stats['document_count']} documents")
            return
        
        if force_reload:
            print("Clearing existing knowledge base...")
            self.rag_service.clear_collection()
        
        print("Loading documents...")
        docs = self.rag_service.load_documents()
        print(f"Loaded {len(docs)} documents")
        
        print("Chunking documents...")
        chunks = self.rag_service.chunk_documents(docs)
        print(f"Created {len(chunks)} chunks")
        
        print("Ingesting into vector database...")
        count = self.rag_service.ingest_documents(chunks)
        print(f"Successfully ingested {count} chunks")
        
        return count


def main():
    """Example usage of AI Tutor Engine"""
    print("Initializing AI Tutor Engine...")
    engine = AITutorEngine(use_rag=True)
    
    # Initialize knowledge base
    print("\nInitializing knowledge base...")
    engine.initialize_knowledge_base()
    
    # Example request
    print("\n" + "="*80)
    print("EXAMPLE: Student asking about ImagePullBackOff")
    print("="*80)
    
    mission = MissionContext(
        mission_id="m1",
        mission_name="ImagePullBackOff Challenge",
        mission_level=1,
        chaos_type="image_pull_error",
        expected_solution="Fix image name typo"
    )
    
    system = SystemContext(
        namespace="user-123",
        pod_status="ImagePullBackOff",
        pod_logs="Error: Failed to pull image 'ngnix:latest'",
        recent_events="Failed to pull image: rpc error: code = NotFound"
    )
    
    user = UserContext(
        user_id="user-123",
        hint_count=0,
        previous_questions=[]
    )
    
    # Test at different hint levels
    questions = [
        "My pod is not starting. What should I check?",
        "I see ImagePullBackOff error. What does that mean?",
        "How do I fix the image pull error?",
    ]
    
    for hint_level, question in enumerate(questions):
        print(f"\n{'='*80}")
        print(f"HINT LEVEL {hint_level}: {question}")
        print('='*80)
        
        request = TutorRequest(
            user_question=question,
            hint_level=hint_level,
            mission_ctx=mission,
            system_ctx=system,
            user_ctx=user
        )
        
        response = engine.get_response(request)
        
        print(f"\nAI Response:")
        print(response.message)
        print(f"\nSources: {', '.join(response.sources) if response.sources else 'None'}")
        print(f"Tokens: {response.token_usage}")
        
        # Update user context
        user.hint_count += 1
        user.previous_questions.append(question)


if __name__ == "__main__":
    main()
