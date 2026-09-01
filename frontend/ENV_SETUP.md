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

## CORS: 어떤 origin 으로 열었는지가 중요하다

`api.ts` 의 `normalizeApiBaseUrl` 은 **`VITE_API_BASE_URL` 의 hostname 이 브라우저
주소창의 hostname 과 같고 포트가 8000 이면** base URL 을 빈 문자열로 접는다.
그러면 요청이 상대 경로로 나가 Vite dev proxy(또는 nginx)를 타고 **same-origin** 이
되므로 CORS 가 아예 관여하지 않는다.

hostname 이 다르면 그 접기가 일어나지 않고 **cross-origin 직접 호출**이 된다.
이때는 백엔드 `CORS_ORIGINS` 에 **페이지의 origin** 이 들어 있어야 한다.
예전에는 wildcard 라 전부 통과했지만 BE-23 에서 허용 목록으로 바뀌었다.

백엔드 기본값 (`.env.example`):

```env
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

| 브라우저 주소 | `VITE_API_BASE_URL` | 결과 |
|---|---|---|
| `http://localhost:3000` | `http://localhost:8000` | same-origin (proxy). CORS 무관 |
| `http://127.0.0.1:3000` | `http://localhost:8000` | **cross-origin.** `CORS_ORIGINS` 에 `http://127.0.0.1:3000` 추가 필요 |
| `http://192.168.1.100:3000` | `http://192.168.1.100:8000` | same-origin (proxy). CORS 무관 |
| `http://192.168.1.100:3000` | `http://localhost:8000` | **cross-origin.** LAN origin 추가 필요 |
| Docker (nginx) | `http://backend:8000` | same-origin (nginx proxy). CORS 무관 |

`localhost` 와 `127.0.0.1` 은 **다른 origin** 이다. 같은 `.env` 로 한쪽은 되고 한쪽은
막히는 형태이므로, CORS 오류가 나면 먼저 주소창의 origin 을 확인한다.

> `vite.config.ts` 는 `host: true` 라 LAN IP 로도 열린다. 팀 시연에서 다른 기기로
> 접속하려면 그 origin 을 `CORS_ORIGINS` 에 넣어야 한다 (백엔드 `.env`, 백엔드 담당 소유).

### Retry-After 가 안 읽히는 경우

`POST /api/chat/` 은 사용자당 분당 호출 제한이 있고(백엔드 `CHAT_RATE_LIMIT_PER_MINUTE`,
기본 12) 초과 시 429 와 `Retry-After` 헤더를 보낸다.

`Retry-After` 는 CORS-safelisted response header 가 **아니다.** cross-origin 경로에서는
백엔드가 `Access-Control-Expose-Headers` 에 넣어주지 않으면 JS 에서 `null` 로 읽힌다.
프론트는 이 경우 초를 만들어 표시하지 않고 "잠시 후 다시 질문할 수 있습니다"로만 안내하며,
그래도 재시도는 최소 시간 잠근다.

same-origin(proxy) 경로에서는 헤더가 그대로 읽혀 남은 초가 카운트다운으로 표시된다.

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
