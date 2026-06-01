# 📋 향후 작업 계획 (Tasks TODO)

## 🎯 프로젝트 현황

### ✅ 완료된 작업
- [x] **TASK 1**: LLM 통합 (OpenAI API, Prompt Engine)
- [x] **TASK 2**: Vector Database Setup (ChromaDB → Qdrant 마이그레이션)
- [x] **챗봇 UI**: 점수 기반 AI 챗봇 인터페이스 (독립 실행형 HTML)
- [x] **TASK A**: 챗봇 위젯과 Backend API 연동 (2026-06-01 완료)
- [x] **TASK B**: Knowledge Base 확장 (2026-06-01 완료)

### 🚧 진행 중인 작업
- [ ] 통합 테스트 및 검증
- [ ] 프로덕션 배포 준비

---

## 🎉 신규 완료 작업 (2026-06-01)

### ✅ Task A: 챗봇 위젯과 Backend API 연동

**목표**: 독립 실행형 HTML 챗봇을 Backend API와 연결

#### A.1 API 클라이언트 구현 ✅

**파일**: `ai-chatbot-widget/src/api-client.js` (신규 생성)

**구현 내용**:
- ✅ ChatAPIClient 클래스 구현
- ✅ JWT 토큰 인증 처리
- ✅ 재시도 로직 (Exponential Backoff)
- ✅ 에러 처리 (APIError 클래스)
- ✅ CORS 처리

**주요 메서드**:
```javascript
- sendMessage(message, hintLevel) // POST /api/chat
- getMissionStatus()              // GET /api/missions/status
- getMissions()                   // GET /api/missions/
- login(username, password)       // POST /api/auth/login
- getProfile()                    // GET /api/auth/me
- testConnection()                // GET /health
```

**특징**:
- 네트워크 오류 시 자동 재시도 (최대 3회)
- 401/403/404/500 에러 별도 처리
- 타임아웃 및 연결 실패 핸들링

---

#### A.2 챗봇 위젯 HTML 업데이트 ✅

**파일**: `ai-chatbot-widget/demo-standalone.html` (수정)

**구현 내용**:
- ✅ 실제 API 호출 통합
- ✅ 데모 모드 / 실제 API 모드 전환 기능
- ✅ 로딩 상태 UI (타이핑 인디케이터)
- ✅ 에러 메시지 표시
- ✅ 토큰 입력 UI (localStorage 저장)
- ✅ 미션 정보 표시 (현재 미션명, 힌트 레벨)
- ✅ 연결 상태 표시 (설정 패널)

**주요 기능**:
1. **데모 모드 (기본값)**:
   - 시뮬레이션 응답 사용
   - Backend 연결 불필요
   - 로컬에서 즉시 테스트 가능

2. **실제 API 모드**:
   - Backend API와 실시간 통신
   - JWT 토큰 인증
   - 미션 상태 자동 로드
   - 힌트 레벨별 AI 응답 (0~3)

3. **설정 패널**:
   - 데모/실제 API 모드 전환
   - 연결 상태 표시
   - API URL 표시

**사용 방법**:
```bash
# 1. 데모 모드 (기본)
# - 브라우저에서 demo-standalone.html 열기
# - 시뮬레이션 응답으로 즉시 테스트

# 2. 실제 API 모드
# - Backend 서버 실행 (http://localhost:8000)
# - 설정 패널에서 "데모 모드" 체크 해제
# - 로그인 후 JWT 토큰 입력
# - 미션 시작 후 챗봇 사용
```

**Backend API 연동 스펙**:
```javascript
// POST /api/chat
Request: {
  message: string,
  hint_level: number (0~3)
}

Response: {
  response: string,
  hint_level: number,
  mission_name: string (optional)
}

// GET /api/missions/status
Response: {
  attempt: {
    id: string,
    mission_id: string,
    status: string,
    hints_used: number,
    ...
  },
  elapsed_seconds: number,
  remaining_seconds: number,
  current_score: number
}
```

**완료 일시**: 2026-06-01  
**소요 시간**: 약 2시간  
**테스트 상태**: 데모 모드 동작 확인 완료, 실제 API 모드는 Backend 서버 실행 후 테스트 필요

---

## 🎉 신규 완료 작업 (2026-06-01 - Part 2)

### ✅ Task B: Knowledge Base 확장

**목표**: RAG 시스템을 위한 Kubernetes 트러블슈팅 문서 확충

#### B.1 트러블슈팅 문서 추가 ✅

