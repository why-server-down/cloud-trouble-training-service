# Backend - K8s Survival Camp

## 개요
FastAPI 기반 백엔드. 웹 터미널, AI 튜터, 게임 로직, 채점 시스템, AI 시나리오 생성 담당.

## 기술 스택
- Python 3.11, FastAPI, Pydantic v2
- SQLAlchemy async + PostgreSQL (asyncpg)
- JWT 인증 (python-jose, passlib)
- LangChain + Qdrant (RAG)
- Kubernetes Python Client
- WebSocket (실시간 터미널)
- OpenAI gpt-4o-mini (시나리오 생성 + 튜터)

## 프로젝트 구조
```
app/
├── main.py              # FastAPI 앱, 라우터 등록
├── models.py            # SQLAlchemy 모델
│                        #   User, TerminalSession, CommandLog
│                        #   Mission, MissionAttempt (attempt_type 필드 추가 예정)
│                        #   GeneratedScenario, ValidationRule, TutorMessage (예정)
├── schemas.py           # Pydantic 스키마 (요청/응답)
├── api/
│   ├── deps.py          # 의존성 (get_db, get_current_user)
│   ├── auth.py          # POST /api/auth/register, /api/auth/login
│   ├── terminal.py      # WS /ws/terminal/{session_id}, POST /api/terminal/sessions
│   ├── missions.py      # 고정 4개 미션 API (목록/시작/상태/확인/포기/힌트)
│   ├── scenarios.py     # AI 시나리오 API (예정)
│   ├── dashboard.py     # 대시보드/리더보드/업적 API
│   └── chat.py          # AI 튜터 채팅 API
├── core/
│   ├── config.py        # Settings (환경변수, 미션 시스템 설정)
│   ├── database.py      # async engine, session
│   ├── metrics.py       # Prometheus 메트릭
│   └── security.py      # JWT, 비밀번호 해싱
├── services/
│   ├── command_validator.py   # kubectl 명령어 검증
│   ├── command_executor.py    # kubectl 비동기 실행
│   ├── websocket_handler.py   # WebSocket 연결
│   ├── mission_service.py     # 고정 미션 오케스트레이터
│   ├── chaos_injector.py      # 장애 주입 (Mock | ChaosMesh)
│   │                          #   inject_plan() 추가 예정
│   ├── chaos_plan.py          # ChaosPlan, ChaosPlanCompiler (예정)
│   ├── validation_service.py  # 해결 검증 (Mock | K8s API | Prometheus)
│   ├── validation_rule_service.py  # AI 생성 검증 조건 저장/실행 (예정)
│   ├── promql_guard.py        # PromQL 안전성 검사 (예정)
│   ├── scenario_service.py    # AI 시나리오 생성/시작/완료 오케스트레이터 (예정)
│   ├── runtime_context.py     # K8s/Prometheus/Loki/명령 이력 수집 (예정)
│   ├── scoring_service.py     # 점수 계산 (시간/힌트 감점)
│   ├── analytics_service.py   # 대시보드/리더보드/업적/티어 계산
│   ├── k8s_setup.py           # 사용자 K8s 네임스페이스 자동 생성
│   ├── service_factory.py     # 환경변수 기반 서비스 팩토리
│   └── seed_data.py           # 미션 초기 데이터 (4개 레벨)
└── ai/
    ├── __init__.py
    ├── tutor_service.py      # AI 튜터 어댑터 (ai-data 연동, Mock/OpenAI 전환)
    ├── scenario_agent.py     # 시나리오 생성 AI (Mock + OpenAI, 예정)
    └── validation_agent.py   # 검증 조건 생성 AI (예정)
```

## API 엔드포인트

### 인증
- `POST /api/auth/register` - 회원가입
- `POST /api/auth/login` - 로그인 (JWT 발급, form-data 형식)
- `GET /api/auth/me` - 프로필 조회 (완료 미션 수, 총 점수 포함) 🔒
- `POST /api/auth/logout` - 로그아웃 (204 반환, 토큰 삭제는 클라이언트 처리) 🔒

### 터미널
- `POST /api/terminal/sessions` - 터미널 세션 생성 + K8s 네임스페이스/nginx Pod 자동 생성 🔒
- `WS /ws/terminal/{session_id}?token=JWT` - 웹 터미널

### 고정 미션 (4개 레벨 튜토리얼)
- `GET /api/missions/` - 미션 목록 (잠금 상태 포함)
- `POST /api/missions/start` - 미션 시작
- `GET /api/missions/status` - 진행 중 미션 상태
- `POST /api/missions/check` - 해결 여부 확인
- `POST /api/missions/abandon` - 미션 포기
- `POST /api/missions/hint` - 힌트 사용
- `POST /api/missions/debug/resolve` - (Mock 전용) 수동 해결

### AI 시나리오 (예정 - agent.md Phase 1~6)
- `POST /api/scenarios/start-random` - 난이도 선택 후 AI 랜덤 시나리오 생성+시작 🔒
- `POST /api/scenarios/generate` - 시나리오 후보 생성만 (미리보기) 🔒
- `POST /api/scenarios/{scenario_id}/start` - 생성된 시나리오 시작 🔒
- `POST /api/scenarios/current/check` - AI 시나리오 완료 검증 🔒

### 대시보드 / 게이미피케이션
- `GET /api/dashboard/stats` - 내 통계 (총 점수, 티어, 스킬 점수) 🔒
- `GET /api/dashboard/learning-curve` - 미션 시도 히스토리 🔒
- `GET /api/leaderboard` - 전체 리더보드 🔒
- `GET /api/achievements` - 업적 목록 및 달성 여부 🔒

