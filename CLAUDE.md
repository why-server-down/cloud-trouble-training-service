# AfterFail

카오스 엔지니어링 + AI 튜터 + 게이미피케이션 기반 DevOps 장애 대응 훈련 플랫폼 (캡스톤 디자인)

## 핵심 메커니즘
1. Attack - Chaos Mesh가 사용자 Pod 공격 (고정 4개 미션 + AI 동적 생성)
2. Defend - 사용자가 kubectl로 장애 해결 (AI 튜터가 소크라테스식 힌트 제공)
3. Score - K8s API/Prometheus가 정상화 감지 → 점수 부여

## 캡스톤 로드맵

### 캡스톤 1 - Kubernetes 완성 (진행 중)
기존 4개 고정 미션을 튜토리얼로 유지하고, AI가 동적으로 장애를 생성하는 "AI 문제 더 풀기" 모드를 추가한다. 자세한 설계는 [agent.md](agent.md) 참고.

- 기존 4개 미션 튜토리얼 유지
- AI 장애 생성 모드 Phase 1~6 완료 (Phase 5는 부분 완료 - incident-logs 미구성)
- Grafana 패널 cAdvisor 수정 완료 (Docker Desktop container="" 필터)
- 검증 K8s fallback 추가 완료
- 미션 4 재설계 완료 (network_latency → Readiness Probe 실패로 구현)

### 캡스톤 2 - 멀티 환경 고도화 (진행 중)
K8s 전용 훈련을 다중 환경으로 확장한다. 환경은 **Kubernetes(기존) / Docker / Linux** 3종.

> **실행 명세 우선.** 2학기 구현은 담당별 계획서의 작업 ID 단위로 진행한다.
> 백엔드 [docs/backend-capstone2-semester-plan.md](docs/backend-capstone2-semester-plan.md) (`BE-00`~`BE-28`),
> 프론트 [docs/frontend-capstone2-semester-plan.md](docs/frontend-capstone2-semester-plan.md) (`FE-*`),
> AI [docs/ai-capstone2-semester-plan.md](docs/ai-capstone2-semester-plan.md).
> 이 파일과 계획서가 어긋나면 계획서가 기준이며, 이 파일을 갱신한다.

**Application/DB는 목업 한정.** 백엔드 `SUPPORTED_ENVIRONMENTS`에 등록하지 않고 sandbox·injector·validator·명령 정책을 제공하지 않는다. UI에서도 "개발 예정"이 아니라 **후속 연구**로 표기한다. 8주차 범위 게이트(BE-15) 통과 + 실행 계약 확정 시에만 별도 이슈로 승격.