**디렉토리**: `ai-data/knowledge-base/troubleshooting/` (신규 생성)

**작성 완료 문서**:
1. ✅ `crashloopbackoff.md` - CrashLoopBackOff 해결 가이드
   - 원인: 애플리케이션 오류, 설정 문제, 리소스 문제, 의존성 문제
   - 진단: Exit Code 확인, 로그 분석, Events 확인
   - 해결: 로그 분석, 설정 확인, 리소스 조정, Probe 조정
   - 실전 예제 4개 포함

2. ✅ `imagepullbackoff.md` - ImagePullBackOff 해결 가이드
   - 원인: 이미지 이름 오류, 인증 문제, 네트워크 문제, 레지스트리 문제
   - 진단: Events 확인, 이미지 정보 확인, imagePullSecrets 확인
   - 해결: 이미지 이름 수정, Private 레지스트리 인증, Rate Limit 해결
   - Docker Hub, AWS ECR, GCR, Harbor 인증 예제 포함

3. ✅ `pending-pods.md` - Pending Pods 해결 가이드
   - 원인: 리소스 부족, Node Selector 불일치, Taints/Tolerations, PVC 문제
   - 진단: Node 리소스 확인, 레이블 확인, Taint 확인
   - 해결: 리소스 요청 조정, Node 추가, 레이블 관리, PVC 설정
   - 실전 예제 4개 포함

4. ✅ `oomkilled.md` - OOMKilled 해결 가이드
   - 원인: 메모리 제한 부족, 메모리 누수, 트래픽 급증, 비효율적인 코드
   - 진단: Exit Code 137 확인, 메모리 사용량 확인, 메모리 프로파일링
   - 해결: 메모리 제한 증가, 메모리 누수 수정, 코드 최적화, HPA/VPA
   - Node.js, Python 메모리 프로파일링 예제 포함

**문서 특징**:
- 각 문서 평균 300-400줄 (상세한 설명)
- 실전 예제 및 명령어 포함
- 체크리스트 제공
- 디버깅 명령어 모음
- 예방 방법 포함

---

#### B.2 kubectl 명령어 가이드 ✅

**디렉토리**: `ai-data/knowledge-base/commands/` (신규 생성)

**작성 완료 문서**:
1. ✅ `kubectl-basics.md` - kubectl 기본 명령어 가이드
   - 클러스터 정보 및 Context 관리
   - Pod 관리 (조회, 생성, 삭제)
   - Deployment 관리 (생성, 업데이트, 스케일링, 롤백)
   - Service 관리
   - Namespace 관리
   - ConfigMap & Secret 관리
   - 레이블 및 어노테이션
   - 유용한 팁 (출력 형식, 별칭, 자동 완성)
   - 자주 사용하는 명령어 조합

**추가 예정 문서** (향후 작성):
- `kubectl-logs.md` - 로그 조회 및 분석
- `kubectl-describe.md` - 리소스 상세 조회
- `kubectl-debug.md` - 디버깅 명령어

---

#### B.3 Knowledge Base 적재 스크립트 ✅

**파일**: `ai-data/scripts/ingest_knowledge.py` (신규 생성)

**구현 내용**:
```python
# Knowledge Base를 Qdrant에 적재하는 스크립트
# - 문서 로드
# - 청킹
# - 임베딩 생성
# - Qdrant 업로드
# - 검증 및 테스트
```

**주요 기능**:
1. **RAG Service 초기화**
   - In-memory 모드 또는 Qdrant 서버 연결
   - 환경 변수 검증

2. **문서 로드**
   - knowledge-base 디렉토리에서 .md 파일 로드
   - 문서 목록 및 크기 표시

3. **문서 청킹**
   - RecursiveCharacterTextSplitter 사용
   - 청크 통계 표시 (평균, 최소, 최대 크기)

4. **임베딩 생성 및 적재**
   - OpenAI text-embedding-ada-002 사용
   - 진행 상황 표시
   - Qdrant에 업로드

5. **검증**
   - 문서 수 확인
   - 테스트 쿼리 실행
   - 검색 결과 표시

6. **사용자 친화적 출력**
   - 단계별 진행 상황
   - 성공/실패 메시지
   - 요약 및 다음 단계 안내

**사용 방법**:
```bash
# 1. 환경 변수 설정
export OPENAI_API_KEY=your_api_key_here

# 2. Qdrant 서버 실행 (선택사항)
docker run -p 6333:6333 qdrant/qdrant

# 3. 스크립트 실행
cd ai-data
python scripts/ingest_knowledge.py

# 또는 in-memory 모드
QDRANT_USE_MEMORY=true python scripts/ingest_knowledge.py
```

