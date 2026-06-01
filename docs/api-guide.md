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
Content-Type: application/x-www-form-urlencoded
```

**Request:**
```
username=student1&password=mypassword123
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

### 1-3. 로그아웃

```
POST /api/auth/logout
Authorization: Bearer {token}
```

**Response (204):** 빈 응답. 프론트엔드에서 localStorage의 토큰을 삭제해야 합니다.

---

### 1-4. 프로필 조회

```
GET /api/auth/me
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "student1",
  "created_at": "2026-02-14T12:00:00Z",
  "missions_completed": 3,
  "total_score": 270
}
```

---

### 1-5. 인증 토큰 사용법

로그인 후 받은 `access_token`을 모든 인증 필요 API에 헤더로 전달:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

토큰 만료 시간: **60분**

---

## 2. 터미널 세션

### 2-1. 세션 생성

터미널 WebSocket 연결 전에 반드시 세션을 먼저 생성해야 합니다.

> **K8s 자동 설정 포함:** 호출 시 사용자 전용 K8s 네임스페이스(`user-{uuid}`)와 nginx Deployment가 자동으로 생성됩니다. 이미 존재하면 스킵합니다.

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
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({ username: 'student1', password: 'pass123' })
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

## 5. 미션 시스템

### 5-1. 미션 목록 조회

```
GET /api/missions/
Authorization: Bearer {token}
```

**Response (200):**
```json
[
  {
    "id": "uuid-level-1",
    "name": "사라진 웹페이지",
    "level": 1,
    "description": "Nginx Pod가 ImagePullBackOff 상태입니다. 이미지 이름을 수정하여 Pod를 정상 상태로 복구하세요.",
    "chaos_type": "pod_failure",
    "base_score": 100,
    "time_limit": 1200,
    "hint_penalty": 5,
    "is_unlocked": true
  },
  {
    "id": "uuid-level-2",
    "name": "터져버린 쇼핑몰",
    "level": 2,
    "description": "애플리케이션 Pod가 메모리 부족으로 OOMKilled 되고 있습니다.",
    "chaos_type": "memory_stress",
    "base_score": 100,
    "time_limit": 1500,
    "hint_penalty": 7,
    "is_unlocked": false
  }
]
```

- `is_unlocked`: 이전 레벨 완료 시 `true`. Level 1은 항상 `true`
- `time_limit`: 제한 시간 (초 단위)

---

### 5-2. 미션 시작

```
POST /api/missions/start
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:**
```json
{
  "mission_id": "uuid-level-1"
}
```

**Response (201):**
```json
{
  "id": "attempt-uuid",
  "user_id": "user-uuid",
  "mission_id": "uuid-level-1",
  "status": "in_progress",
  "start_time": "2026-02-15T10:00:00Z",
  "end_time": null,
  "final_score": null,
  "hints_used": 0
}
```

**에러:**
| 코드 | 상황 |
|------|------|
| 400 | 이미 진행 중인 미션이 있음 |
| 400 | 이전 레벨 미완료 (잠금 상태) |
| 400 | 존재하지 않는 mission_id |

---

### 5-3. 미션 상태 조회

진행 중인 미션의 실시간 상태를 조회합니다. **주기적 폴링 권장 (5~10초).**

```
GET /api/missions/status
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "attempt": {
    "id": "attempt-uuid",
    "user_id": "user-uuid",
    "mission_id": "uuid-level-1",
    "status": "in_progress",
    "start_time": "2026-02-15T10:00:00Z",
    "end_time": null,
    "final_score": null,
    "hints_used": 1
  },
  "elapsed_seconds": 180,
  "remaining_seconds": 1020,
  "current_score": 89
}
```

- `current_score`: 현재 시점 점수 (시간 경과 + 힌트 감점 반영)
- `remaining_seconds`: 0이 되면 자동 실패 처리

**에러:**
| 코드 | 상황 |
|------|------|
| 404 | 진행 중인 미션 없음 |

---

### 5-4. 미션 해결 확인

사용자가 장애를 해결했다고 판단될 때 호출합니다.

```
POST /api/missions/check
Authorization: Bearer {token}
```

**Response - 미해결 (200):**
```json
{
  "attempt": { "...": "status: in_progress" },
  "message": "[MOCK] pod_failure 장애가 아직 해결되지 않았습니다."
}
```

**Response - 해결 완료 (200):**
```json
{
  "attempt": {
    "id": "attempt-uuid",
    "status": "completed",
    "end_time": "2026-02-15T10:05:30Z",
    "final_score": 90,
    "hints_used": 1
  },
  "message": "미션 완료! 점수: 90점"
}
```

---

### 5-5. 미션 포기

```
POST /api/missions/abandon
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "id": "attempt-uuid",
  "status": "abandoned",
  "final_score": 0,
  "end_time": "2026-02-15T10:10:00Z"
}
```

---

### 5-6. 힌트 사용

```
POST /api/missions/hint
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "id": "attempt-uuid",
  "hints_used": 2,
  "status": "in_progress"
}
```

힌트 사용 시 미션의 `hint_penalty`만큼 점수가 차감됩니다.

---

### 5-7. (Mock 전용) 수동 해결 트리거

개발/테스트용입니다. 실제 K8s 환경에서는 사용하지 않습니다.

```
POST /api/missions/debug/resolve
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "message": "user-{user_id} 장애 해결 처리됨"
}
```

이 API 호출 후 `POST /api/missions/check`를 하면 미션이 완료됩니다.

---

### 5-8. 미션 점수 규칙

| 항목 | 값 |
|------|-----|
| 기본 점수 | 100점 |
| 시간 감점 | 1분마다 -2점 |
| 힌트 감점 | Level 1: -5점, Level 2~3: -7점, Level 4: -10점 |
| 최소 보장 점수 | 20점 |
| 포기 시 | 0점 |
| 시간 초과 시 | 자동 실패 (20점) |

---

### 5-9. 프론트엔드 연동 흐름

```
1. GET /api/missions/         → 미션 목록 화면 (잠금/해제 표시)
2. POST /api/missions/start   → 미션 시작 → 터미널 화면 전환
3. GET /api/missions/status   → 5~10초마다 폴링 (점수, 남은 시간 표시)
4. POST /api/missions/hint    → 힌트 버튼 클릭 시
5. POST /api/missions/check   → "제출" 버튼 또는 자동 체크
6. POST /api/missions/abandon → "포기" 버튼 클릭 시
```

### 5-10. 코드 예시 (React)

```typescript
const API_BASE = 'http://localhost:8000';

