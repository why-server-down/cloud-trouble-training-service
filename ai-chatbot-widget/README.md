# AI Chatbot Widget

점수 기반 AI 튜터 챗봇 위젯 - Backend API 연동 완료

## 🎯 개요

Kubernetes 트러블슈팅을 도와주는 소크라테스식 AI 튜터 챗봇입니다.
질문 횟수에 따라 점수가 차감되며, 힌트 레벨이 점진적으로 증가합니다.

## ✨ 주요 기능

### 1. 점수 시스템
- 시작 점수: 100점
- 질문 횟수별 차등 차감:
  - 1회 질문: -5점
  - 2회 질문: -10점
  - 3회 질문: -20점
  - 4회 이상: -40점
- 답 보기: 0점 처리

### 2. 힌트 레벨 (소크라테스식)
- **Level 0**: 방향만 제시 (일반적인 가이드)
- **Level 1**: 확인할 리소스 지목 (구체적인 영역)
- **Level 2**: 정확한 kubectl 명령어 제공
- **Level 3**: 전체 해결 방법 제공 (답 보기)

### 3. 모드 전환
- **데모 모드**: 시뮬레이션 응답 (Backend 불필요)
- **실제 API 모드**: Backend API와 실시간 통신

## 📁 파일 구조

```
ai-chatbot-widget/
├── demo-standalone.html    # 독립 실행형 챗봇 위젯
├── src/
│   └── api-client.js       # Backend API 클라이언트
└── README.md               # 이 파일
```

## 🚀 사용 방법

### 방법 1: 데모 모드 (기본)

Backend 서버 없이 즉시 테스트 가능합니다.

```bash
# 1. 브라우저에서 파일 열기
open ai-chatbot-widget/demo-standalone.html

# 또는 로컬 서버 실행
cd ai-chatbot-widget
python -m http.server 8080
# http://localhost:8080/demo-standalone.html 접속
```

**특징**:
- 시뮬레이션 응답 사용
- 질문 횟수별 다른 응답 제공
- 점수 시스템 동작 확인 가능

---

### 방법 2: 실제 API 모드

Backend API와 연동하여 실제 AI 응답을 받습니다.

#### Step 1: Backend 서버 실행

```bash
# Backend 서버 실행
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Step 2: 사용자 등록 및 로그인

```bash
# 회원가입
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass123"}'

# 로그인 (토큰 발급)
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=testuser&password=testpass123"

# Response:
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
#   "token_type": "bearer"
# }
```

#### Step 3: 미션 시작

```bash
# 미션 목록 조회
curl -X GET http://localhost:8000/api/missions/ \
  -H "Authorization: Bearer {YOUR_TOKEN}"

# 미션 시작
curl -X POST http://localhost:8000/api/missions/start \
  -H "Authorization: Bearer {YOUR_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"mission_id": "{MISSION_ID}"}'
```

#### Step 4: 챗봇 위젯 사용

1. 브라우저에서 `demo-standalone.html` 열기
2. 우측 상단 설정 패널에서 **"데모 모드" 체크 해제**
3. JWT 토큰 입력 프롬프트에 `access_token` 입력
4. 챗봇 사용 시작!

**특징**:
- 실제 AI 응답 (OpenAI GPT-4)
- RAG 기반 지식 검색 (Qdrant)
- 미션 상태 자동 로드
- 힌트 레벨별 맞춤 응답

---

## 🔧 API 클라이언트 사용법

`src/api-client.js`를 다른 프로젝트에서 사용할 수 있습니다.

### 기본 사용

```javascript
// API 클라이언트 초기화
const apiClient = new ChatAPIClient('http://localhost:8000');

// 로그인
const { access_token } = await apiClient.login('testuser', 'testpass123');

// 토큰 설정
apiClient.setToken(access_token);

// AI에게 질문
const response = await apiClient.sendMessage('Pod가 시작되지 않습니다', 0);
console.log(response.response);