### AI 튜터
- `POST /api/chat/` - AI 튜터에게 질문 (소크라테스식 힌트)
  - Request: `{ "message": str, "hint_level": 0~3 }`
  - Response: `{ "response": str, "hint_level": int, "mission_name": str, "sources": [...] }`
  - 진행 중인 미션(고정/AI) 있어야 사용 가능

## 미션 시스템 아키텍처

### 고정 미션 (튜토리얼)
- 환경변수 `CHAOS_BACKEND=mock|chaos_mesh`, `VALIDATION_BACKEND=mock|k8s|prometheus`로 전환
- `POST /api/terminal/sessions` 호출 시 K8s 네임스페이스(`user-{uuid}`) + nginx Deployment 자동 생성 (k8s_setup.py)
- 미션 시작 시 해당 네임스페이스에 chaos 주입

### Chaos Mesh 장애 주입 방식 (chaos_injector.py)
| chaos_type | 방식 | 사용자 Fix |
|---|---|---|
| `pod_failure` | nginx 이미지를 `nginx:wrongtag`로 패치 → ImagePullBackOff | `kubectl set image deployment/nginx nginx=nginx:latest` |
| `memory_stress` | nginx 메모리 limit을 6Mi로 낮춤 + StressChaos 64MB 압박 → OOMKilled | `kubectl patch deployment/nginx`으로 memory limit 상향 |
| `service_misconfig` | webapp Deployment + 잘못된 selector의 Service 생성 | Service selector 수정 |
| `network_latency` | NetworkChaos로 2초 지연 주입 | **재설계 필요** - 현재 Liveness Probe 추가가 실제로 지연을 제거하지 않음 |

> **memory_stress 주의**: 컨테이너 런타임 최소 메모리는 약 6Mi. 4Mi 이하는 CreateContainerError 발생.

### 검증 백엔드 (validation_service.py)
| VALIDATION_BACKEND | 설명 |
|---|---|
| `mock` | 인메모리 수동 해결 (개발용, MOCK_VALIDATION_AUTO_PASS=true 가능) |
| `k8s` | Kubernetes API로 실제 리소스 상태 검증 |
| `prometheus` | Prometheus PromQL로 메트릭 기반 검증 |

### AI 시나리오 모드 (예정)
- 기본 4개 미션 완료 후 활성화
- 사용자가 난이도(Beginner/Intermediate/Advanced/Expert) 선택 → AI가 3개 후보 생성 → 백엔드 안전성 검사 → 주입
- `ChaosPlan` 구조로 컴파일 후 실행 (allowlist + namespace 격리 + dry-run 검증)
- 동적 PromQL 검증 조건을 `validation_rules` 테이블에 저장
- `PromQLGuard`로 namespace 없는 광범위 쿼리 차단
- 자세한 설계: [agent.md](../agent.md)

### 게이미피케이션 (analytics_service.py)
- 티어: Bronze(0) → Silver(201) → Gold(501) → Platinum(1001) → DevOps Master(2001+)
- 업적: First Recovery, Environmentalist(힌트 없이 클리어), Speed Runner(5분 이내), Persistent Resolver(10회 시도)
- 스킬 점수: troubleshooting / resource / network / ops 카테고리별 계산

## 데이터 모델

### 현재 모델
- `User` - 사용자 (username, email, hashed_password, total_score)
- `Mission` - 고정 미션 정의 (level, chaos_type, base_score 등)
- `MissionAttempt` - 미션 시도 기록 (status, final_score, hints_used)
- `TerminalSession` - 터미널 세션
- `CommandLog` - kubectl 명령 실행 기록

### 추가 예정 (AI 시나리오 Phase 1~3)
- `MissionAttempt`에 `attempt_type` (static_mission | ai_scenario), `scenario_id` 필드 추가
- `GeneratedScenario` - AI 생성 시나리오 (scenario_json, chaos_plan_json, safety_review 등)
- `ValidationRule` - AI 생성 검증 조건 (promql/k8s 타입, guard_status)
- `TutorMessage` - 튜터 대화 영구 저장 (현재는 인메모리)

## AI 튜터 아키텍처
- `ai-data/` 모듈을 sys.path로 동적 import (별도 패키지 설치 불필요)
- `AI_BACKEND=mock`: OpenAI 없이 고정 힌트 반환 (개발용)
- `AI_BACKEND=openai`: ai-data의 AITutorEngine + RAG + GPT 사용
- 힌트 레벨 0~3: 방향제시 → 리소스지목 → kubectl 명령어 → 전체 해결
- 대화 히스토리: attempt_id 기준 인메모리 저장 (최근 5개 질문) → TutorMessage로 DB 저장 예정

## 컨벤션
- PEP8 준수, 타입 힌트 필수
- Pydantic 모델로 요청/응답 정의
- 환경 변수는 .env + pydantic-settings
- 비동기 우선 (async/await)
- K8s 동기 API는 `run_in_executor` 패턴으로 비동기 래핑

## 실행
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 의존 서비스
- PostgreSQL: localhost:5432 (k8s_survival DB)
- Qdrant: localhost:6333 (벡터 DB)
- Prometheus: localhost:9090 (메트릭, 모니터링 프로필 실행 시)
- Grafana: localhost:3001 (대시보드, 모니터링 프로필 실행 시)

## 테스트
```bash
cd backend
python -m pytest tests/ -v
```