// 미션 목록
const getMissions = async (token: string) => {
  const res = await fetch(`${API_BASE}/api/missions/`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.json();
};

// 미션 시작
const startMission = async (token: string, missionId: string) => {
  const res = await fetch(`${API_BASE}/api/missions/start`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ mission_id: missionId }),
  });
  return res.json();
};

// 상태 폴링
const pollStatus = async (token: string) => {
  const res = await fetch(`${API_BASE}/api/missions/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 404) return null; // 진행 중인 미션 없음
  return res.json();
};

// 해결 확인
const checkMission = async (token: string) => {
  const res = await fetch(`${API_BASE}/api/missions/check`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.json();
};
```

---

## 6. AI 튜터 채팅

> 진행 중인 미션이 있어야 사용 가능합니다.

### 6-1. AI 튜터에게 질문

```
POST /api/chat/
Authorization: Bearer {token}
Content-Type: application/json
```

**Request:**
```json
{
  "message": "Pod가 안 떠요. 어디서부터 확인해야 하나요?",
  "hint_level": 0
}
```

**힌트 레벨 기준:**
| 레벨 | 설명 | 예시 응답 |
|------|------|-----------|
| 0 | 방향만 제시 | "어떤 명령어로 Pod 상태를 볼 수 있을까요?" |
| 1 | 확인할 리소스 지목 | "describe와 get 중 어떤 게 더 자세한 정보를 줄까요?" |
| 2 | kubectl 명령어 제공 | "`kubectl describe pod <이름>`의 Events 섹션을 확인해보세요." |
| 3 | 전체 해결 방법 | 단계별 해결 방법 전체 제공 |

**Response (200):**
```json
{
  "response": "좋은 질문이에요! 현재 클러스터에서 어떤 일이 벌어지는지 전체적으로 볼 수 있는 방법이 뭐가 있을까요?",
  "hint_level": 0,
  "mission_name": "사라진 웹페이지"
}
```

**에러:**
| 코드 | 상황 |
|------|------|
| 400 | 진행 중인 미션 없음 |
| 401 | 인증 토큰 없음 |

---

### 6-2. 힌트 사용 + 채팅 연동 (프론트엔드 권장 패턴)

힌트 버튼을 누를 때 감점 처리(`hint` API)와 AI 응답(`chat` API)을 동시에 호출합니다.

```typescript
const useHintWithChat = async (token: string, hintLevel: number) => {
  // 1. 감점 처리
  await fetch(`${API_BASE}/api/missions/hint`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });

  // 2. AI 튜터 응답 받기
  const res = await fetch(`${API_BASE}/api/chat/`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message: "힌트 주세요", hint_level: hintLevel }),
  });
  return res.json();
};
```

---

## 7. 허용된 kubectl 명령어

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

## 7. 허용된 kubectl 명령어 (set image 추가)

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
| `kubectl set image` | 컨테이너 이미지 변경 (pod_failure 미션 fix용) |
| `kubectl patch` | 리소스 부분 수정 (memory_stress 미션 fix용) |

---

## 8. 로컬 개발 환경 실행

**사전 요구사항:**
- Docker Desktop (Kubernetes 활성화 필수)
- Chaos Mesh 설치: `helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-testing`

```bash
# 프로젝트 루트에서
docker compose up postgres -d

# 백엔드 실행
cd backend
pip install -r requirements.txt

# backend/.env 파일 생성
echo "CHAOS_BACKEND=chaos_mesh" > .env

uvicorn app.main:app --reload --reload-dir app --port 8000

# 확인
curl http://localhost:8000/health
# → {"status":"ok"}

# Swagger UI
open http://localhost:8000/docs
```
