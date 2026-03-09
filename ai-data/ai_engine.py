"""
AI Tutor Engine
Main interface for AI tutoring functionality
Integrates RAG, Prompt Engineering, and LLM
"""

import os
from typing import Dict, Optional
from dataclasses import dataclass
import openai
from dotenv import load_dotenv

from rag_service import RAGService
from prompt_engine import (
    SocraticPromptEngine,
    MissionContext,
    SystemContext,
    UserContext
)

load_dotenv()


@dataclass
class TutorRequest:
    """Request to AI tutor"""
    user_question: str
    hint_level: int = 0
    mission_ctx: Optional[MissionContext] = None
    system_ctx: Optional[SystemContext] = None
    user_ctx: Optional[UserContext] = None


@dataclass
class TutorResponse:
    """Response from AI tutor"""
    message: str
    hint_level: int
    sources: list
    token_usage: Dict


class AITutorEngine:
    """
    Main AI Tutor Engine
    Coordinates RAG, prompt generation, and LLM calls
    """
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        model: str = "gpt-4",
        use_rag: bool = True
    ):
        """
        Initialize AI Tutor Engine
        
        Args:
            openai_api_key: OpenAI API key (defaults to env var)
            model: OpenAI model to use
            use_rag: Whether to use RAG for knowledge retrieval
        """
        self.api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.use_rag = use_rag
        
        # Initialize OpenAI client
        openai.api_key = self.api_key
        self.client = openai.OpenAI(api_key=self.api_key)
        
        # Initialize components
        self.prompt_engine = SocraticPromptEngine()
        
        if self.use_rag:
            self.rag_service = RAGService()
    
    def get_response(
        self,
        request: TutorRequest,
        max_tokens: int = 500,
        temperature: float = 0.7
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
        # Generate base prompt
        prompt = self.prompt_engine.generate_prompt(
            user_question=request.user_question,
            hint_level=request.hint_level,
            mission_ctx=request.mission_ctx,
            system_ctx=request.system_ctx,
            user_ctx=request.user_ctx
        )
        
        # Augment with RAG if enabled and hint level >= 1
        sources = []
        if self.use_rag and request.hint_level >= 1:
            retrieved_docs = self.rag_service.search_knowledge(
                request.user_question,
                top_k=3
            )
            
            if retrieved_docs:
                sources = [doc.source for doc in retrieved_docs]
                
                # Format retrieved docs
                docs_text = "\n\n=== RELEVANT DOCUMENTATION ===\n"
                for i, doc in enumerate(retrieved_docs, 1):
                    docs_text += f"\n[Source {i}: {doc.source}]\n"
                    docs_text += f"{doc.content}\n"
                    docs_text += "-" * 80 + "\n"
                
                prompt = prompt.replace(
                    "=== USER QUESTION ===",
                    f"{docs_text}\n\n=== USER QUESTION ==="
                )
        
        # Call LLM
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": request.user_question}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=10.0
            )
            
            message = response.choices[0].message.content
            token_usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
        except Exception as e:
            message = f"Error generating response: {str(e)}"
            token_usage = {}
        
        return TutorResponse(
            message=message,
            hint_level=request.hint_level,
            sources=sources,
            token_usage=token_usage
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
