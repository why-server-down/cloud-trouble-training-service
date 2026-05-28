# AI Tutor System - Socratic Method Implementation

소크라테스식 대화법을 활용한 Kubernetes 트러블슈팅 AI 튜터 시스템입니다.

## 📋 요약

LLM 기반 AI 튜터 시스템을 구현했습니다. 4단계 힌트 레벨 시스템으로 학생의 자기주도 학습을 유도하며, OpenAI API 연동, 프롬프트 엔진, 컨텍스트 관리 기능을 포함합니다.

## ✨ 주요 변경사항

### 1. LLM 통합 (Task 1 완료)

**OpenAI API 연동**
- LLM 클라이언트 래퍼 구현 (`llm_client.py`)
- 재시도 로직 및 에러 핸들링
- 토큰 사용량 추적
- Rate limit 및 Connection 에러 자동 복구

**환경 설정**
- `.env` 파일 기반 설정 관리
- OpenAI API 키, 모델, 온도 등 설정 가능
- 개발/프로덕션 환경 분리

### 2. 소크라테스식 프롬프트 엔진

**4단계 힌트 레벨 시스템**
- Level 0: 일반적 방향 제시 (명령어 금지)
- Level 1: 구체적 조사 영역 제시
- Level 2: 정확한 kubectl 명령어 제공
- Level 3: 완전한 해결책 단계별 제공

**컨텍스트 통합**
- Mission Context: 미션 정보, 난이도, 예상 해결책
- System Context: Pod 상태, 로그, 이벤트
- User Context: 사용자 ID, 힌트 사용 횟수, 질문 히스토리

**동적 프롬프트 생성**
- 시스템 프롬프트 템플릿 로딩
- 힌트 레벨별 가이드라인 적용
- 컨텍스트 정보 자동 포맷팅

### 3. 테스트 환경 구축

**테스트 파일 정리**
- `tests/` 폴더로 모든 테스트 파일 이동
- Import 경로 자동 수정
- 테스트 가이드 문서 추가

**다양한 테스트 도구**
- 단위 테스트 (config, LLM client)
- 통합 테스트 (전체 시스템)
- 데모 스크립트 (오프라인/온라인)

### 4. RAG 시스템 준비 (Phase 2 대비)

**문서 관리**
- Knowledge base 구조 설계
- 문서 로더 및 청킹 전략
- Vector DB 연동 준비 (ChromaDB)

## 🔧 기술 세부사항

### 프로젝트 구조

```
ai-data/
├── knowledge-base/              # 지식 베이스 문서
│   ├── k8s_troubleshooting_guide.md
│   └── survival_camp_playbook.md
├── prompts/                     # 프롬프트 템플릿
│   └── socratic_tutor.md        # 소크라테스식 튜터 시스템 프롬프트
├── tests/                       # 테스트 및 데모 (신규)
│   ├── README.md                # 테스트 가이드
│   ├── test_task1.py            # Task 1 완전 테스트
│   ├── test_basic.py            # 기본 기능 테스트
│   ├── test_rag.py              # RAG 시스템 테스트
│   ├── test_simple.py           # 간단한 테스트
│   ├── chat_demo.py             # 실제 AI 채팅 데모
│   ├── chat_demo_offline.py    # 오프라인 프롬프트 데모
│   ├── simple_chat_test.py     # 시뮬레이션 응답 데모
│   └── test_ai_chat.py          # AI 응답 예시
├── vector-db/                   # ChromaDB 저장소
│   └── chroma_data/
├── config.py                    # 설정 관리 (신규)
├── llm_client.py                # LLM 클라이언트 래퍼 (신규)
├── prompt_engine.py             # 프롬프트 생성 엔진 (신규)
├── rag_service.py               # RAG 서비스
├── ai_engine.py                 # 메인 AI 엔진
├── requirements.txt             # Python 의존성
├── .env                         # 환경 변수 (gitignore)
├── .env.example                 # 환경 변수 템플릿
├── TASK1_COMPLETE.md            # Task 1 완료 보고서 (신규)
└── README.md                    # 이 파일
```

## 🚀 빠른 시작

### 1. 환경 설정

```bash
cd ai-data

# Python 가상환경 생성 (권장)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일을 열어서 OPENAI_API_KEY 설정
```

### 2. OpenAI API 키 설정

