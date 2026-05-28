# 🤖 AI Chatbot Widget

Kubernetes 트러블슈팅을 위한 임베디드 AI 튜터 위젯입니다. iframe을 통해 어떤 웹페이지에도 쉽게 통합할 수 있습니다.

## ✨ 주요 기능

### 💡 4단계 힌트 시스템
- **Level 0 (일반 방향)**: 문제 해결의 일반적인 방향 제시 (점수 차감 없음)
- **Level 1 (구체적 조사)**: 구체적인 조사 방법과 체크포인트 (-5점)
- **Level 2 (정확한 명령어)**: 정확한 kubectl 명령어 제공 (-10점)
- **Level 3 (완전한 해결책)**: 완전한 해결 방법과 설명 (-50점)

### 🎯 소크라테스식 튜터링
- 학습자가 스스로 문제를 해결하도록 유도
- 질문을 통한 사고 과정 촉진
- 단계적 학습 지원

### 📊 점수 시스템
- 힌트 사용에 따른 점수 차감
- 학습 동기 부여 및 자기주도 학습 촉진
- 힌트 사용 횟수 추적

### 🔌 임베딩 기능
- iframe을 통한 간편한 통합
- PostMessage API로 부모 페이지와 통신
- 반응형 디자인 (모바일/태블릿/데스크톱)

## 🚀 시작하기

### 1. 의존성 설치

```bash
cd ai-chatbot-widget
npm install
```

### 2. 환경 설정

`.env.development` 파일을 생성하고 다음 내용을 추가하세요:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
VITE_WIDGET_TITLE=AI Tutor
VITE_WIDGET_THEME=purple
```

### 3. 개발 서버 실행

```bash
npm run dev
```

브라우저에서 http://localhost:3001 을 열어 확인하세요.

### 4. 프로덕션 빌드

```bash
npm run build
```

빌드된 파일은 `dist/` 폴더에 생성됩니다.

### 5. 빌드 미리보기

```bash
npm run preview
```

## 📦 임베딩 방법

### 기본 임베딩

```html
<iframe
  src="http://localhost:3001"
  width="100%"
  height="600px"
  frameborder="0"
  title="AI Chatbot"
></iframe>
```

### 반응형 임베딩

```html
<style>
  .chatbot-wrapper {
    width: 100%;
    max-width: 800px;
    height: 600px;
    margin: 0 auto;
  }
  
  .chatbot-wrapper iframe {
    width: 100%;
    height: 100%;
    border: none;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }
  
  @media (max-width: 768px) {
    .chatbot-wrapper {
      height: 500px;
    }
  }
</style>

<div class="chatbot-wrapper">
  <iframe src="http://localhost:3001" title="AI Chatbot"></iframe>
</div>
```

### PostMessage API 통신

부모 페이지에서 챗봇 이벤트를 수신할 수 있습니다:

```javascript
window.addEventListener('message', (event) => {
  // 보안: origin 체크 (프로덕션에서 필수)
  if (event.origin !== 'http://localhost:3001') return;

  if (event.data.type === 'CHATBOT_MESSAGE_SENT') {
    const { userMessage, aiMessage } = event.data.data;
    
    console.log('User:', userMessage.content);
    console.log('AI:', aiMessage.content);
    
    // 부모 페이지에서 추가 처리
    // 예: 분석, 로깅, UI 업데이트 등
  }
});
```

## 🎨 프로젝트 구조

```
ai-chatbot-widget/
├── public/              # 정적 파일
├── src/
│   ├── components/      # React 컴포넌트
│   │   ├── ChatWidget.jsx       # 메인 채팅 위젯
│   │   ├── ChatWidget.css
│   │   ├── ChatHeader.jsx       # 헤더 (힌트 레벨 표시)
│   │   ├── ChatHeader.css
│   │   ├── ChatMessages.jsx     # 메시지 목록
│   │   ├── ChatMessages.css
│   │   ├── ChatInput.jsx        # 입력 필드
│   │   ├── ChatInput.css
│   │   ├── HintPanel.jsx        # 힌트 패널
│   │   └── HintPanel.css
│   ├── App.jsx          # 메인 앱 (PostMessage API)
│   ├── App.css
│   ├── main.jsx         # 엔트리 포인트
│   └── index.css        # 글로벌 스타일
├── .env.example         # 환경 변수 템플릿
├── .env.development     # 개발 환경 설정
├── embed-example.html   # 임베딩 예제
├── index.html           # HTML 템플릿
├── vite.config.js       # Vite 설정
├── package.json
└── README.md
```

## 🧪 테스트 방법

### 1. 임베딩 예제 확인

개발 서버를 실행한 후, `embed-example.html` 파일을 브라우저에서 열어보세요:

```bash
# 개발 서버 실행
npm run dev

# 다른 터미널에서 예제 파일 열기
# Windows
start embed-example.html

# macOS
open embed-example.html

# Linux
xdg-open embed-example.html
```

### 2. 기능 테스트

- ✅ 메시지 전송 및 수신
- ✅ 힌트 레벨 증가/초기화
- ✅ 점수 차감 시스템
- ✅ PostMessage 이벤트 로깅
- ✅ 반응형 디자인 (모바일/태블릿/데스크톱)
- ✅ 키보드 단축키 (Enter: 전송, Shift+Enter: 줄바꿈)

## 🔧 기술 스택

- **React 18**: UI 라이브러리
- **Vite**: 빌드 도구 및 개발 서버
- **Axios**: HTTP 클라이언트
- **PostMessage API**: iframe 통신
- **CSS3**: 스타일링 (Flexbox, Grid, Animations)

## 🎯 향후 개선사항

### Backend 통합
- [ ] AI 엔진 API 연동 (`/ai-data/llm_client.py`)
- [ ] 실시간 응답 스트리밍
- [ ] 세션 관리 및 대화 히스토리 저장

### 기능 추가
- [ ] 다크 모드 지원
- [ ] 다국어 지원 (i18n)
- [ ] 음성 입력/출력
- [ ] 코드 하이라이팅
- [ ] 파일 첨부 기능
- [ ] 대화 내보내기 (PDF, TXT)

### 성능 최적화
- [ ] 메시지 가상화 (react-window)
- [ ] 이미지 lazy loading
- [ ] 번들 크기 최적화
- [ ] PWA 지원

### 보안 강화
- [ ] CORS 설정 강화
- [ ] XSS 방지
- [ ] CSP (Content Security Policy) 적용
- [ ] Rate limiting

## 📚 관련 문서

- [AI 엔진 README](../ai-data/README.md)
- [Backend API 문서](../backend/README.md)
- [Vite 공식 문서](https://vitejs.dev/)
- [React 공식 문서](https://react.dev/)

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.

## 💬 문의

문제가 발생하거나 질문이 있으시면 이슈를 등록해주세요.