**출력 예시**:
```
================================================================================
  Knowledge Base Ingestion
================================================================================

Configuration:
  Knowledge Base Dir: ./knowledge-base
  OpenAI API Key: ✓ Set
  OpenAI Model: gpt-4

[Step 1] Initializing RAG Service
  Connecting to Qdrant at http://localhost:6333
✓ RAG Service initialized

[Step 2] Checking existing collection
  Collection: k8s_docs
  Existing documents: 0

[Step 3] Loading documents from knowledge base
  Found 5 documents
  Loaded documents:
    - crashloopbackoff.md (15234 chars)
    - imagepullbackoff.md (14567 chars)
    - pending-pods.md (13890 chars)
    - oomkilled.md (16123 chars)
    - kubectl-basics.md (12456 chars)
✓ Loaded 5 documents

[Step 4] Chunking documents
  Chunk size: 1000
  Chunk overlap: 200
  Created 87 chunks
  Chunk statistics:
    Average size: 856 chars
    Min size: 234 chars
    Max size: 1000 chars
✓ Created 87 chunks

[Step 5] Generating embeddings and ingesting into Qdrant
  This may take a few minutes...
  Embedding model: text-embedding-ada-002
  Estimated API calls: 87
✓ Successfully ingested 87 chunks

[Step 6] Verifying ingestion
  Collection: k8s_docs
  Total documents: 87
✓ Document count verified

[Step 7] Testing search functionality
  Running test queries:
  Query: "Pod is in CrashLoopBackOff status"
  Found 2 results:
    1. crashloopbackoff.md (similarity: 0.892)
       Preview: CrashLoopBackOff는 Kubernetes에서 가장 흔하게 발생하는 Pod 오류 중 하나입니다...
    2. oomkilled.md (similarity: 0.756)
       Preview: OOMKilled는 컨테이너가 할당된 메모리 제한을 초과하여...
✓ Search functionality verified

================================================================================
  Ingestion Complete!
================================================================================

Summary:
  ✓ Documents loaded: 5
  ✓ Chunks created: 87
  ✓ Chunks ingested: 87
  ✓ Collection: k8s_docs
  ✓ Total documents in DB: 87

Next steps:
  1. Test the AI Tutor Engine:
     python ai_engine.py
  2. Start the Backend API:
     cd ../backend && uvicorn app.main:app --reload
  3. Use the chatbot widget:
     open ../ai-chatbot-widget/demo-standalone.html
```

---

**완료 일시**: 2026-06-01  
**소요 시간**: 약 3시간  
**테스트 상태**: 스크립트 작성 완료, 실제 적재는 OpenAI API 키 설정 후 실행 필요

**통계**:
- 트러블슈팅 문서: 4개 (약 1,200줄)
- kubectl 가이드: 1개 (약 400줄)
- 적재 스크립트: 1개 (약 250줄)
- 총 라인 수: 약 1,850줄

---

## 📌 우선순위별 작업 목록

---

## 🔴 우선순위 1: 핵심 기능 완성 (필수)

### Task 3: Backend API 개발

**목표**: AI 챗봇을 위한 RESTful API 엔드포인트 구현

#### 3.1 AI Chat API 엔드포인트 생성

**파일**: `backend/app/api/chat.py` (신규)

**구현 내용**:
```python
# POST /api/chat
# - 사용자 질문 수신
# - 힌트 레벨 처리
# - AI 응답 생성
# - 점수 계산

# GET /api/chat/history/{session_id}
# - 대화 히스토리 조회

# POST /api/chat/reset
# - 세션 초기화
```

**요구사항**:
- [ ] LLM Client 통합 (`ai-data/llm_client.py`)
- [ ] Prompt Engine 통합 (`ai-data/prompt_engine.py`)
- [ ] RAG Service 통합 (`ai-data/rag_service.py`)
- [ ] 세션 관리 (Redis 또는 DB)
- [ ] 점수 계산 로직 (100점 만점, 차등 차감)
- [ ] 에러 처리 및 로깅

**API 스펙**:
```json
// POST /api/chat
{
  "message": "Pod가 CrashLoopBackOff 상태입니다",
  "session_id": "optional-uuid",
  "question_count": 0
}

// Response
{
  "response": "AI 응답 내용",
  "session_id": "uuid",
  "question_count": 1,
  "score_deducted": 5,
  "current_score": 95,
  "suggestions": ["kubectl logs", "kubectl describe"]
}
```

