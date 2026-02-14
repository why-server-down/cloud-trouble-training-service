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
├── models.py            # SQLAlchemy 모델 (User, TerminalSession, CommandLog)
├── schemas.py           # Pydantic 스키마 (요청/응답)
├── api/
│   ├── deps.py          # 의존성 (get_db, get_current_user)
│   ├── auth.py          # POST /api/auth/register, /api/auth/login
│   └── terminal.py      # WS /ws/terminal/{session_id}, POST /api/terminal/sessions
├── core/
│   ├── config.py        # Settings (환경변수)
│   ├── database.py      # async engine, session
│   └── security.py      # JWT, 비밀번호 해싱
├── services/
│   ├── command_validator.py  # kubectl 명령어 검증 (화이트리스트, 네임스페이스 격리)
│   ├── command_executor.py   # kubectl 비동기 실행 (5초 타임아웃)
│   └── websocket_handler.py  # WebSocket 연결, 명령어 파이프라인
└── ai/                  # AI 튜터 (미구현)
```

## API 엔드포인트
- `POST /api/auth/register` - 회원가입
- `POST /api/auth/login` - 로그인 (JWT 발급)
- `POST /api/terminal/sessions` - 터미널 세션 생성
- `WS /ws/terminal/{session_id}?token=JWT` - 웹 터미널

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
