# AI Tutor System - Design Document

## 1. System Architecture

### 1.1 High-Level Architecture
```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Frontend  │─────▶│   Backend    │─────▶│  LLM API    │
│  (Chat UI)  │◀─────│  (FastAPI)   │◀─────│  (OpenAI)   │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
                            ├─────▶ ┌─────────────┐
                            │       │  Vector DB  │
                            │       │  (ChromaDB) │
                            │       └─────────────┘
                            │
                            ├─────▶ ┌─────────────┐
                            │       │ Kubernetes  │
                            │       │   Client    │
                            │       └─────────────┘
                            │
                            └─────▶ ┌─────────────┐
                                    │  Database   │
                                    │ (Postgres)  │
                                    └─────────────┘
```

### 1.2 Component Breakdown

**Frontend Components:**
- ChatInterface: 사용자 질문 입력 및 AI 응답 표시
- HintLevelSelector: 힌트 단계 선택 버튼
- ContextDisplay: 현재 미션 정보 표시

**Backend Services:**
- ContextCollector: 시스템 상태 수집
- PromptEngine: LLM 프롬프트 생성
- RAGService: 벡터 검색 및 문서 검색
- HintManager: 힌트 레벨 관리
- ConversationLogger: 대화 이력 저장

## 2. Data Models

### 2.1 Database Schema

```python
# Conversation Model
class Conversation(Base):
    id: UUID
    user_id: UUID
    mission_id: UUID
    created_at: datetime
    
# Message Model
class Message(Base):
    id: UUID
    conversation_id: UUID
    role: str  # 'user' | 'assistant' | 'system'
    content: str
    hint_level: int  # 0, 1, 2, 3
    context_snapshot: JSON
    created_at: datetime

# HintHistory Model
class HintHistory(Base):
    id: UUID
    user_id: UUID
    mission_id: UUID
    hint_level: int
    points_deducted: int
    created_at: datetime
```

### 2.2 Context Data Structure

```python
class MissionContext:
    mission_id: str
    mission_name: str
    mission_level: int
    chaos_type: str
    expected_solution: str
    time_elapsed: int
    
class SystemContext:
    namespace: str
    pod_status: List[PodStatus]
    pod_logs: Dict[str, str]
    service_status: List[ServiceStatus]
    recent_events: List[K8sEvent]
    
class UserContext:
    user_id: str
    hint_history: List[HintRecord]
    previous_attempts: int
    skill_level: Dict[str, float]
    
class FullContext:
    mission: MissionContext
    system: SystemContext
    user: UserContext
    timestamp: datetime
```

## 3. Core Algorithms

### 3.1 Context Collection Algorithm

```python
async def collect_context(user_id: str, mission_id: str) -> FullContext:
    """
    Collects all relevant context for AI tutor
    Timeout: 3 seconds
    """
    # Parallel execution for performance
    mission_task = get_mission_info(mission_id)
    system_task = collect_system_state(user_id)
    user_task = get_user_history(user_id, mission_id)
    
    mission_ctx, system_ctx, user_ctx = await asyncio.gather(
        mission_task, system_task, user_task
    )
    
    return FullContext(
        mission=mission_ctx,
        system=system_ctx,
        user=user_ctx,
        timestamp=datetime.now()
    )

async def collect_system_state(user_id: str) -> SystemContext:
    """
    Collects K8s cluster state
    """
    namespace = f"user-{user_id}"
    k8s_client = get_k8s_client()
    
    # Get pod status
    pods = k8s_client.list_namespaced_pod(namespace)
    pod_status = [extract_pod_status(pod) for pod in pods.items]
    
    # Get recent logs (last 50 lines)
    pod_logs = {}
    for pod in pods.items:
        logs = k8s_client.read_namespaced_pod_log(
            pod.metadata.name, namespace, tail_lines=50
        )
        pod_logs[pod.metadata.name] = logs
    
    # Get recent events
    events = k8s_client.list_namespaced_event(namespace)
    recent_events = sorted(events.items, key=lambda e: e.last_timestamp)[-10:]
    
    return SystemContext(
        namespace=namespace,
        pod_status=pod_status,
        pod_logs=pod_logs,
        recent_events=recent_events
    )
```

### 3.2 Prompt Engineering Strategy

