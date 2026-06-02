# K8s Survival Camp

카오스 엔지니어링 + AI 튜터 + 게이미피케이션 기반 DevOps 장애 대응 훈련 플랫폼 (캡스톤 디자인)

## 핵심 메커니즘
1. Attack - Chaos Mesh가 사용자 Pod 공격
2. Defend - 사용자가 kubectl로 장애 해결 (AI 튜터가 소크라테스식 힌트 제공)
3. Score - Prometheus가 정상화 감지 → 점수 부여

## 기술 스택
- Frontend: React (xterm.js 터미널, 채팅 UI)
- Backend: FastAPI, SQLAlchemy async, PostgreSQL
- AI: LangChain + OpenAI (소크라테스식 튜터), Qdrant (RAG)
- Infra: Kubernetes, Chaos Mesh
- Monitoring: Prometheus, Grafana, Loki, Promtail, AlertManager

## 구현 현황 (2026-06-03 기준)
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
- [ ] AWS EKS 배포
- [ ] AI 튜터 OpenAI 실제 연동

## 브랜치 전략
- `main` - 배포 브랜치
- `dev` - 통합 브랜치
- `feature/*` - 기능 브랜치 → dev PR

## 로컬 실행
```bash
# DB 실행
docker compose up postgres -d

# 백엔드
cd backend
source venv/bin/activate
uvicorn app.main:app --port 8000

# Swagger
open http://localhost:8000/docs
```

## 환경변수 (.env)
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival
AI_BACKEND=mock              # mock | openai
OPENAI_API_KEY=              # openai 모드일 때 필요
CHAOS_BACKEND=mock           # mock | chaos_mesh
VALIDATION_BACKEND=mock      # mock | k8s | prometheus
MOCK_VALIDATION_AUTO_PASS=false

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

## 규칙
- 항상 한국어로 응답
- 커밋 메시지는 한국어로 작성