`.env` 파일에 API 키 추가:
```env
OPENAI_API_KEY=sk-your-actual-api-key-here
OPENAI_MODEL=gpt-4
OPENAI_TEMPERATURE=0.7
OPENAI_MAX_TOKENS=500
```

### 3. 테스트 실행

```bash
# Task 1 완전 테스트 (LLM 통합)
python tests/test_task1.py

# 간단한 기능 테스트 (API 키 불필요)
python tests/test_simple.py

# AI 채팅 데모 (API 키 필요)
python tests/chat_demo.py
```

## 사용법

### 1. Knowledge Base 초기화

```python
from ai_engine import AITutorEngine

# AI 엔진 초기화
engine = AITutorEngine(use_rag=True)

# 지식 베이스 로드 (최초 1회)
engine.initialize_knowledge_base()
```

### 2. AI 튜터 사용

```python
from ai_engine import TutorRequest, MissionContext, SystemContext, UserContext

# 컨텍스트 준비
mission = MissionContext(
    mission_id="m1",
    mission_name="ImagePullBackOff Challenge",
    mission_level=1,
    chaos_type="image_pull_error",
    expected_solution="Fix image name"
)

system = SystemContext(
    namespace="user-123",
    pod_status="ImagePullBackOff",
    pod_logs="Error: Failed to pull image",
    recent_events="Image pull failed"
)

user = UserContext(
    user_id="user-123",
    hint_count=0,
    previous_questions=[]
)

# 요청 생성
request = TutorRequest(
    user_question="My pod is not starting. What should I check?",
    hint_level=0,  # 0: 방향 제시, 1: 구체적, 2: 명령어, 3: 정답
    mission_ctx=mission,
    system_ctx=system,
    user_ctx=user
)

# 응답 받기
response = engine.get_response(request)
print(response.message)
```

### 3. 독립 실행 테스트

각 모듈을 독립적으로 테스트할 수 있습니다:

```bash
# RAG 서비스 테스트
python rag_service.py

# 프롬프트 엔진 테스트
python prompt_engine.py

# 전체 AI 엔진 테스트
python ai_engine.py
```

## 🎯 구현된 기능

### LLM Client (`llm_client.py`)
- ✅ OpenAI API 통합
- ✅ 재시도 로직 (Rate limit, Connection error)
- ✅ 지수 백오프 (Exponential backoff)
- ✅ 토큰 사용량 추적
- ✅ 응답 시간 측정
- ✅ 에러 핸들링 및 타임아웃

### Prompt Engine (`prompt_engine.py`)
- ✅ 소크라테스식 시스템 프롬프트
- ✅ 4단계 힌트 레벨 시스템
- ✅ 동적 프롬프트 생성
- ✅ 컨텍스트 통합 (Mission, System, User)
- ✅ 템플릿 기반 프롬프트 로딩

### Configuration (`config.py`)
- ✅ 환경 변수 관리
- ✅ 설정 검증
- ✅ 기본값 설정
- ✅ 개발/프로덕션 환경 분리

### RAG Service (`rag_service.py`) - Task 2 완료 ✅
- ✅ 문서 로딩 (Markdown)
- ✅ 청킹 (코드 블록 보존)
- ✅ 임베딩 생성 (OpenAI)
- ✅ 벡터 저장 (ChromaDB)
- ✅ 의미 기반 검색
- ✅ 에러 핸들링 및 재시도 로직

### AI Engine (`ai_engine.py`) - Phase 3 준비
- ⏳ RAG + Prompt + LLM 통합
- ⏳ 응답 생성 파이프라인
- ⏳ 소스 추적

## 💡 힌트 레벨 시스템

AI 튜터는 4단계 힌트 레벨로 학생의 학습을 지원합니다:

### Level 0: 일반적 방향 제시
- 명령어나 구체적 리소스명 금지
- 질문을 통한 사고 유도
- 예시: "Pod의 상태를 확인하면 어떤 정보를 얻을 수 있을까요?"

### Level 1: 구체적 조사 영역
- 확인해야 할 리소스나 영역 제시
- 명령어 타입 제안 (정확한 문법 제외)
- 예시: "Pod의 이벤트를 확인해보세요. 어떤 에러가 보이나요?"

### Level 2: 정확한 명령어
- 실행할 kubectl 명령어 제공
- 출력에서 찾아야 할 정보 설명
- 예시: "`kubectl describe pod <pod-name>` 실행 후 Events 섹션을 확인하세요"

