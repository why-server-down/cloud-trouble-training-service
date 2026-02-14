# ☁️ Cloud Trouble Training Service

AI 기반 클라우드 장애 대응 훈련 플랫폼

## 📋 프로젝트 개요

Chaos Engineering과 AI를 결합하여 실전 같은 클라우드 장애 시뮬레이션 및 대응 훈련을 제공하는 플랫폼입니다.

## 🏗️ 프로젝트 구조

```
cloud-trouble-training-service/
├── 📂 frontend/            # [대시보드] React/Next.js 프로젝트
│   ├── src/
│   ├── public/
│   └── Dockerfile
│
├── 📂 backend/             # [두뇌 & 제어] FastAPI 프로젝트
│   ├── app/
│   │   ├── api/            # API 라우터
│   │   ├── core/           # FinOps 가상 로직, 설정 파일
│   │   ├── services/       # K8s 제어(Healing), Chaos 실행 로직
│   │   └── ai/             # ★ AI 관련 로직 (LangChain, Prompt)
│   ├── requirements.txt
│   └── Dockerfile
│
├── 📂 ai-data/             # [RAG 지식창고] AI가 참고할 문서들
│   ├── knowledge-base/     # PDF, MD 파일 (장애 대응 매뉴얼 등)
│   ├── vector-db/          # 로컬 벡터 DB 데이터 (ChromaDB 등)
│   └── prompts/            # 시스템 프롬프트 텍스트 파일들
│
├── 📂 infra/               # [훈련장] 인프라 설정 파일 모음
│   ├── k8s/                # Kubernetes Manifests
│   ├── chaos-mesh/         # ★ Chaos 실험 명세서
│   ├── monitoring/         # Prometheus, Grafana, Loki 설정
│   └── scripts/            # 자동화 쉘 스크립트
│
├── 📂 docs/                # [문서] 프로젝트 기획서, 발표자료
│   └── proposal.md
│
├── docker-compose.yml      # 로컬 전체 실행
├── README.md
└── .gitignore
```

## 🚀 빠른 시작

### 로컬 환경에서 실행

```bash
# 전체 서비스 실행
docker-compose up -d

# 프론트엔드: http://localhost:3000
# 백엔드 API: http://localhost:8000
# Grafana: http://localhost:3001
```

### 개별 서비스 실행

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## 🛠️ 기술 스택

- **Frontend**: React, Next.js
- **Backend**: FastAPI, Python
- **AI**: LangChain, ChromaDB (RAG)
- **Infrastructure**: Kubernetes, Chaos Mesh
- **Monitoring**: Prometheus, Grafana, Loki
- **Container**: Docker, Docker Compose

## 📚 주요 기능

- ⚡ Chaos Engineering 기반 장애 시뮬레이션
- 🤖 AI 기반 장애 분석 및 대응 가이드
- 📊 실시간 모니터링 및 메트릭 수집
- 💰 FinOps 최적화 제안
- 🔄 자동 복구(Self-Healing) 기능

## 📖 문서

자세한 내용은 [docs/proposal.md](docs/proposal.md)를 참고하세요.