# 환경변수 설정 가이드

## 개요
프론트엔드는 환경변수를 통해 API 서버 URL을 설정합니다. 이를 통해 로컬 개발, Docker, 프로덕션 환경에서 유연하게 대응할 수 있습니다.

## 환경변수 파일

### `.env.development` (개발 환경)
로컬 개발 시 자동으로 사용됩니다.
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```

### `.env.production` (프로덕션 환경)
빌드 시 사용됩니다.
```env
VITE_API_BASE_URL=http://your-production-api.com
VITE_WS_BASE_URL=ws://your-production-api.com
```

### `.env.local` (로컬 오버라이드)
개인 설정용 (Git에 커밋되지 않음)
```env
VITE_API_BASE_URL=http://192.168.1.100:8000
VITE_WS_BASE_URL=ws://192.168.1.100:8000
```

## Docker 환경 설정

Docker Compose를 사용하는 경우:

```env
VITE_API_BASE_URL=http://backend:8000
VITE_WS_BASE_URL=ws://backend:8000
```

또는 docker-compose.yml에서 환경변수 주입:

```yaml
services:
  frontend:
    build: ./frontend
    environment:
      - VITE_API_BASE_URL=http://backend:8000
      - VITE_WS_BASE_URL=ws://backend:8000
    ports:
      - "5173:5173"
```

## 사용 방법

### 1. 환경변수 파일 생성
```bash
cd frontend
cp .env.example .env.development
```

### 2. 필요에 따라 URL 수정
```env
# 로컬 개발
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000

# 다른 머신의 백엔드 사용
VITE_API_BASE_URL=http://192.168.1.100:8000
VITE_WS_BASE_URL=ws://192.168.1.100:8000

# Docker 환경
VITE_API_BASE_URL=http://backend:8000
VITE_WS_BASE_URL=ws://backend:8000
```

### 3. 개발 서버 실행
```bash
npm run dev
```

## 주의사항

1. **환경변수 변경 후 재시작 필요**
   - 환경변수를 변경한 후에는 개발 서버를 재시작해야 합니다.
   - `Ctrl+C` 후 `npm run dev` 재실행

2. **빌드 시점에 결정됨**
   - Vite는 빌드 시점에 환경변수를 번들에 포함시킵니다.
   - 런타임에 변경할 수 없으므로 환경별로 다시 빌드해야 합니다.

3. **VITE_ 접두사 필수**
   - Vite에서 환경변수를 사용하려면 `VITE_` 접두사가 필요합니다.
   - 예: `VITE_API_BASE_URL` (O), `API_BASE_URL` (X)

4. **보안**
   - `.env.local` 파일은 Git에 커밋되지 않습니다.
   - 민감한 정보는 `.env.local`에 저장하세요.

## 트러블슈팅

### 환경변수가 적용되지 않을 때
1. 개발 서버 재시작
2. 브라우저 캐시 삭제 (Ctrl+Shift+R)
3. `node_modules/.vite` 폴더 삭제 후 재시작

### CORS 에러가 발생할 때
백엔드의 CORS 설정을 확인하세요:
```python
# backend/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # 프론트엔드 URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### WebSocket 연결 실패
1. WebSocket URL 프로토콜 확인 (`ws://` 또는 `wss://`)
2. 백엔드 서버가 실행 중인지 확인
3. 방화벽 설정 확인
