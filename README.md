# K8s Survival Camp

카오스 엔지니어링 + AI 튜터 + 게이미피케이션 기반 DevOps 장애 대응 훈련 플랫폼

## 프로젝트 개요

Kubernetes 환경에서 실제 장애를 직접 주입하고 해결하며 배우는 실전형 훈련 플랫폼입니다.

- **고정 미션 4개**: 기초 K8s 장애 유형을 순서대로 학습 (튜토리얼)
- **AI 장애 생성 모드**: 4개 미션 완료 후 AI가 동적으로 장애를 생성해 무한 실습 (개발 중)
- **소크라테스식 AI 튜터**: 정답을 바로 주지 않고 관찰과 추론을 유도
- **실시간 Grafana 대시보드**: 미션 진행 중 내 네임스페이스 메트릭을 실시간 관찰

## 프로젝트 구조

```
cloud-trouble-training-service/
├── frontend/               # React + TypeScript + xterm.js 터미널 UI
├── backend/                # FastAPI 백엔드 (미션/터미널/AI/채점)
│   └── CLAUDE.md           # 백엔드 상세 아키텍처
├── ai-data/                # RAG 지식창고 (LangChain + Qdrant)
│   ├── knowledge-base/     # 장애 대응 문서, 인시던트 로그
│   ├── prompts/            # AI 튜터/시나리오 생성 프롬프트
│   └── rag_service.py      # 벡터 검색 서비스
├── infra/
│   ├── monitoring/         # Prometheus, Grafana, Loki, AlertManager 설정
│   └── k8s/                # Kubernetes 매니페스트
├── agent.md                # AI 장애 생성 모드 전체 설계 문서
├── CLAUDE.md               # 프로젝트 개발 가이드 (Claude Code용)
├── docker-compose.yml      # 로컬 인프라 실행 (postgres, qdrant, monitoring)
└── README.md
```

## 기술 스택

| 영역 | 기술 |
|---|---|
| Frontend | React 18, TypeScript, Vite, xterm.js |
| Backend | FastAPI, Python 3.11, SQLAlchemy async, PostgreSQL |
| AI | LangChain, OpenAI gpt-4o-mini, Qdrant (RAG) |
| Infra | Kubernetes, Chaos Mesh |
| Monitoring | Prometheus, Grafana, Loki, Promtail, AlertManager |

## 주요 기능

- **Chaos Mesh 장애 주입**: pod_failure / memory_stress / service_misconfig / network_latency
- **사용자별 격리된 K8s 네임스페이스**: 로그인 시 `user-{uuid}` 네임스페이스 자동 생성
- **웹 터미널**: xterm.js + WebSocket, kubectl 명령 전용
- **AI 튜터**: 소크라테스식 힌트 (레벨 0~3), RAG 기반 지식 검색
- **게이미피케이션**: 티어 시스템, 업적, 리더보드, 스킬 점수
- **실시간 모니터링**: 미션 진행 중 Grafana iframe으로 내 네임스페이스 상태 표시

## 로컬 실행 (Method B - 권장)

인프라는 Docker Compose, 백엔드/프론트는 직접 실행.

**사전 요구사항:**
- Docker Desktop (Kubernetes 활성화)
- Helm (Chaos Mesh 설치용)
- Python 3.11, Node.js

```bash
# 1. Chaos Mesh 설치 (최초 1회)
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-testing --create-namespace \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock

# 2. 인프라 실행
docker compose up postgres qdrant -d

# 3. 백엔드 실행
cd backend
pip install -r requirements.txt
cp .env.example .env   # 환경변수 설정
uvicorn app.main:app --reload --port 8000

# 4. 프론트엔드 실행
cd frontend
npm install
npm run dev

# Swagger: http://localhost:8000/docs
# Frontend: http://localhost:3000
```

## 모니터링 스택 포함 실행

```bash
docker compose --profile monitoring up -d

# Grafana: http://localhost:3001 (admin/admin)
# Prometheus: http://localhost:9090
```

## 환경변수

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival
AI_BACKEND=mock              # mock | openai
OPENAI_API_KEY=
CHAOS_BACKEND=mock           # mock | chaos_mesh
VALIDATION_BACKEND=mock      # mock | k8s | prometheus
MOCK_VALIDATION_AUTO_PASS=false
PROMETHEUS_URL=http://localhost:9090
```

## 문서

- [agent.md](agent.md) - AI 장애 생성 모드 전체 설계 (Phase 1~7)
- [CLAUDE.md](CLAUDE.md) - 개발 가이드 및 구현 현황
- [backend/CLAUDE.md](backend/CLAUDE.md) - 백엔드 API 및 서비스 상세
