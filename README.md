# K8s Survival Camp

카오스 엔지니어링 + AI 튜터 + 게이미피케이션 기반 DevOps 장애 대응 훈련 플랫폼

## 프로젝트 개요

Kubernetes 환경에서 실제 장애를 직접 주입하고 해결하며 배우는 실전형 훈련 플랫폼입니다.

- **고정 미션 4개**: 기초 K8s 장애 유형을 순서대로 학습하는 튜토리얼 커리큘럼
- **AI 장애 생성 모드**: 4개 미션 완료 후 AI가 동적으로 장애를 생성해 무한 실습
- **소크라테스식 AI 튜터**: 정답을 바로 주지 않고 관찰과 추론을 유도하는 힌트 시스템
- **실시간 Grafana 대시보드**: 미션 진행 중 내 네임스페이스 메트릭을 실시간 관찰

## 프로젝트 구조

```
cloud-trouble-training-service/
├── frontend/               # React + TypeScript + xterm.js 터미널 UI
├── backend/                # FastAPI 백엔드 (미션/터미널/AI/채점)
│   └── CLAUDE.md           # 백엔드 상세 아키텍처
├── ai-data/                # RAG 지식창고 (LangChain + Qdrant)
│   ├── knowledge-base/     # 장애 대응 문서
│   ├── prompts/            # AI 튜터/시나리오 생성 시스템 프롬프트
│   └── rag_service.py      # 벡터 검색 서비스
├── infra/
│   ├── monitoring/         # Prometheus, Grafana, Loki, AlertManager 설정
│   └── k8s/                # Kubernetes 매니페스트
├── agent.md                # AI 장애 생성 모드 설계 및 구현 현황
├── CLAUDE.md               # 프로젝트 개발 가이드 (Claude Code용)
├── docker-compose.yml      # 로컬 인프라 (postgres, qdrant, monitoring)
└── README.md
```

## 기술 스택

| 영역 | 기술 |
|---|---|
| Frontend | React 18, TypeScript, Vite, xterm.js |
| Backend | FastAPI, Python 3.11, SQLAlchemy async, PostgreSQL |
| AI | LangChain, OpenAI gpt-4o-mini / Google Gemini, Qdrant (RAG) |
| Infra | Kubernetes (Docker Desktop), Chaos Mesh |
| Monitoring | Prometheus, Grafana, Loki, Promtail, AlertManager |

## 주요 기능

### 고정 미션 (튜토리얼)
| 레벨 | 장애 유형 | 학습 내용 |
|---|---|---|
| Level 1 | ImagePullBackOff | 잘못된 이미지 태그 진단 및 수정 |
| Level 2 | OOMKilled | 메모리 리소스 제한 설정 |
| Level 3 | Service 연결 실패 | Service selector/label 관계 이해 |
| Level 4 | Readiness Probe 실패 | Pod 헬스체크 설정 |

### AI 장애 생성 모드
- 기본 4개 미션 완료 후 활성화
- 난이도 선택 (Beginner / Intermediate / Advanced / Expert)
- AI가 시나리오 생성 → 안전성 검사 → 실제 K8s에 장애 주입
- 동적 K8s API 기반 검증 (서비스 엔드포인트, 배포 상태)

### 공통
- 사용자별 격리된 K8s 네임스페이스 (`user-{uuid}`)
- 웹 터미널 (xterm.js + WebSocket, kubectl 전용)
- AI 튜터: 소크라테스식 힌트 레벨 0~3, RAG 기반 지식 검색
- 게이미피케이션: 티어, 업적, 리더보드, 스킬 점수
- Grafana 대시보드: Pod 메모리/CPU/엔드포인트 상태 실시간 표시

## 로컬 실행 (Method B - 권장)

인프라는 Docker Compose, 백엔드/프론트는 직접 실행.

**사전 요구사항:**
- Docker Desktop (Kubernetes 활성화 필요)
- Helm (Chaos Mesh 설치용)
- Python 3.11, Node.js 18+

```bash
# 1. Chaos Mesh 설치 (최초 1회, CHAOS_BACKEND=chaos_mesh 사용 시)
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-testing --create-namespace \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock

# 2. 인프라 실행
docker compose up postgres qdrant -d

# 3. 백엔드 실행
cd backend
pip install -r requirements.txt
cp .env.example .env   # 환경변수 설정 후 편집
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

## 환경변수 주요 설정

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival

# AI 백엔드 (mock: API 키 불필요, openai/gemini: 실제 LLM 사용)
AI_BACKEND=mock              # mock | openai | gemini

# OpenAI 모드
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Gemini 모드
GEMINI_API_KEY=AIza...
GEMINI_MODEL=models/gemini-2.0-flash-lite

# 인프라 (mock: 로컬 개발, chaos_mesh: 실제 K8s)
CHAOS_BACKEND=mock           # mock | chaos_mesh
VALIDATION_BACKEND=mock      # mock | k8s | prometheus
```

전체 환경변수는 `backend/.env.example` 참고.

## 문서

- [agent.md](agent.md) - AI 장애 생성 모드 설계 및 구현 현황
- [CLAUDE.md](CLAUDE.md) - 개발 가이드 및 구현 현황
- [backend/CLAUDE.md](backend/CLAUDE.md) - 백엔드 API 및 서비스 상세
