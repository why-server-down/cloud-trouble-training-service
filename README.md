# AfterFail

Kubernetes 장애를 직접 일으키고, 직접 고치면서 배우는 DevOps 훈련 플랫폼입니다.
카오스 엔지니어링으로 실제 장애를 주입하고, AI 튜터가 소크라테스식으로 사고를 유도하며,
게이미피케이션 요소로 학습 동기를 이어가도록 설계했습니다. (캡스톤 디자인 프로젝트)

## 왜 만들었나

장애 대응 능력은 문서만 읽어서는 늘지 않습니다. 실제로 깨진 클러스터를 마주하고
로그와 이벤트를 뒤지며 가설을 세워 명령을 던져보는 경험이 쌓여야 합니다.
하지만 운영 환경을 일부러 망가뜨릴 수는 없고, 개인이 안전한 실습 환경을 갖추기도 번거롭습니다.

AfterFail은 사용자마다 격리된 Kubernetes 네임스페이스를 만들고 그 안에서만 장애를 주입합니다.
사용자는 웹 터미널에서 `kubectl`로 문제를 진단하고 고치며, 정상화되면 시스템이 이를
메트릭과 리소스 상태로 감지해 점수를 줍니다.

## 동작 방식

세 단계 루프로 돌아갑니다.

1. Attack — Chaos Mesh가 사용자 네임스페이스의 리소스에 장애를 주입합니다.
2. Defend — 사용자가 터미널에서 장애를 진단하고 해결합니다. 막히면 AI 튜터에게 힌트를 요청합니다.
3. Score — Kubernetes API 또는 Prometheus가 정상화를 감지하면 점수가 부여됩니다.

해결에 걸린 시간과 사용한 힌트 수만큼 점수가 감점되고, 누적 점수로 티어가 올라갑니다.

## 주요 기능

### 고정 미션 (튜토리얼)

난이도 순으로 잠금이 풀리는 4개 미션으로, Kubernetes 장애 대응의 기본 패턴을 단계적으로 익힙니다.

| 레벨 | 미션 | 장애 유형 | 학습 내용 |
|---|---|---|---|
| 1 | 사라진 웹페이지 | ImagePullBackOff | 잘못된 이미지 태그 진단 및 수정 |
| 2 | 터져버린 쇼핑몰 | OOMKilled | 메모리 리소스 제한 조정 |
| 3 | 끊어진 연결고리 | Service 연결 실패 | Service selector와 Pod label의 관계 |
| 4 | 좀비 서버의 습격 | Readiness Probe 실패 | Pod 헬스체크와 엔드포인트 복구 |

### AI 장애 생성 모드

기본 4개 미션을 모두 끝내면 "AI 문제 더 풀기"가 열립니다. 고정된 시나리오를 반복하는 대신,
AI가 매번 새로운 장애를 만들어 무한 실습을 제공합니다.

- 난이도 선택 (Beginner / Intermediate / Advanced / Expert)
- AI가 시나리오 생성 → 백엔드 안전성 검사 → 사용자 네임스페이스에 실제 장애 주입
- 동적 검증 — 시나리오마다 다른 Kubernetes API / PromQL 조건으로 정상화 여부를 판단

AI는 시나리오와 검증 조건을 생성하는 역할만 하고, 클러스터에 직접 명령을 내리지 않습니다.
생성된 결과는 fault type allowlist, 네임스페이스 격리, PromQL 가드 등 백엔드 검사를 통과한 것만
실행됩니다. 전체 설계는 [agent.md](agent.md)에 정리되어 있습니다.

### 공통

- 사용자별 격리 네임스페이스 — 터미널 세션 생성 시 `user-{uuid}` 네임스페이스와 실습용 리소스 자동 생성
- 웹 터미널 — xterm.js + WebSocket 기반, `kubectl` 명령 전용
- AI 튜터 — 정답을 바로 주지 않고 관찰 유도에서 해결책 제시까지 단계적으로 힌트 제공, RAG 기반 지식 검색
- 게이미피케이션 — 티어(Bronze → DevOps Master), 업적, 리더보드, 스킬 점수
- 모니터링 — Prometheus, Grafana, Loki, Promtail, AlertManager 스택. 미션 진행 중 Grafana로 본인 네임스페이스의 Pod 메모리/CPU/엔드포인트 상태를 실시간 관찰

## 기술 스택

| 영역 | 기술 |
|---|---|
| Frontend | React 18, TypeScript, Vite, xterm.js |
| Backend | FastAPI, Python 3.11, SQLAlchemy async, PostgreSQL |
| AI | LangChain, OpenAI gpt-4o-mini / Google Gemini, Qdrant (RAG) |
| Infra | Kubernetes (Docker Desktop), Chaos Mesh |
| Monitoring | Prometheus, Grafana, Loki, Promtail, AlertManager |