// 미션 상태 조회
const status = await apiClient.getMissionStatus();
console.log(`현재 점수: ${status.current_score}`);
```

### 에러 처리

```javascript
try {
  const response = await apiClient.sendMessage('질문', 0);
  console.log(response);
} catch (error) {
  if (error instanceof APIError) {
    console.error(`API 에러 [${error.code}]: ${error.message}`);
    
    if (error.code === 'UNAUTHORIZED') {
      // 토큰 만료 - 재로그인 필요
    } else if (error.code === 'NOT_FOUND') {
      // 진행 중인 미션 없음
    } else if (error.code === 'NETWORK_ERROR') {
      // 네트워크 연결 실패
    }
  }
}
```

### 주요 메서드

| 메서드 | 설명 | 파라미터 | 반환값 |
|--------|------|----------|--------|
| `login(username, password)` | 로그인 및 토큰 발급 | username, password | `{access_token, token_type}` |
| `sendMessage(message, hintLevel)` | AI에게 질문 | message, hintLevel (0~3) | `{response, hint_level, mission_name}` |
| `getMissionStatus()` | 진행 중인 미션 상태 | - | `{attempt, elapsed_seconds, remaining_seconds, current_score}` |
| `getMissions()` | 미션 목록 조회 | - | `Mission[]` |
| `getProfile()` | 사용자 프로필 | - | `{id, username, created_at, missions_completed, total_score}` |
| `testConnection()` | 연결 테스트 | - | `boolean` |

---

## 🎨 커스터마이징

### 1. API URL 변경

```javascript
// demo-standalone.html 파일 수정
const API_BASE_URL = 'https://your-api-server.com';
```

### 2. 점수 시스템 변경

```javascript
// 점수 차감 규칙 수정
const penalties = [5, 10, 20, 40]; // 원하는 값으로 변경
```

### 3. 스타일 변경

CSS 변수를 수정하여 색상 테마를 변경할 수 있습니다:

```css
/* 그라데이션 색상 */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

/* 메시지 색상 */
.message.user .message-content {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
```

---

## 🧪 테스트

### 데모 모드 테스트

```bash
# 1. 브라우저에서 demo-standalone.html 열기
# 2. 질문 입력 및 응답 확인
# 3. 점수 차감 확인
# 4. 답 보기 버튼 테스트
```

### 실제 API 모드 테스트

```bash
# 1. Backend 서버 실행 확인
curl http://localhost:8000/health

# 2. 로그인 및 토큰 발급
# 3. 미션 시작
# 4. 챗봇 위젯에서 실제 API 모드로 전환
# 5. 질문 입력 및 AI 응답 확인
```

---

## 🐛 트러블슈팅

### 문제: "Backend API에 연결할 수 없습니다"

**원인**: Backend 서버가 실행되지 않았거나 URL이 잘못됨

**해결**:
```bash
# Backend 서버 실행 확인
curl http://localhost:8000/health

# 응답: {"status": "ok"}
```

### 문제: "인증이 필요합니다"

**원인**: JWT 토큰이 만료되었거나 잘못됨

**해결**:
```bash
# 1. localStorage에서 토큰 삭제
localStorage.removeItem('auth_token');

# 2. 재로그인
# 3. 새 토큰 입력
```

### 문제: "진행 중인 미션이 없습니다"

**원인**: 미션을 시작하지 않음

**해결**:
```bash
# 미션 시작
curl -X POST http://localhost:8000/api/missions/start \
  -H "Authorization: Bearer {YOUR_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"mission_id": "{MISSION_ID}"}'
```

---

## 📚 관련 문서

- [Backend API 문서](../backend/README.md)
- [AI Engine 문서](../ai-data/README.md)
- [전체 프로젝트 문서](../README.md)

---

## 🔄 업데이트 로그

### 2026-06-01
- ✅ Backend API 연동 완료
- ✅ API 클라이언트 구현 (`src/api-client.js`)
- ✅ 데모 모드 / 실제 API 모드 전환 기능
- ✅ 에러 처리 및 재시도 로직
- ✅ 연결 상태 표시 UI

### 이전 버전
- ✅ 점수 기반 챗봇 UI 구현
- ✅ 시뮬레이션 응답 시스템
- ✅ 힌트 레벨별 응답 차별화

---

## 📝 라이선스

이 프로젝트는 AfterFail의 일부입니다.

---

**작성일**: 2026-06-01  
**버전**: 2.0.0 (Backend API 연동)
