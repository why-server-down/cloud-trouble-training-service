# K8s Survival Camp

카오스 엔지니어링 + AI 튜터 + 게이미피케이션 기반 DevOps 장애 대응 훈련 플랫폼 (캡스톤 디자인)

## 핵심 메커니즘
1. Attack - Chaos Mesh가 사용자 Pod 공격
2. Defend - 사용자가 kubectl로 장애 해결 (AI 튜터가 소크라테스식 힌트 제공)
3. Score - Prometheus가 정상화 감지 → 점수 부여

## 기술 스택
- Frontend: React (xterm.js 터미널, 채팅 UI)
- Backend: FastAPI, SQLAlchemy async, PostgreSQL
- AI: LangChain + OpenAI (소크라테스식 튜터)
- Infra: Kubernetes, Chaos Mesh
- Monitoring: Prometheus

## 규칙
- 항상 한국어로 응답
- 커밋 메시지는 한국어로 작성