**예상 소요 시간**: 2-3일

---

#### 3.2 점수 시스템 구현

**파일**: `backend/app/services/scoring_service.py` (신규)

**구현 내용**:
```python
class ScoringService:
    def calculate_score(question_count: int) -> dict:
        # 질문 횟수별 점수 차감
        # 1회: -5점, 2회: -10점, 3회: -20점, 4회+: -40점
        pass
    
    def get_penalty(question_count: int) -> int:
        # 다음 질문 시 차감될 점수 반환
        pass
    
    def show_answer_penalty() -> int:
        # 답 보기 사용 시 0점 처리
        return 0
```

**요구사항**:
- [ ] 점수 계산 로직
- [ ] 질문 횟수 추적
- [ ] 답 보기 처리
- [ ] 점수 히스토리 저장

**예상 소요 시간**: 1일

---

#### 3.3 세션 관리

**파일**: `backend/app/services/session_service.py` (신규)

**구현 내용**:
```python
class SessionService:
    def create_session(user_id: str) -> str:
        # 새 세션 생성
        pass
    
    def get_session(session_id: str) -> Session:
        # 세션 조회
        pass
    
    def update_session(session_id: str, data: dict):
        # 세션 업데이트 (점수, 질문 횟수 등)
        pass
    
    def get_chat_history(session_id: str) -> list:
        # 대화 히스토리 조회
        pass
```

**요구사항**:
- [ ] 세션 생성 및 관리
- [ ] 대화 히스토리 저장
- [ ] 세션 만료 처리 (TTL)
- [ ] Redis 또는 PostgreSQL 사용

**예상 소요 시간**: 1-2일

---

### Task 4: AI 엔진 통합

**목표**: Backend API와 AI 엔진 (LLM, RAG) 연동

#### 4.1 RAG 기반 응답 생성

**파일**: `backend/app/services/ai_service.py` (신규)

**구현 내용**:
```python
class AIService:
    def __init__(self):
        self.llm_client = LLMClient()
        self.prompt_engine = PromptEngine()
        self.rag_service = RAGService()
    
    def generate_response(
        self,
        user_message: str,
        question_count: int,
        chat_history: list
    ) -> str:
        # 1. RAG로 관련 문서 검색
        # 2. Prompt 생성 (질문 횟수 기반)
        # 3. LLM 호출
        # 4. 응답 반환
        pass
```

**요구사항**:
- [ ] RAG Service 초기화 및 연동
- [ ] 질문 횟수별 프롬프트 전략
- [ ] 대화 컨텍스트 관리
- [ ] 스트리밍 응답 지원 (선택사항)

**예상 소요 시간**: 2-3일

---

#### 4.2 Knowledge Base 구축

**파일**: `ai-data/knowledge-base/` (디렉토리)

**구현 내용**:
- Kubernetes 트러블슈팅 문서 수집
- Markdown 형식으로 정리
- RAG Service에 적재

**문서 카테고리**:
```
knowledge-base/
├── troubleshooting/
│   ├── crashloopbackoff.md
│   ├── imagepullbackoff.md
│   ├── pending-pods.md
│   └── oomkilled.md
├── commands/
│   ├── kubectl-basics.md
│   ├── kubectl-logs.md
│   └── kubectl-describe.md
├── concepts/
│   ├── pod-lifecycle.md
│   ├── deployments.md
│   └── services.md
└── best-practices/
    ├── resource-limits.md
    └── health-checks.md
```

**요구사항**:
- [ ] 최소 20개 이상의 문서 작성
- [ ] 실제 트러블슈팅 시나리오 포함
- [ ] 명령어 예제 포함
- [ ] RAG Service에 적재 스크립트 작성

**예상 소요 시간**: 3-4일

---

### Task 5: 챗봇 UI와 Backend 연동

**목표**: 독립 실행형 HTML 챗봇을 Backend API와 연결

#### 5.1 API 클라이언트 구현

**파일**: `ai-chatbot-widget/src/services/api.js` (신규)

**구현 내용**:
```javascript
class ChatAPI {
  constructor(baseURL) {
    this.baseURL = baseURL;
  }
  
  async sendMessage(message, sessionId, questionCount) {
    // POST /api/chat
  }
  
  async getChatHistory(sessionId) {
    // GET /api/chat/history/{session_id}
  }
  
  async resetSession(sessionId) {
    // POST /api/chat/reset
  }
  
  async showAnswer(sessionId) {
    // POST /api/chat/answer
  }
}
```

