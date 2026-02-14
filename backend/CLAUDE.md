# Backend - Cloud Trouble Training Service

## 개요
FastAPI 기반 백엔드. AI 장애 분석, K8s 제어, Chaos Engineering 실행, FinOps 로직을 담당.

## 기술 스택
- Python 3.11, FastAPI, Pydantic v2
- LangChain + ChromaDB (RAG)
- Kubernetes Python Client
- uvicorn (ASGI 서버)

## 프로젝트 구조
- `app/api/`       → API 라우터 (엔드포인트 정의)
- `app/ai/`        → AI 로직 (LangChain, RAG, 프롬프트 처리)
- `app/services/`  → 비즈니스 로직 (K8s 제어, Chaos 실행, Self-Healing)
- `app/core/`      → 설정, FinOps 로직, 공통 유틸

## 컨벤션
- PEP8 준수
- API 엔드포인트는 RESTful 규칙
- 타입 힌트 필수
- Pydantic 모델로 요청/응답 스키마 정의
- 환경 변수는 python-dotenv로 관리

## 실행
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 의존 서비스
- ChromaDB: localhost:8001 (벡터 DB)
- Prometheus: localhost:9090 (메트릭)