## 프로젝트 구조

```
cloud-trouble-training-service/
├── frontend/             React + TypeScript 클라이언트 (터미널 / 미션 / 튜터 / 대시보드 UI)
├── backend/              FastAPI 백엔드 (미션, 터미널, AI 시나리오, 튜터, 채점)
│   └── CLAUDE.md         백엔드 API 및 서비스 상세
├── ai-data/              RAG 엔진과 지식 창고
│   ├── knowledge-base/   장애 대응 문서 (troubleshooting / commands / playbook)
│   ├── prompts/          소크라테스식 튜터 시스템 프롬프트
│   └── rag_service.py    Qdrant 기반 벡터 검색
├── ai-chatbot-widget/    독립 실행형 AI 튜터 챗봇 위젯
├── infra/
│   └── monitoring/       Prometheus, Grafana, Loki, AlertManager 설정
├── docs/                 API 가이드, 제안서 등 문서
├── agent.md              AI 장애 생성 모드 설계 및 구현 현황
├── CLAUDE.md             개발 가이드 및 구현 현황
└── docker-compose.yml    로컬 인프라 및 서비스 실행
```

## 로컬 실행 (권장 구성)

인프라는 Docker Compose로 띄우고, 백엔드와 프론트엔드는 직접 실행합니다.

사전 요구사항:

- Docker Desktop (Kubernetes 활성화)
- Helm (Chaos Mesh 설치용, `CHAOS_BACKEND=chaos_mesh`일 때)
- Python 3.11, Node.js 18+

```bash
# 1. Chaos Mesh 설치 (최초 1회, 실제 K8s 장애 주입을 쓸 때만)
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-testing --create-namespace \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock

# 2. 인프라 실행 (PostgreSQL + Qdrant)
docker compose up postgres qdrant -d

# 3. 백엔드 실행
cd backend
pip install -r requirements.txt
cp .env.example .env          # 환경변수 설정 후 편집
uvicorn app.main:app --reload --port 8000

# 4. 프론트엔드 실행
cd frontend
npm install
npm run dev
```

실행 후 접속 주소:

- 프론트엔드: http://localhost:3000
- API 문서 (Swagger): http://localhost:8000/docs

모든 백엔드는 `mock` 모드를 지원하므로, Kubernetes나 LLM API 키 없이도 전체 흐름을 확인할 수 있습니다.

### 모니터링 스택까지 함께 실행

```bash
docker compose --profile monitoring up -d

# Grafana:    http://localhost:3001  (admin / admin)
# Prometheus: http://localhost:9090
```

## 환경변수

`.env`의 주요 항목입니다. 전체 목록은 `backend/.env.example`를 참고하세요.

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival

# AI 백엔드 (mock: API 키 불필요 / openai, gemini: 실제 LLM 사용)
AI_BACKEND=mock              # mock | openai | gemini

# OpenAI 모드
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Gemini 모드
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.5-flash-lite

# 인프라 (mock: 로컬 개발 / chaos_mesh, k8s, prometheus: 실제 클러스터)
CHAOS_BACKEND=mock           # mock | chaos_mesh
VALIDATION_BACKEND=mock      # mock | k8s | prometheus
```

## 테스트

```bash
cd backend
python -m pytest tests/ -v
```

## 로드맵

이 프로젝트는 두 단계의 캡스톤으로 진행됩니다.

### 캡스톤 1 — Kubernetes 완성 (진행 중)

고정 미션 4개를 튜토리얼로 두고, 그 위에 AI 장애 생성 모드를 얹어 무한 실습을 제공하는 것이
핵심 목표입니다. 미션 시스템, AI 시나리오 생성·주입·검증, 소크라테스식 튜터, 게이미피케이션은
모두 동작하며, 남은 과제는 다음과 같습니다.

- cAdvisor 추가 — Pod의 실제 CPU/Memory/Network 사용량 메트릭 확보
- Gemini 완전 통합 — RAG(ai-data) 계층까지 Gemini 임베딩/추론 연결
- 검증 안정화 — `VALIDATION_BACKEND=k8s`, `prometheus` 실환경 테스트 강화
- 테스트 커버리지 확대

### 캡스톤 2 — 멀티 환경 고도화 (예정)

Kubernetes 외에 Docker-only, Linux, Application 환경을 탭으로 분리해 환경별 장애 유형을
다룹니다. 장애 주입기를 추상 클래스 기반으로 설계해 두어, 환경이 늘어나도 같은 구조로 확장할 수 있습니다.

## 참고 문서

- [agent.md](agent.md) — AI 장애 생성 모드 설계 및 구현 현황
- [CLAUDE.md](CLAUDE.md) — 개발 가이드 및 구현 현황
- [backend/CLAUDE.md](backend/CLAUDE.md) — 백엔드 API와 서비스 상세
