# K8s Survival Camp - Spec Documentation

## 프로젝트 개요
카오스 엔지니어링과 AI 튜터를 결합한 게이미피케이션 기반 DevOps 장애 대응 훈련소

## Spec 목록

### 1. AI Tutor System (ai-tutor-system)
Context-Aware AI 튜터 시스템으로, 소크라테스식 문답법을 통해 학습을 유도합니다.

**핵심 기능:**
- Context Collection: 미션 정보, 파드 로그, 힌트 이력 수집
- Socratic Tutoring: 정답 대신 유도 질문 제공
- RAG-based Knowledge: Vector DB 기반 공식 문서 검색
- Hint Level Management: 3단계 힌트 시스템

**기술 스택:** LangChain, OpenAI API, ChromaDB, FastAPI

---

### 2. Chaos Mission System (chaos-mission-system)
Chaos Mesh를 활용한 실전 장애 시뮬레이션 및 미션 관리 시스템입니다.

**핵심 기능:**
- Mission Initialization: 자동 K8s 환경 구성
- Chaos Injection: 미션별 장애 주입 (Pod Failure, Memory Stress, Network Latency)
- Mission Validation: Prometheus 기반 자동 검증
- Time-based Scoring: 시간 기반 점수 시스템

**기술 스택:** Kubernetes, Chaos Mesh, Prometheus

---

### 3. Dashboard & Gamification (dashboard-gamification)
학습 데이터 시각화 및 게이미피케이션 요소를 제공하는 대시보드입니다.

**핵심 기능:**
- Real-time Scoring: 실시간 점수 표시
- Skill Radar Chart: 4대 역량 시각화
- Learning Curve: 성장 곡선 그래프
- Tier System: 5단계 티어 시스템
- Leaderboard: 실시간 순위표
- Achievement System: 업적 시스템

**기술 스택:** React, Chart.js/Recharts, WebSocket

---

### 4. Web Terminal Interface (web-terminal-interface)
브라우저 기반 kubectl 명령어 실행 환경입니다.

**핵심 기능:**
- Terminal Emulation: xterm.js 기반 터미널 UI
- Command Execution: kubectl 명령어 실행
- Namespace Isolation: 사용자별 네임스페이스 격리
- Command Whitelist: 보안을 위한 명령어 제한
- Real-time Collaboration: 터미널 세션 공유

**기술 스택:** xterm.js, WebSocket, FastAPI

---

### 5. User Authentication & Profile (user-authentication)
사용자 인증 및 프로필 관리 시스템입니다.

**핵심 기능:**
- User Registration: 회원가입 및 네임스페이스 자동 생성
- User Login: JWT 기반 인증
- Profile Management: 프로필 정보 관리
- Session Management: 세션 관리 및 보안

**기술 스택:** JWT, bcrypt, PostgreSQL

---

### 6. Monitoring & Observability (monitoring-observability)
시스템 모니터링 및 관측성 시스템입니다.

**핵심 기능:**
- Metrics Collection: K8s 메트릭 수집
- Mission Validation Metrics: 미션 완료 조건 검증
- Grafana Dashboard: 시스템 상태 시각화
- Log Aggregation: 중앙 로그 수집
- Alerting: 이상 상황 알림

**기술 스택:** Prometheus, Grafana, Loki, AlertManager

---

## 개발 우선순위

### Phase 1: 핵심 인프라 (2주)
1. User Authentication
2. Web Terminal Interface
3. Monitoring & Observability

### Phase 2: 미션 시스템 (3주)
4. Chaos Mission System (Level 1-2)
5. Mission Validation

### Phase 3: AI 튜터 (3주)
6. AI Tutor System (Context Collection + Socratic Tutoring)
7. RAG Knowledge Base

### Phase 4: 게이미피케이션 (2주)
8. Dashboard & Gamification
9. Leaderboard & Achievement

---

## 시작하기

각 spec 디렉토리의 `requirements.md` 파일을 참고하여 개발을 시작하세요.

```bash
# Spec 구조
.kiro/specs/
├── ai-tutor-system/
│   └── requirements.md
├── chaos-mission-system/
│   └── requirements.md
├── dashboard-gamification/
│   └── requirements.md
├── web-terminal-interface/
│   └── requirements.md
├── user-authentication/
│   └── requirements.md
└── monitoring-observability/
    └── requirements.md
```

## 다음 단계

1. 각 spec의 `requirements.md`를 검토
2. 우선순위에 따라 `design.md` 작성
3. `tasks.md`로 구체적인 구현 작업 정의
4. 개발 시작