```python
class SocraticPromptEngine:
    """
    Generates prompts using Socratic method with 3-level progressive hint system
    """
    
    SYSTEM_PROMPT = """
    You are a Socratic tutor for Kubernetes troubleshooting.
    
    CORE RULES:
    1. Strictly adhere to hint level constraints - never exceed boundaries
    2. Guide through observation and questions, not direct answers
    3. Reference the current system state in your responses
    4. Progressive disclosure - reveal information gradually
    5. Be encouraging and celebrate learning moments
    
    HINT LEVELS:
    - Level 1 (Observational): Ask about observable state, NO answers/causes/commands
    - Level 2 (Conceptual): Explain concepts, point to log lines, NO direct solutions
    - Level 3 (Complete): Provide root cause, exact commands, YAML fixes
    
    Context will be provided in {context} placeholder.
    User question in {user_message} placeholder.
    Current hint level: [Hint_Level]
    """
    
    def generate_prompt(
        self, 
        user_question: str,
        context: FullContext,
        hint_level: int
    ) -> str:
        """
        Generates LLM prompt based on context and hint level (1-3)
        """
        prompt_parts = [
            self.SYSTEM_PROMPT,
            self._format_mission_context(context.mission),
            self._format_system_context(context.system),
            self._format_user_context(context.user),
            self._format_hint_level_instruction(hint_level),
            f"User Question: {user_question}",
            "Your Response:"
        ]
        
        return "\n\n".join(prompt_parts)
    
    def _format_hint_level_instruction(self, level: int) -> str:
        instructions = {
            1: """
            LEVEL 1 - OBSERVATIONAL GUIDANCE:
            - FORBIDDEN: Direct answers, root causes, specific commands
            - ALLOWED: Questions about observable state, general directions
            - Ask what they SEE, not what to DO
            Example: "What does the pod Status show? What patterns do you notice in the Events?"
            """,
            2: """
            LEVEL 2 - CONCEPTUAL + DIAGNOSTIC:
            - FORBIDDEN: Direct solutions, exact fixes
            - ALLOWED: Explain concepts, point to specific log lines, narrow investigation area
            Example: "CrashLoopBackOff means the container exits immediately. Line 7 shows exit code 127. What does that error code typically indicate?"
            """,
            3: """
            LEVEL 3 - COMPLETE SOLUTION:
            - REQUIRED: Root cause statement, exact kubectl commands, YAML snippets
            - Provide step-by-step fix with explanation
            Example: "Root Cause: Image typo 'ngnix' → 'nginx'. Run: kubectl edit deployment myapp. Change line 24: image: nginx:latest. Why: Correct image name resolves ImagePullBackOff."
            """
        }
        return f"[Hint_Level: {level}]\n{instructions[level]}"
```

### 3.3 RAG Implementation

```python
class RAGService:
    """
    Retrieval-Augmented Generation service
    """
    
    def __init__(self):
        self.vectordb = chromadb.Client()
        self.collection = self.vectordb.get_or_create_collection(
            name="k8s_docs",
            embedding_function=OpenAIEmbeddings()
        )
    
    async def search_knowledge(
        self, 
        query: str, 
        top_k: int = 3,
        min_similarity: float = 0.7
    ) -> List[Document]:
        """
        Searches vector DB for relevant documents
        Timeout: 2 seconds
        """
        # Generate query embedding
        query_embedding = await self._embed_query(query)
        
        # Search similar documents
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Filter by similarity threshold
        documents = []
        for doc, distance in zip(results['documents'][0], results['distances'][0]):
            similarity = 1 - distance
            if similarity >= min_similarity:
                documents.append(Document(
                    content=doc,
                    similarity=similarity,
                    source=results['metadatas'][0]['source']
                ))
        
        return documents
    
    async def augment_prompt(
        self, 
        base_prompt: str, 
        user_question: str
    ) -> str:
        """
        Augments prompt with relevant knowledge
        """
        # Search for relevant docs
        docs = await self.search_knowledge(user_question)
        
        if not docs:
            return base_prompt
        
        # Format retrieved knowledge
        knowledge_section = "RELEVANT DOCUMENTATION:\n"
        for i, doc in enumerate(docs, 1):
            knowledge_section += f"\n[Source {i}]: {doc.source}\n"
            knowledge_section += f"{doc.content}\n"
        
        # Insert before user question
        return base_prompt.replace(
            f"User Question: {user_question}",
            f"{knowledge_section}\n\nUser Question: {user_question}"
        )
```

### 3.4 Hint Level Management

```python
class HintManager:
    """
    Manages hint levels and scoring (3-level system)
    """
    
    HINT_PENALTIES = {
        1: 5,   # Level 1: Observational guidance
        2: 10,  # Level 2: Conceptual hints
        3: 50   # Level 3: Complete solution
    }
    
    async def request_hint(
        self,
        user_id: str,
        mission_id: str,
        current_level: int
    ) -> HintResponse:
        """
        Processes hint request and updates score
        Valid levels: 1, 2, 3
        """
        # Increment hint level (max 3)
        new_level = min(current_level + 1, 3)
        
        # Deduct points
        penalty = self.HINT_PENALTIES.get(new_level, 0)
        await self._deduct_points(user_id, mission_id, penalty)
        
        # Log hint usage
        await self._log_hint_usage(user_id, mission_id, new_level, penalty)
        
        return HintResponse(
            hint_level=new_level,
            points_deducted=penalty,
            message=f"Hint level increased to {new_level}. -{penalty} points."
        )
    
    async def auto_escalate_hint(
        self,
        user_id: str,
        mission_id: str,
        conversation_id: str
    ) -> bool:
        """
        Auto-escalates hint level if user is stuck
        Returns True if escalated
        """
        # Count recent failed attempts
        messages = await self._get_recent_messages(conversation_id, limit=6)
        
        # Check if user asked similar questions 3+ times
        if self._detect_repetitive_questions(messages):
            current_level = await self._get_current_hint_level(conversation_id)
            if current_level < 3:
                await self.request_hint(user_id, mission_id, current_level)
                return True
        
        return False
```