**요구사항**:
- [ ] Axios 또는 Fetch API 사용
- [ ] 에러 처리
- [ ] 재시도 로직
- [ ] 타임아웃 설정

**예상 소요 시간**: 1일

---

#### 5.2 챗봇 UI 업데이트

**파일**: `ai-chatbot-widget/demo-standalone.html` (수정)

**구현 내용**:
- 시뮬레이션 응답 제거
- 실제 API 호출로 교체
- 로딩 상태 처리
- 에러 메시지 표시

**요구사항**:
- [ ] API 연동
- [ ] 세션 ID 관리
- [ ] 로딩 인디케이터
- [ ] 에러 핸들링
- [ ] 재연결 로직

**예상 소요 시간**: 1-2일

---

#### 5.3 React 버전 챗봇 구현 (선택사항)

**파일**: `ai-chatbot-widget/src/` (React 프로젝트)

**구현 내용**:
- React 컴포넌트 구조
- 상태 관리 (Context API 또는 Redux)
- API 통합
- iframe 임베딩 지원

**요구사항**:
- [ ] React 18 사용
- [ ] TypeScript (선택사항)
- [ ] 컴포넌트 분리
- [ ] 환경 변수 관리

**예상 소요 시간**: 3-4일

---

## 🟡 우선순위 2: 기능 개선 (중요)

### Task 6: 미션 시스템 통합

**목표**: 챗봇을 미션 시스템과 연동

#### 6.1 미션 API 연동

**파일**: `backend/app/api/missions.py` (수정)

**구현 내용**:
```python
# POST /api/missions/{mission_id}/start
# - 미션 시작 시 챗봇 세션 생성
# - 초기 점수 100점 설정

# POST /api/missions/{mission_id}/complete
# - 미션 완료 시 최종 점수 계산
# - 힌트 사용 횟수 기록
```

**요구사항**:
- [ ] 미션과 챗봇 세션 연결
- [ ] 점수 계산 및 저장
- [ ] 미션 완료 조건 검증

**예상 소요 시간**: 2일

---

#### 6.2 점수 및 통계

**파일**: `backend/app/api/stats.py` (신규)

**구현 내용**:
```python
# GET /api/stats/user/{user_id}
# - 사용자 통계 조회
# - 평균 점수, 힌트 사용 횟수 등

# GET /api/stats/leaderboard
# - 리더보드 조회
```

**요구사항**:
- [ ] 사용자별 통계 집계
- [ ] 리더보드 구현
- [ ] 캐싱 (Redis)

**예상 소요 시간**: 2일

---

### Task 7: 프로덕션 배포 준비

**목표**: 프로덕션 환경 설정 및 배포

#### 7.1 Qdrant 서버 설정

**파일**: `infra/qdrant/` (디렉토리)

**구현 내용**:
- Docker Compose 설정
- 볼륨 마운트 설정
- 백업 스크립트

**요구사항**:
- [ ] Qdrant 서버 Docker 설정
- [ ] 데이터 영속성 보장
- [ ] 백업 자동화
- [ ] 모니터링 설정

**예상 소요 시간**: 1-2일

---

#### 7.2 환경 변수 관리

**파일**: `.env.production`, `docker-compose.prod.yml`

**구현 내용**:
```env
# Production 환경 변수
OPENAI_API_KEY=
QDRANT_URL=
DATABASE_URL=
REDIS_URL=
CORS_ORIGINS=
```

**요구사항**:
- [ ] 환경별 설정 분리
- [ ] 시크릿 관리 (AWS Secrets Manager 등)
- [ ] CORS 설정

**예상 소요 시간**: 1일

---

#### 7.3 CI/CD 파이프라인

**파일**: `.github/workflows/` (디렉토리)

**구현 내용**:
- GitHub Actions 워크플로우
- 자동 테스트
- 자동 배포

**요구사항**:
- [ ] 테스트 자동화
- [ ] 린트 및 포맷 체크
- [ ] Docker 이미지 빌드
- [ ] 배포 자동화

**예상 소요 시간**: 2-3일

---

## 🟢 우선순위 3: 추가 기능 (선택사항)

### Task 8: 고급 기능

#### 8.1 스트리밍 응답

**목표**: 실시간 스트리밍 응답 구현