### Level 3: 완전한 해결책
- 단계별 해결 방법 제공
- 정확한 명령어와 YAML 수정 포함
- 각 단계의 이유 설명
- 예시: "이미지 이름 오타를 수정하세요: `kubectl edit deployment` 실행 후 'ngnix'를 'nginx'로 변경"

### 점수 패널티
- Level 1: -5점
- Level 2: -10점
- Level 3: -50점

## Backend 연동 스키마

Backend에서 이 AI 엔진을 호출할 때 필요한 데이터 형식:

```json
{
  "user_question": "My pod is not starting",
  "hint_level": 0,
  "mission": {
    "mission_id": "m1",
    "mission_name": "ImagePullBackOff Challenge",
    "mission_level": 1,
    "chaos_type": "image_pull_error",
    "expected_solution": "Fix image name"
  },
  "system": {
    "namespace": "user-123",
    "pod_status": "ImagePullBackOff",
    "pod_logs": "Error: Failed to pull image...",
    "recent_events": "Image pull failed..."
  },
  "user": {
    "user_id": "user-123",
    "hint_count": 0,
    "previous_questions": []
  }
}
```

## ⚡ 성능

### 현재 성능 (Phase 1)
- LLM 응답 생성: ~2-4초
- 프롬프트 생성: <100ms
- 총 응답 시간: ~2-4초

### 예상 성능 (Phase 2 이후)
- 문서 검색 (RAG): ~1-2초
- LLM 응답 생성: ~2-4초
- 총 응답 시간: ~3-6초

### 최적화 계획
- 프롬프트 캐싱
- 응답 스트리밍
- 벡터 검색 최적화

## 🧪 테스트 방법

### 자동 테스트

```bash
# Task 1 완전 테스트 (모든 서브태스크)
python tests/test_task1.py

# 출력 예시:
# ✓ Task 1.1: PASS (OpenAI SDK 설치)
# ✓ Task 1.2: PASS (API 키 설정)
# ✓ Task 1.3: PASS (LLM 클라이언트)
# ✓ Task 1.4: PASS (API 연결)
# ✓ Task 1.5: PASS (재시도 로직)
```

### 인터랙티브 데모

```bash
# 실제 AI와 채팅 (API 키 필요)
python tests/chat_demo.py

# 명령어:
# /hint     - 힌트 레벨 증가
# /reset    - 힌트 레벨 초기화
# /status   - 현재 상태 확인
# /quit     - 종료
```

### 오프라인 데모 (API 키 불필요)

```bash
# 프롬프트 생성 확인
python tests/chat_demo_offline.py

# 시뮬레이션 응답 확인
python tests/simple_chat_test.py
```

## 📊 테스트 결과

### Task 1: LLM 통합 ✅

- ✅ 1.1: OpenAI SDK 및 LangChain 설치
- ✅ 1.2: API 키 설정 및 환경 변수 관리
- ✅ 1.3: LLM 클라이언트 래퍼 구현
- ✅ 1.4: API 연결 테스트
- ✅ 1.5: 재시도 로직 및 에러 핸들링

### Task 2: Vector Database Setup ✅

- ✅ 2.1: ChromaDB 설치
- ✅ 2.2: ChromaDB 클라이언트 설정
- ✅ 2.3: K8s 문서 컬렉션 생성
- ✅ 2.4: 벡터 저장 테스트
- ✅ 2.5: 에러 핸들링 추가

**Note**: Python 3.14 호환성 문제로 인해 Python 3.11 또는 3.12 사용 권장

### 프롬프트 엔진 ✅

- ✅ 4단계 힌트 레벨 구현
- ✅ 동적 프롬프트 생성
- ✅ 컨텍스트 통합
- ✅ 템플릿 로딩

### 테스트 커버리지 ✅

- ✅ 단위 테스트 (config, LLM client, RAG service)
- ✅ 통합 테스트 (prompt engine)
- ✅ 데모 스크립트 (온라인/오프라인)
- ✅ 문서화 (README, 테스트 가이드, Task 완료 보고서)

**Last Updated**: 2024-02-20  
**Status**: Phase 1-2 완료 (LLM 통합 + Vector DB Setup) ✅  
**Next**: Phase 2 통합 (RAG + Prompt Augmentation)
