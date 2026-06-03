# K8s Survival Camp

카오스 엔지니어링 + AI 튜터 + 게이미피케이션 기반 DevOps 장애 대응 훈련 플랫폼 (캡스톤 디자인)

## 핵심 메커니즘
1. Attack - Chaos Mesh가 사용자 Pod 공격 (고정 4개 미션 + AI 동적 생성)
2. Defend - 사용자가 kubectl로 장애 해결 (AI 튜터가 소크라테스식 힌트 제공)
3. Score - Prometheus가 정상화 감지 → 점수 부여

## 캡스톤 로드맵

### 캡스톤 1 - Kubernetes 완성 (현재 진행)
기존 4개 고정 미션을 튜토리얼로 유지하고, AI가 동적으로 장애를 생성하는 "AI 문제 더 풀기" 모드를 추가한다. 자세한 설계는 [agent.md](agent.md) 참고.

- 기존 4개 미션 튜토리얼 유지
- AI 장애 생성 모드 (난이도 선택 → 랜덤 시나리오 주입)
- Grafana 패널 실무형 완성 (cAdvisor 추가 필요)
- 검증 안정화 (VALIDATION_BACKEND=k8s 실 테스트)
- 미션 4 (network_latency) 재설계 필요

### 캡스톤 2 - 멀티 환경 고도화 (예정)
탭 분리: Kubernetes / Docker-only / Linux / Application

## 기술 스택
- Frontend: React (xterm.js 터미널, 채팅 UI)
- Backend: FastAPI, SQLAlchemy async, PostgreSQL
- AI: LangChain + OpenAI gpt-4o-mini (소크라테스식 튜터, 시나리오 생성), Qdrant (RAG)
- Infra: Kubernetes, Chaos Mesh
- Monitoring: Prometheus, Grafana, Loki, Promtail, AlertManager

## 구현 현황 (2026-06-03 기준)

### 완료
- [x] 회원가입 / 로그인 (JWT)
- [x] 로그아웃 / 프로필 조회 API
- [x] 웹 터미널 (xterm.js + WebSocket, kubectl 전용)
- [x] 미션 시스템 (목록/시작/상태/완료/포기/힌트, 4개 레벨)
- [x] 점수 계산 (시간 감점 + 힌트 감점)
- [x] AI 튜터 채팅 API (Mock 패턴, 시나리오별 소크라테스식 힌트)
- [x] RAG AI 엔진 (ai-data/ - LangChain + Qdrant + GPT)
- [x] Chaos Mesh 연동 (로그인 시 사용자 네임스페이스 + nginx Pod 자동 생성)
- [x] K8s API 기반 실제 검증 (K8sValidationService)
- [x] Prometheus 기반 검증 (PrometheusValidationService)
- [x] 대시보드 / 리더보드 / 업적 시스템
- [x] 티어 시스템 (Bronze → Silver → Gold → Platinum → DevOps Master)
- [x] 모니터링 스택 (Prometheus + Grafana + Loki + Promtail + AlertManager)

### 진행 중 (캡스톤 1)
- [ ] AI 장애 생성 모드 (agent.md Phase 1~6)
- [ ] cAdvisor 추가 (Pod CPU/Memory/Network 실사용 메트릭)
- [ ] 미션 4 (network_latency) 재설계
- [ ] AI 튜터 OpenAI 실제 연동

### 예정 (캡스톤 2)
- [ ] AWS EKS 배포
- [ ] 멀티 환경 탭 (Docker-only, Linux, Application)

## 브랜치 전략
- `main` - 배포 브랜치
- `dev` - 통합 브랜치
- `feature/*` - 기능 브랜치 → dev PR
- AI 장애 생성 기능은 `feature/ai-scenario` 브랜치에서 개발 후 dev PR

## 로컬 실행
```bash
# 인프라만 (권장 - Method B)
docker compose up postgres qdrant -d

# 백엔드
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
AI_BACKEND=mock              # mock | openai
OPENAI_API_KEY=              # openai 모드일 때 필요
OPENAI_MODEL=gpt-4o-mini
SCENARIO_MODEL=gpt-4o-mini   # AI 시나리오 생성 모델
TUTOR_MODEL=gpt-4o-mini      # AI 튜터 모델
EMBEDDING_MODEL=text-embedding-3-small
CHAOS_BACKEND=mock           # mock | chaos_mesh
VALIDATION_BACKEND=mock      # mock | k8s | prometheus
MOCK_VALIDATION_AUTO_PASS=false
PROMETHEUS_URL=http://localhost:9090

# 프론트엔드 (Vite 빌드 시)
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
VITE_GRAFANA_BASE_URL=http://localhost:3001
```

## 모니터링 스택 실행
```bash
# 모니터링 프로필로 실행 (Prometheus + Grafana + Loki 포함)
docker compose --profile monitoring up -d

# Grafana: http://localhost:3001 (admin/admin)
# Prometheus: http://localhost:9090
```

## 주요 설계 문서
- [agent.md](agent.md) - AI 장애 생성 모드 전체 설계 (Phase 1~7, 안전장치, API, 데이터 모델)
- [backend/CLAUDE.md](backend/CLAUDE.md) - 백엔드 API 및 서비스 상세
- [README.md](README.md) - 프로젝트 공개 소개

## 규칙
- 항상 한국어로 응답
- 커밋 메시지는 한국어로 작성
