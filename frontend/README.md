# Frontend - K8s Survival Camp

React + TypeScript + Vite 기반 프론트엔드

## 시작하기

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
npm run build
```

## 프로젝트 구조

```
frontend/src/
├── components/
│   ├── Login/
│   │   ├── Login.tsx           # 로그인/회원가입
│   │   └── Login.css
│   ├── Mission/
│   │   ├── MissionList.tsx     # 미션 목록 + 진행/완료/잠금 상태
│   │   ├── MissionCard.tsx     # 개별 미션 카드
│   │   └── Mission.css
│   ├── Terminal/
│   │   ├── Terminal.tsx        # xterm.js 웹 터미널 (WebSocket)
│   │   └── Terminal.css
│   ├── Chat/
│   │   ├── ChatPanel.tsx       # AI 튜터 채팅 패널
│   │   └── Chat.css
│   └── Profile/
│       ├── DashboardOverview.tsx   # 학습 대시보드 (미션 없을 때)
│       ├── ProfileDetails.tsx      # 프로필 상세 (티어, 업적, 스킬)
│       └── Profile.css
├── services/
│   └── api.ts                  # API 클라이언트 (인증, 미션, 튜터, 대시보드)
├── App.tsx                     # 메인 앱 (레이아웃, 인증 상태, Grafana iframe)
├── App.css
├── main.tsx
└── index.css
```

## 화면 구성

```
┌─────────────────────────────────────────────────────────┐
│  K8s Survival Camp          [프로필]  [Namespace]  [로그아웃] │
├──────────────────┬──────────────────────────────────────┤
│  [미션] [터미널]  │                                        │
├──────────────────┤                                        │
│ 미션 목록         │  미션 진행 중:  xterm.js 터미널          │
│  Level 1 ✓      │                                        │
│  Level 2 ✓      ├──────────────────────────────────────┤
│  Level 3 ✓      │  미션 진행 중:  Grafana 대시보드 iframe  │
│  Level 4 🔒      │  미션 없을 때: 학습 대시보드 (통계/업적) │
│                  │                                        │
│ [AI 문제 더 풀기] │                                        │
│ (4개 완료 후 활성) │                                        │
└──────────────────┴──────────────────────────────────────┘
```

## 주요 기술

- **React 18** + **TypeScript**
- **Vite** - 빌드 도구
- **xterm.js** + **@xterm/addon-fit** - 터미널 에뮬레이터
- **WebSocket** - 터미널 실시간 연결

## 환경변수 (Vite)

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
VITE_GRAFANA_BASE_URL=http://localhost:3001
```

## AI 시나리오 UI (예정 - agent.md Phase 1)

기본 4개 미션 목록 아래에 `AI 문제 더 풀기` 영역 추가 예정:

```
Mission Page
  ├── 기본 미션 (Level 1~4)
  └── AI 문제 더 풀기 (4개 완료 시 활성화)
        ├── 난이도 선택 (Beginner / Intermediate / Advanced / Expert)
        ├── 시작 버튼
        └── 최근 AI 문제 기록
```

- `internal_summary`, `expected_solution`, `validation_json`은 프론트에 노출하지 않음
- 완료 전에는 `student_brief`, 난이도, 제한 시간, 학습 목표만 표시
- 기존 터미널/튜터 UI를 AI 시나리오와 공유