| 단계 | 브랜치 | 작업 ID | 주차 | 상태 |
|---|---|---|---|---|
| 기반 | `feature/env-schema` | — | — | [x] environment 데이터 계층 관통 (PR #30) |
| 기반 | `feature/injector-refactor` | — | — | [x] 레지스트리 디스패치 전환 (PR #31) |
| 1 | `feature/backend-baseline` | BE-01~03 | 1–2 | [ ] 테스트 녹색화, Alembic 도입, API environment 필드 |
| 2 | `feature/env-sandbox` | BE-04, BE-07 | 3–4 | [ ] SandboxService, Quota/NetworkPolicy/RBAC, 세션 API |
| 3 | `feature/safe-terminal-exec` | BE-05, BE-06 | 3–4 | [ ] host shell 제거 → Pod exec, WS 소유권 검증 |
| 4 | `feature/env-runtime` | BE-08~10 | 5–6 | [ ] environment 기반 factory, 미션 잠금·seed, K8s 회귀 |
| 5 | `feature/docker-env` | BE-11~15 | 7–8 | [ ] DinD sandbox·injector·validator, 8주차 범위 게이트 |
| 6 | `feature/linux-env` | BE-16~18 | 9–10 | [ ] Linux sandbox·injector·validator |
| 7 | `feature/cross-layer-contracts` | BE-19~21 | 11–12 | [ ] RuntimeContext, AI 실행 계약, MTTR·analytics |
| 8 | `feature/backend-hardening` | BE-22~24 | 13–14 | [ ] 동시성·reconciliation, CORS·메트릭, 테스트 확대 |
| 9 | `feature/aws-migration` | BE-25 | 15–16 | [ ] EKS 보안 배포 (별도 트랙) |
| 10 | `feature/backend-release` | BE-26~28 | 15–16 | [ ] E2E·성능·문서 |

**실행/격리 설계:** K8s를 실행 기반으로 삼아 환경을 사용자 네임스페이스 안 샌드박스 Pod(kubernetes=toolbox+target, docker=DinD, linux=범용 Pod)로 제공하고, 터미널 명령을 호스트 subprocess가 아닌 **argv allowlist + Pod 내부 exec**로 실행한다. 실행 대상은 서버가 DB 세션에서 결정하며 클라이언트 값을 신뢰하지 않는다. 상세는 [agent.md](agent.md) "실행/격리 아키텍처" 참고.

**우선 해소 대상 (P0):** ① host `shell=True` 실행 ② WebSocket 세션 소유권 미검증 ③ environment가 세션·명령 실행까지 미연결 ④ active chaos ID가 프로세스 메모리에만 존재(재시작 시 정리 불가).

브랜치는 dev에서 기능별로 분기 → dev PR. 위 표의 순서를 따르되 5·6(Docker/Linux)은 4 머지 후 병렬 가능.

## 기술 스택
- Frontend: React (xterm.js 터미널, 채팅 UI, 환경 탭 UI)
- Backend: FastAPI, SQLAlchemy async, PostgreSQL
- AI: LangChain + OpenAI gpt-4o-mini / Google Gemini (소크라테스식 튜터, 시나리오 생성), Qdrant (RAG)
- Infra: Kubernetes, Chaos Mesh
- Monitoring: Prometheus, Grafana, Loki, Promtail, AlertManager

## 구현 현황 (2026-06-05 기준)

### 완료
- [x] 회원가입 / 로그인 (JWT)
- [x] 로그아웃 / 프로필 조회 API
- [x] 웹 터미널 (xterm.js + WebSocket, kubectl 전용)
- [x] 미션 시스템 (목록/시작/상태/완료/포기/힌트, 4개 레벨)
- [x] 점수 계산 (시간 감점 + 힌트 감점)
- [x] AI 튜터 채팅 API (Mock + OpenAI/Gemini 연동, K8s Pod 상태 실시간 반영)
- [x] RAG AI 엔진 (ai-data/ - LangChain + Qdrant + GPT/Gemini)
- [x] Chaos Mesh 연동 (로그인 시 사용자 네임스페이스 + nginx Pod 자동 생성)
- [x] K8s API 기반 실제 검증 (K8sValidationService)
- [x] Prometheus 기반 검증 (PrometheusValidationService)
- [x] 대시보드 / 리더보드 / 업적 시스템
- [x] 티어 시스템 (Bronze → Silver → Gold → Platinum → DevOps Master)
- [x] 모니터링 스택 (Prometheus + Grafana + Loki + Promtail + AlertManager)
- [x] Grafana cAdvisor 패널 수정 (container="" 필터, Docker Desktop 호환)
- [x] AI 튜터 Pod 상태 조회 datetime 정렬 버그 수정
- [x] 환경 탭 UI (Kubernetes / Docker / Linux / Application, 미개발 탭 WIP 화면)
  - 캡스톤2에서 `GET /api/environments` 가용성 기반으로 전환 예정. Application 탭은 목업/후속 연구 표기로 변경.
- [x] **AI 장애 생성 모드 Phase 1~3** (agent.md 기준)
  - GeneratedScenario / ValidationRule 모델 및 DB 마이그레이션
  - ScenarioAgent: Mock fixture (난이도별 4종) + OpenAI/Gemini 실제 생성
  - ChaosPlan / ChaosPlanCompiler (allowlist 안전장치)
  - ScenarioService (생성 → 주입 → 검증 → 포기 → 힌트 전체 오케스트레이션)
  - ValidationRuleService: PromQLGuard + k8s 타입 룰 + K8s 직접 검증 fallback
  - /api/scenarios/* 전체 엔드포인트 (start-random, status, current/check, current/abandon, current/hint, unlock-status)
  - ai-data/prompts/scenario_gen.md 시나리오 생성 시스템 프롬프트
  - 프론트엔드 AI Challenge Mode UI (잠금 해제 조건, 난이도 선택, 진행 상황 표시)
- [x] missions.py AI 시나리오 attempt 혼용 크래시 수정 (NoneType 방지)
- [x] scenario_agent.py mock fixture validation k8s 룰로 통일
- [x] 미션 4 재설계 (chaos_type=network_latency → Readiness Probe 실패 주입으로 구현)
- [x] **AI 장애 생성 모드 Phase 4** (agent.md 기준)
  - RuntimeContextCollector 구현 및 튜터 연결 완료 (K8s state + 이벤트 + Prometheus + 명령 이력)
  - TutorMessage DB 모델 및 저장 로직 구현 완료
- [x] **AI 장애 생성 모드 Phase 5 (부분 완료)**
  - RAG knowledge-base 구축 (troubleshooting/ 전용 문서 + 6개 권위 출처 문서)
  - fault_type 기반 RAG 필터링 구현 (ingest_knowledge.py + rag_service.py + ai_engine.py)
  - Qdrant 217개 청크 ingestion 완료, 채팅 API 연동 검증 완료
  - ai-data/ingest.py 공용 모듈 분리 (load_all_documents + FAULT_TYPE_TAGS)
  - 미완료: incident-logs/ 실제 운영 장애 로그 문서 미구성
- [x] **AI 장애 생성 모드 Phase 6** — validation_agent.py 구현 완료 (Mock + OpenAI/Gemini LLM 판정)
- [x] **Qdrant knowledge-base 자동 ingestion** — 서버 시작 시 컬렉션 비어있으면 자동 적재
  - AI_BACKEND=mock이거나 이미 문서 있으면 skip
  - backend/app/services/qdrant_init.py (auto_ingest_if_empty)
  - main.py lifespan에 통합

### 진행 중 (캡스톤 1)
- [ ] AI 장애 생성 모드 Phase 7 (운영 메트릭, 비용 제한, 시드 저장)
- [ ] Phase 5 미완료: incident-logs/ 실제 클라우드 장애 로그 문서 추가

### 진행 중 (캡스톤 2)
단계별 진행 상태는 위 "캡스톤 2" 로드맵 표를 기준으로 한다. 현재 기반 2건(env-schema, injector-refactor) 완료, 다음은 `feature/backend-baseline`(BE-01~03).

**백엔드 테스트 기준선 (2026-08-26 실측, `backend/` venv):**
```
python -m pytest -q  →  1 failed, 31 passed
```
- 실패 1건: `tests/test_command_validator.py::TestBlockedCommands::test_invalid_subcommand`
  (`kubectl create secret`이 허용됨 → 허용 여부를 미션 요구와 맞추고 resource/flag까지 제한)
- `pytest-asyncio==0.23.3`은 requirements·venv 모두에 설치되어 async 테스트가 실행된다.
  단 `pytest.ini`가 없어 `asyncio_mode`가 미명시 → BE-01에서 추가한다.
- 계획서 §2.2의 "28 passed / 4 failed / pytest-asyncio 미설치"는 다른 환경 기준 수치다.

## 브랜치 전략
- `main` - 배포 브랜치
- `dev` - 통합 브랜치
- `feature/*` - 기능 브랜치 → dev PR
- AI 장애 생성 기능은 `feature/ai-scenario` 브랜치에서 개발 후 dev PR

## 로컬 실행
```bash
# 인프라만 (권장 - Method B)
docker compose up postgres qdrant -d

# 백엔드 (AI_BACKEND=openai|gemini 시 서버 시작 시 Qdrant 자동 ingestion)
cd backend
source venv/bin/activate
uvicorn app.main:app --port 8000

# 프론트엔드
cd frontend
npm run dev

# Swagger
open http://localhost:8000/docs
```

## 환경변수 (.env)
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival

# AI 백엔드 선택
AI_BACKEND=mock              # mock | openai | gemini

# OpenAI 모드
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
SCENARIO_MODEL=gpt-4o-mini
TUTOR_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

# Gemini 모드 (OpenAI 호환 API 사용)
GEMINI_API_KEY=
GEMINI_MODEL=models/gemini-2.0-flash-lite
GEMINI_EMBEDDING_MODEL=models/text-embedding-004

# 인프라
CHAOS_BACKEND=mock           # mock | chaos_mesh
VALIDATION_BACKEND=mock      # mock | k8s | prometheus
MOCK_VALIDATION_AUTO_PASS=false
PROMETHEUS_URL=http://localhost:9090

# RAG (Qdrant 벡터 DB)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=              # Qdrant Cloud 사용 시

# 프론트엔드 (Vite 빌드 시)
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
VITE_GRAFANA_BASE_URL=http://localhost:3001
```

## 모니터링 스택 실행
```bash
docker compose --profile monitoring up -d

# Grafana: http://localhost:3001 (admin/admin)
# Prometheus: http://localhost:9090
```

> **주의 (로컬 환경)**: `infra/monitoring/prometheus.yml`의 노드명(`desktop-control-plane`)은 **Docker Desktop 4.x 이상** 기준.
> 구버전 Docker Desktop은 노드명이 `docker-desktop`이므로 Grafana CPU/Memory가 No Data로 표시됨.
> ```bash
> kubectl get nodes          # 노드명 확인
> docker --version           # Docker Desktop 버전 확인
> # 구버전이면 Docker Desktop 업데이트 권장 (Settings → Check for Updates)
> # 업데이트 후 Settings → Kubernetes → Reset Kubernetes Cluster
> ```
> 캡스톤 2 (EKS 배포) 때 Kubernetes 서비스 디스커버리(`kubernetes_sd_configs`)로 자동화 예정.

## 주요 설계 문서
- [agent.md](agent.md) - AI 장애 생성 모드 전체 설계 및 구현 현황 (Phase 1~7)
- [backend/CLAUDE.md](backend/CLAUDE.md) - 백엔드 API 및 서비스 상세
- [README.md](README.md) - 프로젝트 공개 소개

## 규칙
- 항상 한국어로 응답
- 커밋 메시지는 한국어로 작성
