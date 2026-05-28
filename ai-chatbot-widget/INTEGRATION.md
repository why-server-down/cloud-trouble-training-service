# 🔌 Backend Integration Guide

이 문서는 AI Chatbot Widget을 Backend API와 통합하는 방법을 설명합니다.

## 📋 개요

현재 위젯은 시뮬레이션 응답을 사용하고 있습니다. 실제 AI 엔진과 통합하려면 다음 단계를 따르세요.

## 🔧 Backend API 요구사항

### 1. Chat Endpoint

**POST** `/api/chat`

**Request Body:**
```json
{
  "message": "Pod가 CrashLoopBackOff 상태입니다",
  "hint_level": 0,
  "session_id": "optional-session-id",
  "context": {
    "namespace": "default",
    "previous_messages": []
  }
}
```

**Response:**
```json
{
  "response": "Pod가 CrashLoopBackOff 상태라면...",
  "hint_level": 0,
  "suggestions": [
    "kubectl logs <pod-name>",
    "kubectl describe pod <pod-name>"
  ],
  "session_id": "session-123"
}
```

### 2. CORS 설정

Backend에서 다음 CORS 헤더를 설정해야 합니다:

```python
# FastAPI 예제
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],  # 프로덕션에서는 실제 도메인
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 🔨 Frontend 수정사항

### 1. API 클라이언트 생성

`src/services/api.js` 파일을 생성하세요:

```javascript
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const sendChatMessage = async (message, hintLevel, sessionId = null) => {
  try {
    const response = await apiClient.post('/api/chat', {
      message,
      hint_level: hintLevel,
      session_id: sessionId,
    })
    return response.data
  } catch (error) {
    console.error('API Error:', error)
    throw error
  }
}

export default apiClient
```

### 2. ChatWidget 컴포넌트 수정

`src/components/ChatWidget.jsx`의 `handleSendMessage` 함수를 다음과 같이 수정하세요:

```javascript
import { sendChatMessage } from '../services/api'

const ChatWidget = ({ config }) => {
  const [sessionId, setSessionId] = useState(null)
  
  // ... 기존 코드 ...

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: inputValue,
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setIsLoading(true)

    try {
      // 실제 API 호출
      const response = await sendChatMessage(
        inputValue,
        hintLevel,
        sessionId
      )
      
      // 세션 ID 저장
      if (response.session_id && !sessionId) {
        setSessionId(response.session_id)
      }
      
      const aiMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.response,
        timestamp: new Date(),
        hintLevel,
        suggestions: response.suggestions || [],
      }

      setMessages(prev => [...prev, aiMessage])

      // Notify parent window
      window.parent.postMessage({
        type: 'CHATBOT_MESSAGE_SENT',
        data: { userMessage, aiMessage }
      }, '*')

    } catch (error) {
      console.error('Error sending message:', error)
      
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: '죄송합니다. 메시지 전송 중 오류가 발생했습니다. 다시 시도해주세요.',
        timestamp: new Date(),
        isError: true,
      }
      
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  // ... 기존 코드 ...
}
```

## 🧪 통합 테스트

### 1. Backend 실행

```bash
cd ai-data
python -m uvicorn app.main:app --reload --port 8000
```

### 2. Frontend 실행

```bash
cd ai-chatbot-widget
npm run dev
```

### 3. 테스트 시나리오

1. **기본 메시지 전송**
   - 메시지 입력 후 전송
   - AI 응답 확인
   - 네트워크 탭에서 API 호출 확인

2. **힌트 레벨 변경**
   - 힌트 레벨 증가
   - 다음 메시지에서 변경된 레벨 적용 확인

3. **세션 유지**
   - 여러 메시지 전송
   - 세션 ID가 유지되는지 확인

4. **에러 처리**
   - Backend 중단 후 메시지 전송
   - 에러 메시지 표시 확인

## 🔐 보안 고려사항

### 1. Origin 검증

PostMessage 이벤트 수신 시 origin을 검증하세요:

```javascript
window.addEventListener('message', (event) => {
  // 프로덕션에서는 실제 도메인으로 변경
  const allowedOrigins = [
    'http://localhost:3001',
    'https://your-domain.com'
  ]
  
  if (!allowedOrigins.includes(event.origin)) {
    console.warn('Unauthorized origin:', event.origin)
    return
  }
  
  // 이벤트 처리
})
```

### 2. API 인증

필요한 경우 API 키 또는 JWT 토큰을 추가하세요:

```javascript
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${getAuthToken()}`,
  },
})
```

### 3. Rate Limiting

Backend에서 rate limiting을 구현하세요:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/chat")
@limiter.limit("10/minute")
async def chat(request: Request, data: ChatRequest):
    # 처리 로직
    pass
```

## 📊 모니터링

### 1. 에러 로깅

```javascript
const logError = (error, context) => {
  console.error('Error:', error)
  
  // 프로덕션에서는 에러 추적 서비스로 전송
  // 예: Sentry, LogRocket 등
  if (import.meta.env.PROD) {
    // sendToErrorTracking(error, context)
  }
}
```

### 2. 성능 모니터링

```javascript
const measureApiCall = async (apiCall) => {
  const startTime = performance.now()
  
  try {
    const result = await apiCall()
    const duration = performance.now() - startTime
    
    console.log(`API call took ${duration}ms`)
    return result
  } catch (error) {
    const duration = performance.now() - startTime
    console.error(`API call failed after ${duration}ms`)
    throw error
  }
}
```

## 🚀 프로덕션 배포

### 1. 환경 변수 설정

`.env.production` 파일 생성:

```env
VITE_API_BASE_URL=https://api.your-domain.com
VITE_WS_BASE_URL=wss://api.your-domain.com
VITE_WIDGET_TITLE=AI Tutor
VITE_WIDGET_THEME=purple
```

### 2. 빌드

```bash
npm run build
```

### 3. 배포

빌드된 `dist/` 폴더를 웹 서버에 배포하세요:

- **Nginx**: Static file serving
- **Vercel**: `vercel deploy`
- **Netlify**: `netlify deploy`
- **AWS S3 + CloudFront**: S3 업로드 후 CloudFront 배포

### 4. CDN 설정 (선택사항)

정적 파일을 CDN에 배포하여 성능을 향상시킬 수 있습니다.

## 📚 참고 자료

- [AI 엔진 구현](../ai-data/llm_client.py)
- [Prompt 엔진](../ai-data/prompt_engine.py)
- [Backend API 문서](../backend/README.md)
- [Axios 문서](https://axios-http.com/)
- [PostMessage API](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage)

## 💬 문의

통합 과정에서 문제가 발생하면 이슈를 등록해주세요.
