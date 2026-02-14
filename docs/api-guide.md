# Backend API 연동 가이드

> Base URL: `http://localhost:8000`
> Swagger UI: `http://localhost:8000/docs`

---

## 1. 인증 (Auth)

### 1-1. 회원가입

```
POST /api/auth/register
Content-Type: application/json
```

**Request:**
```json
{
  "username": "student1",
  "password": "mypassword123"
}
```

**Response (201):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "student1",
  "created_at": "2026-02-14T12:00:00Z"
}
```

**에러:**
| 코드 | 상황 |
|------|------|
| 409 | 이미 존재하는 username |

---

### 1-2. 로그인

```
POST /api/auth/login
Content-Type: application/json
```

**Request:**
```json
{
  "username": "student1",
  "password": "mypassword123"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**에러:**
| 코드 | 상황 |
|------|------|
| 401 | 잘못된 username 또는 password |

---

### 1-3. 인증 토큰 사용법

로그인 후 받은 `access_token`을 모든 인증 필요 API에 헤더로 전달:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

토큰 만료 시간: **60분**

---

## 2. 터미널 세션

### 2-1. 세션 생성

터미널 WebSocket 연결 전에 반드시 세션을 먼저 생성해야 합니다.

```
POST /api/terminal/sessions
Authorization: Bearer {token}
```

**Request:** 빈 body (없음)

**Response (201):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "namespace": "user-550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-02-14T12:05:00Z",
  "is_active": true
}
```

---

## 3. WebSocket 터미널 (핵심)

### 3-1. 연결

```
ws://localhost:8000/ws/terminal/{session_id}?token={access_token}
```

- `session_id`: 세션 생성 API에서 받은 id
- `token`: 로그인에서 받은 access_token (쿼리 파라미터로 전달)

**연결 실패 시 close code:**
| 코드 | 의미 |
|------|------|
| 4001 | 토큰 누락 또는 유효하지 않은 토큰 |

---

### 3-2. 연결 성공 시

서버가 웰컴 메시지를 보냅니다:

```json
{
  "type": "output",
  "data": "Connected to namespace: user-550e8400...\nType 'kubectl' commands to interact with your cluster.\n\n",
  "exit_code": 0,
  "execution_time": 0.0
}
```

---

### 3-3. 명령어 전송 (Client → Server)

```json
{
  "type": "command",
  "command": "kubectl get pods"
}
```

delete 명령어 확인 시:
```json
{
  "type": "command",
  "command": "kubectl delete pod my-pod",
  "confirmed": true
}
```

---

### 3-4. 서버 응답 (Server → Client)

**성공 응답:**
```json
{
  "type": "output",
  "data": "NAME          READY   STATUS    RESTARTS   AGE\nnginx-pod     1/1     Running   0          5m\n",
  "exit_code": 0,
  "execution_time": 234.5
}
```

**에러 응답:**
```json
{
  "type": "error",
  "message": "Command 'create' is not allowed"
}
```

**삭제 확인 요청:**
```json
{
  "type": "confirm",
  "message": "Delete operation requires confirmation",
  "command": "kubectl delete pod my-pod"
}
```

---

### 3-5. 메시지 타입 정리

| type | 방향 | 설명 |
|------|------|------|
| `command` | Client → Server | 명령어 전송 |
| `output` | Server → Client | 실행 결과 |
| `error` | Server → Client | 에러 메시지 |
| `confirm` | Server → Client | 삭제 확인 요청 (프론트에서 확인 UI 표시 후 `confirmed: true`로 재전송) |

---

## 4. 프론트엔드 연동 예시 (React + xterm.js)

### 4-1. 전체 흐름

```
1. 로그인 → access_token 저장
2. 세션 생성 (POST /api/terminal/sessions) → session_id 획득
3. WebSocket 연결 (ws://.../{session_id}?token=...)
4. xterm.js에 사용자 입력 캡처 → WebSocket으로 전송
5. WebSocket 응답 → xterm.js에 출력
```

### 4-2. 코드 예시

```typescript
// 1. 로그인
const loginRes = await fetch('http://localhost:8000/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'student1', password: 'pass123' })
});
const { access_token } = await loginRes.json();

// 2. 세션 생성
const sessionRes = await fetch('http://localhost:8000/api/terminal/sessions', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${access_token}` }
});
const { id: sessionId } = await sessionRes.json();

// 3. WebSocket 연결
const ws = new WebSocket(
  `ws://localhost:8000/ws/terminal/${sessionId}?token=${access_token}`
);

// 4. 서버 메시지 수신 → xterm.js에 출력
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.type) {
    case 'output':
      terminal.write(msg.data);
      break;
    case 'error':
      terminal.write(`\r\n\x1b[31mError: ${msg.message}\x1b[0m\r\n`);
      break;
    case 'confirm':
      // 확인 다이얼로그 표시
      if (window.confirm(msg.message)) {
        ws.send(JSON.stringify({
          type: 'command',
          command: msg.command,
          confirmed: true
        }));
      }
      break;
  }
};

// 5. 사용자 입력 → 서버로 전송
let currentLine = '';
terminal.onData((data) => {
  if (data === '\r') {  // Enter
    terminal.write('\r\n');
    ws.send(JSON.stringify({ type: 'command', command: currentLine }));
    currentLine = '';
  } else if (data === '\u007F') {  // Backspace
    if (currentLine.length > 0) {
      currentLine = currentLine.slice(0, -1);
      terminal.write('\b \b');
    }
  } else {
    currentLine += data;
    terminal.write(data);
  }
});
```

---

## 5. 허용된 kubectl 명령어

| 명령어 | 설명 |
|--------|------|
| `kubectl get` | 리소스 목록 조회 |
| `kubectl describe` | 리소스 상세 정보 |
| `kubectl logs` | 파드 로그 조회 |
| `kubectl edit` | 리소스 편집 |
| `kubectl apply` | 리소스 적용 |
| `kubectl delete` | 리소스 삭제 (확인 필요) |
| `kubectl exec` | 파드 내 명령 실행 |
| `kubectl port-forward` | 포트 포워딩 |
| `kubectl top` | 리소스 사용량 |
| `kubectl explain` | 리소스 필드 설명 |

**차단되는 패턴:** 파이프(`|`), 리다이렉트(`>`, `<`), 체이닝(`&&`, `;`), 커맨드 치환(`` ` ``, `$()`)

**네임스페이스:** 자동으로 사용자 전용 네임스페이스가 주입됩니다. 다른 네임스페이스 접근 시 차단됩니다.

---

## 6. 로컬 개발 환경 실행

```bash
# 프로젝트 루트에서
docker-compose up -d postgres

# 백엔드 실행
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 확인
curl http://localhost:8000/health
# → {"status":"ok"}

# Swagger UI
open http://localhost:8000/docs
```
