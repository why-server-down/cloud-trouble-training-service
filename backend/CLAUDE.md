# Backend - K8s Survival Camp

## 개요
FastAPI 기반 백엔드. 웹 터미널, AI 튜터, 게임 로직, 채점 시스템 담당.

## 기술 스택
- Python 3.11, FastAPI, Pydantic v2
- SQLAlchemy async + PostgreSQL (asyncpg)
- JWT 인증 (python-jose, passlib)
- LangChain + ChromaDB (RAG)
- Kubernetes Python Client
- WebSocket (실시간 터미널)

## 프로젝트 구조
```
app/
├── main.py              # FastAPI 앱, 라우터 등록
├── models.py            # SQLAlchemy 모델 (User, TerminalSession, CommandLog, Mission, MissionAttempt)
├── schemas.py           # Pydantic 스키마 (요청/응답)
├── api/
│   ├── deps.py          # 의존성 (get_db, get_current_user)
│   ├── auth.py          # POST /api/auth/register, /api/auth/login
│   ├── terminal.py      # WS /ws/terminal/{session_id}, POST /api/terminal/sessions
│   └── missions.py      # 미션 CRUD API (목록/시작/상태/확인/포기/힌트)
├── core/
│   ├── config.py        # Settings (환경변수, 미션 시스템 설정)
│   ├── database.py      # async engine, session
│   └── security.py      # JWT, 비밀번호 해싱
├── services/
│   ├── command_validator.py   # kubectl 명령어 검증
│   ├── command_executor.py    # kubectl 비동기 실행
│   ├── websocket_handler.py   # WebSocket 연결
│   ├── mission_service.py     # 미션 오케스트레이터 (시작/완료/포기/점수)
│   ├── chaos_injector.py      # 장애 주입 (ABC + Mock 구현)
│   ├── validation_service.py  # 해결 검증 (ABC + Mock 구현)
│   ├── scoring_service.py     # 점수 계산 (시간/힌트 감점)
│   ├── service_factory.py     # 환경변수 기반 서비스 팩토리
│   └── seed_data.py           # 미션 초기 데이터 (4개 레벨)
└── ai/
    ├── __init__.py
    └── tutor_service.py      # AI 튜터 어댑터 (ai-data 연동, Mock/OpenAI 전환)
```

## API 엔드포인트

### 인증
- `POST /api/auth/register` - 회원가입
- `POST /api/auth/login` - 로그인 (JWT 발급, form-data 형식)

### 터미널
- `POST /api/terminal/sessions` - 터미널 세션 생성
- `WS /ws/terminal/{session_id}?token=JWT` - 웹 터미널

### 미션
- `GET /api/missions/` - 미션 목록 (잠금 상태 포함)
- `POST /api/missions/start` - 미션 시작
- `GET /api/missions/status` - 진행 중 미션 상태
- `POST /api/missions/check` - 해결 여부 확인
- `POST /api/missions/abandon` - 미션 포기
- `POST /api/missions/hint` - 힌트 사용
- `POST /api/missions/debug/resolve` - (Mock 전용) 수동 해결

### AI 튜터
- `POST /api/chat/` - AI 튜터에게 질문 (소크라테스식 힌트)
  - Request: `{ "message": str, "hint_level": 0~3 }`
  - Response: `{ "response": str, "hint_level": int, "mission_name": str }`
  - 진행 중인 미션이 있어야 사용 가능

## 미션 시스템 아키텍처
- Mock 패턴: Docker 환경에서는 MockChaosInjector, MockValidationService 사용
- 환경변수 `CHAOS_BACKEND=mock|chaos_mesh`, `VALIDATION_BACKEND=mock|prometheus`로 전환
- K8s 이전 시 실제 구현체만 추가하면 코드 변경 없이 동작

## AI 튜터 아키텍처
- `ai-data/` 모듈을 sys.path로 동적 import (별도 패키지 설치 불필요)
- `AI_BACKEND=mock`: OpenAI 없이 고정 힌트 반환 (개발용)
- `AI_BACKEND=openai`: ai-data의 AITutorEngine + RAG + GPT 사용
- 힌트 레벨 0~3: 방향제시 → 리소스지목 → kubectl 명령어 → 전체 해결
- 대화 히스토리: attempt_id 기준 인메모리 저장 (최근 5개 질문)

## 컨벤션
- PEP8 준수, 타입 힌트 필수
- Pydantic 모델로 요청/응답 정의
- 환경 변수는 .env + pydantic-settings
- 비동기 우선 (async/await)

## 실행
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 의존 서비스
- PostgreSQL: localhost:5432 (k8s_survival DB)
- ChromaDB: localhost:8001 (벡터 DB)
- Prometheus: localhost:9090 (메트릭)

## 테스트
```bash
cd backend
python -m pytest tests/ -v
```