## 4. API Endpoints

### 4.1 Chat Endpoints

```python
@router.post("/api/chat/message")
async def send_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Sends user message and gets AI response
    """
    # Collect context
    context = await collect_context(current_user.id, request.mission_id)
    
    # Check for auto-escalation
    await hint_manager.auto_escalate_hint(
        current_user.id, 
        request.mission_id,
        request.conversation_id
    )
    
    # Generate prompt
    prompt = prompt_engine.generate_prompt(
        request.message,
        context,
        request.hint_level
    )
    
    # Augment with RAG if needed
    if request.hint_level >= 1:
        prompt = await rag_service.augment_prompt(prompt, request.message)
    
    # Call LLM
    response = await llm_client.generate(prompt, max_tokens=500)
    
    # Save conversation
    await save_message(request.conversation_id, "user", request.message, context)
    await save_message(request.conversation_id, "assistant", response, context)
    
    return ChatResponse(
        message=response,
        hint_level=request.hint_level,
        context_summary=summarize_context(context)
    )

@router.post("/api/chat/hint")
async def request_hint(
    request: HintRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Requests higher hint level
    """
    result = await hint_manager.request_hint(
        current_user.id,
        request.mission_id,
        request.current_level
    )
    
    return result
```

## 5. Performance Optimizations

### 5.1 Caching Strategy

```python
# Cache mission context (rarely changes)
@cache(ttl=300)  # 5 minutes
async def get_mission_info(mission_id: str) -> MissionContext:
    pass

# Cache user skill level (updated after mission completion)
@cache(ttl=600)  # 10 minutes
async def get_user_skill_level(user_id: str) -> Dict[str, float]:
    pass

# Cache RAG embeddings
@cache(ttl=3600)  # 1 hour
async def embed_query(query: str) -> List[float]:
    pass
```

### 5.2 Rate Limiting

```python
# Limit LLM API calls
@rate_limit(max_calls=10, period=60)  # 10 calls per minute per user
async def generate_ai_response(prompt: str) -> str:
    pass

# Limit hint requests
@rate_limit(max_calls=5, period=300)  # 5 hints per 5 minutes
async def request_hint(user_id: str, mission_id: str) -> HintResponse:
    pass
```

## 6. Error Handling

```python
class AITutorError(Exception):
    pass

class ContextCollectionError(AITutorError):
    """Raised when context collection fails"""
    pass

class LLMAPIError(AITutorError):
    """Raised when LLM API call fails"""
    pass

class RAGSearchError(AITutorError):
    """Raised when vector search fails"""
    pass

# Retry logic for LLM API
@retry(max_attempts=3, backoff=2.0, exceptions=[LLMAPIError])
async def call_llm_api(prompt: str) -> str:
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            timeout=5.0
        )
        return response.choices[0].message.content
    except Exception as e:
        raise LLMAPIError(f"LLM API call failed: {str(e)}")
```

## 7. Testing Strategy

### 7.1 Unit Tests
- Test context collection with mocked K8s client
- Test prompt generation with various hint levels
- Test RAG search with sample embeddings
- Test hint level management logic

### 7.2 Integration Tests
- Test full chat flow with real LLM API
- Test context collection with real K8s cluster
- Test RAG with populated vector DB

### 7.3 Property-Based Tests
- Property: AI response should never contain direct kubectl commands at hint level 0
- Property: Context collection should complete within 3 seconds
- Property: RAG search should only return documents with similarity >= 0.7

## 8. Security Considerations

- API keys stored in environment variables
- User input sanitized before K8s API calls
- Rate limiting to prevent abuse
- Conversation logs exclude sensitive data
- Vector DB access restricted to backend only

## 9. Deployment

### 9.1 Environment Variables
```bash
OPENAI_API_KEY=sk-...
CHROMADB_HOST=localhost
CHROMADB_PORT=8001
DATABASE_URL=postgresql://...
K8S_CONFIG_PATH=/path/to/kubeconfig
```

### 9.2 Dependencies
```
langchain==0.1.0
openai==1.10.0
chromadb==0.4.22
kubernetes==29.0.0
fastapi==0.109.0
```