**구현 내용**:
- Server-Sent Events (SSE) 또는 WebSocket
- 토큰 단위 스트리밍
- 프론트엔드 스트리밍 처리

**예상 소요 시간**: 2-3일

---

#### 8.2 다국어 지원

**목표**: 한국어/영어 지원

**구현 내용**:
- i18n 라이브러리 통합
- 번역 파일 작성
- 언어 전환 UI

**예상 소요 시간**: 2일

---

#### 8.3 음성 입력/출력

**목표**: 음성 인터페이스 추가

**구현 내용**:
- Web Speech API
- 음성 인식 (STT)
- 음성 합성 (TTS)

**예상 소요 시간**: 3-4일

---

#### 8.4 코드 하이라이팅

**목표**: kubectl 명령어 및 YAML 하이라이팅

**구현 내용**:
- Prism.js 또는 Highlight.js
- Markdown 렌더링
- 코드 복사 버튼

**예상 소요 시간**: 1일

---

#### 8.5 대화 내보내기

**목표**: 대화 히스토리 내보내기

**구현 내용**:
- PDF 내보내기
- Markdown 내보내기
- 이메일 전송

**예상 소요 시간**: 2일

---

## 📊 전체 일정 예상

### Phase 1: 핵심 기능 (2-3주)
- Task 3: Backend API 개발 (1주)
- Task 4: AI 엔진 통합 (1주)
- Task 5: 챗봇 UI 연동 (1주)

### Phase 2: 기능 개선 (1-2주)
- Task 6: 미션 시스템 통합 (3-4일)
- Task 7: 프로덕션 배포 준비 (4-5일)

### Phase 3: 추가 기능 (선택사항, 2-3주)
- Task 8: 고급 기능 (필요에 따라)

**총 예상 기간**: 4-8주

---

## 🔧 기술 스택 요약

### Backend
- **Framework**: FastAPI
- **Database**: PostgreSQL
- **Cache**: Redis
- **Vector DB**: Qdrant
- **LLM**: OpenAI GPT-4

### Frontend
- **UI**: HTML/CSS/JavaScript (현재)
- **Framework**: React (향후)
- **HTTP Client**: Axios
- **Build Tool**: Vite

### Infrastructure
- **Container**: Docker
- **Orchestration**: Docker Compose
- **CI/CD**: GitHub Actions
- **Monitoring**: Prometheus + Grafana (선택사항)

---

## 📝 다음 단계 (즉시 시작 가능)

### 1. Backend API 개발 시작
```bash
# 1. API 엔드포인트 파일 생성
touch backend/app/api/chat.py

# 2. 서비스 레이어 생성
mkdir -p backend/app/services
touch backend/app/services/ai_service.py
touch backend/app/services/scoring_service.py
touch backend/app/services/session_service.py

# 3. 스키마 정의
# backend/app/schemas.py에 추가
```

### 2. Knowledge Base 구축
```bash
# 1. 디렉토리 생성
mkdir -p ai-data/knowledge-base/{troubleshooting,commands,concepts,best-practices}

# 2. 첫 번째 문서 작성
touch ai-data/knowledge-base/troubleshooting/crashloopbackoff.md

# 3. 문서 작성 후 RAG에 적재
python ai-data/scripts/ingest_knowledge.py
```

### 3. Qdrant 서버 실행
```bash
# Docker로 Qdrant 실행
docker run -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage:z \
  qdrant/qdrant
```

---

## 📚 참고 문서

- [TASK1_COMPLETE.md](./ai-data/TASK1_COMPLETE.md) - LLM 통합 완료
- [TASK2_COMPLETE.md](./ai-data/TASK2_COMPLETE.md) - RAG 시스템 완료
- [QDRANT_MIGRATION.md](./ai-data/QDRANT_MIGRATION.md) - Qdrant 마이그레이션
- [DEVELOPMENT_SUMMARY.md](./DEVELOPMENT_SUMMARY.md) - 전체 개발 요약
- [PR_AI_FEATURES.md](./PR_AI_FEATURES.md) - AI 기능 PR
- [PR_QDRANT_MIGRATION.md](./PR_QDRANT_MIGRATION.md) - Qdrant 마이그레이션 PR

---

## 💬 질문 및 지원

작업 중 질문이나 도움이 필요하면:
1. 각 Task의 상세 구현 가이드 요청
2. 코드 예제 요청
3. 아키텍처 설계 논의

**작성일**: 2026-05-29  
**최종 업데이트**: 2026-05-29  
**버전**: 1.0.0
