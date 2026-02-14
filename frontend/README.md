# K8s Survival Camp - Frontend

React + TypeScript + Vite 기반 프론트엔드

## 🚀 시작하기

### 1. 패키지 설치
```bash
cd frontend
npm install
```

### 2. 개발 서버 실행
```bash
npm run dev
```

브라우저에서 http://localhost:3000 접속

### 3. 빌드
```bash
npm run build
```

## 📁 프로젝트 구조

```
frontend/
├── src/
│   ├── components/
│   │   └── Terminal/
│   │       ├── Terminal.tsx    # 터미널 컴포넌트
│   │       └── Terminal.css    # 터미널 스타일
│   ├── App.tsx                 # 메인 앱
│   ├── App.css
│   ├── main.tsx                # 진입점
│   └── index.css
├── public/
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## 🛠️ 사용 기술

- **React 18** - UI 라이브러리
- **TypeScript** - 타입 안전성
- **Vite** - 빌드 도구
- **xterm.js** - 터미널 에뮬레이터
