# 캡스톤디자인 II 프론트엔드 2학기 구현 계획

> 프로젝트: AfterFail - 멀티 레이어 클라우드 인프라 기반 지능형 장애 대응 훈련 플랫폼
> 작성 기준: 2026-08-26, `dev` 브랜치 `36b1415`
> 원문 기준: `서버가왜죽었조_캡스톤디자인II_계획서.pdf`
> 대상 기간: 2026학년도 2학기, 16주, 2주 단위 8개 스프린트
> 대상 범위: `frontend/` 구현과 프론트엔드가 의존하는 백엔드 API 계약

## 0. 이 문서의 사용법

이 문서는 단순 일정표가 아니라 AI 코딩 에이전트가 저장소를 읽고 바로 구현할 수 있도록 만든 실행 명세다. 구현할 때는 아래 규칙을 지킨다.

1. 한 번에 하나의 작업 ID만 구현한다. 예: `FE-03만 구현해라`.
2. 각 작업의 선행 조건이 충족되지 않았으면 임의의 목 데이터나 하드코딩으로 완료 처리하지 않는다.
3. 프론트엔드만 수정하는 작업은 `frontend/` 밖을 수정하지 않는다.
4. 백엔드 계약이 필요한 작업은 이 문서의 "API 계약"과 실제 FastAPI 스키마를 대조한 뒤 구현한다.
5. 기존 `fetch`, React state, xterm.js, 직접 작성한 SVG 차트를 재사용한다. Zustand, React Router, Axios, 차트 라이브러리는 추가하지 않는다.
6. 작업 종료 전 최소 `npm.cmd run build`를 실행한다. 해당 스프린트에 테스트 기반이 추가된 뒤에는 `npm.cmd test -- --run`도 실행한다.
7. 활성 미션, 터미널 연결, 인증 만료, 환경 전환은 데이터 손실 위험이 있으므로 성공 경로만 구현하지 말고 실패·재시도·복구 경로까지 완료한다.

AI에 전달할 기본 프롬프트는 다음과 같다.

```text
docs/frontend-capstone2-semester-plan.md를 읽고 [작업 ID]만 구현해라.
현재 저장소의 실제 코드를 먼저 확인하고, 문서와 코드가 충돌하면 현재 코드의 동작을 보존하면서
작업의 인수 조건을 만족시켜라. 불필요한 라이브러리와 전역 상태 관리 도구는 추가하지 마라.
변경 파일, 구현 내용, 실행한 검증, 남은 백엔드 의존성을 마지막에 보고해라.
```

---

## 1. 계획서에서 요구하는 프론트엔드 결과물

PDF 계획서가 프론트엔드에 직접 요구하는 결과물은 다음과 같다.

- Kubernetes, Docker, Linux, Application/DB 실습을 환경 탭으로 분리한다.
- 환경별 미션, 터미널, 장애 상태, 관측 화면을 하나의 일관된 훈련 흐름으로 제공한다.
- xterm.js 웹 터미널에서 선택한 환경에 맞는 명령을 실행한다.
- 현재 실습 환경과 시스템 상태를 반영한 AI 튜터를 제공한다.
- 환경별 학습 이력, MTTR, 힌트 사용, 점수, 레이더 차트, 성장 곡선을 통합 시각화한다.
- AI 튜터 응답 목표 1.5초, 자동 채점 결과 반영 목표 300ms를 사용자가 체감할 수 있도록 로딩·진행 상태를 제공한다.
- Host/Privileged 작업을 브라우저에서 직접 실행하지 않고 백엔드 샌드박스와 RBAC 경계 안에서만 요청한다.

### 현재 저장소와 계획서의 범위 충돌

PDF는 `Application/DB`까지 최종 목표에 포함하지만, 현재 `CLAUDE.md`, `README.md`, `agent.md`, `backend/app/core/environments.py`는 캡스톤 II 범위를 `Kubernetes | Docker | Linux` 3종으로 확정하고 Application을 제외한다.

따라서 이 문서의 구현 기준은 다음과 같이 고정한다.

- 필수 제출 범위: Kubernetes, Docker, Linux.
- 조건부 확장 범위: Application/DB. 4주차 범위 검토에서 지도교수·팀 합의와 백엔드 실행 환경이 확보될 때만 착수한다.
- 범위 확장 전에는 Application 탭을 "개발 예정"으로 계속 노출하지 않는다. 사용자가 실제 제공 기능으로 오해하지 않도록 숨기거나 "후속 연구"로 명시한다.
- PDF를 수정 제출해야 한다면 이 불일치는 팀 차원에서 별도로 정정한다. 프론트엔드가 가짜 Application 화면을 만드는 것으로 문서 불일치를 덮지 않는다.

---

## 2. 현재 프론트엔드 기준선

### 2.1 기술 스택

| 구분 | 현재 값 | 2학기 원칙 |
|---|---|---|
| UI | React 18 + TypeScript + Vite 5 | 유지 |
| 터미널 | xterm.js + fit addon | 환경별 설정만 일반화 |
| API | 브라우저 `fetch` 기반 `src/services/api.ts` | 유지, 공통 오류 처리 재사용 |
| 상태 | `useState`, `useEffect`, localStorage | 유지, 전역 상태 라이브러리 추가 금지 |
| 차트 | React에서 직접 생성한 SVG | 유지, 차트 라이브러리 추가 금지 |
| 스타일 | 컴포넌트별 CSS + `App.css` | 기존 디자인 언어 유지 |
| 테스트 | 자동화 테스트 없음 | Vitest 기반 최소 단위·컴포넌트 테스트 추가 |
| 빌드 | `npm.cmd run build` 통과 | 모든 PR 필수 |
| 린트 | 스크립트는 있으나 설정 파일이 없어 실패 | Sprint 0에서 설정 복구 |

### 2.2 이미 구현되어 재사용할 기능

- 회원가입, 로그인, 로그아웃, JWT 만료 처리.
- 사용자 프로필, 누적 점수, 완료 미션 수.
- Kubernetes 고정 미션 4개 목록·잠금·시작·상태 폴링·검증·포기·힌트.
- AI 동적 시나리오 난이도 선택, 잠금 해제, 시작·검증·포기·힌트.
- AI 튜터 채팅과 단계별 힌트 감점 연결.
- xterm.js 터미널, 명령 기록, 자동 완성, 삭제 확인, WebSocket 3회 재연결.
- Grafana iframe과 Prometheus 데이터 준비 상태 확인.
- 티어, 4축 역량 레이더, 학습 곡선, 리더보드, 업적.
- 모바일에서 미션/터미널 탭 전환, 온보딩 투어, Toast, ConfirmModal.

### 2.3 현재 코드의 핵심 결손

| 영역 | 현재 상태 | 필요한 변경 |
|---|---|---|
| 환경 탭 | Docker/Linux/Application은 WIP 화면 | 백엔드 가용성 기반 실제 환경 전환 |
| 프론트 타입 | Mission, Session, Scenario에 `environment`가 없음 | 공통 `EnvironmentId`와 API 응답 타입 추가 |
| 미션 목록 | 환경 필터 없이 전체 조회 | 선택 환경을 쿼리로 전달하고 응답도 검증 |
| AI 시나리오 | `startRandomScenario()`가 environment를 보내지 않음 | 선택 환경 전달, 응답 환경 불일치 차단 |
| 터미널 세션 | 로그인 직후 Kubernetes 세션 1개를 무조건 생성 | 환경별 지연 생성과 세션 캐시/정리 |
| 터미널 명령 | kubectl 전용 프롬프트·자동완성 | kubectl/docker/linux 명령 프로필 분리 |
| 활성 미션 | 환경 전환과 활성 미션 관계가 없음 | 미션 중 환경 전환 잠금, 새로고침 복원 |
| 관측 화면 | K8s Grafana UID와 PromQL이 하드코딩됨 | 환경별 dashboard UID와 readiness query |
| 대시보드 | 전체 합계이며 환경 필터·환경별 MTTR 없음 | 환경별 통계·역량·성장 곡선 |
| AI 튜터 | 응답의 `sources`, `observations_used`를 표시하지 않음 | 근거/관측 정보 접기 UI, 환경 배지 |
| 품질 | ESLint 설정·테스트 없음 | CI에서 build/lint/test 실행 가능 상태 |

### 2.4 백엔드의 현재 멀티 환경 진행 상태

- `Mission`, `GeneratedScenario`, `TerminalSession` DB 모델에는 `environment`가 있다.
- Pydantic 스키마에도 environment 기본값이 있다.
- `SUPPORTED_ENVIRONMENTS`는 kubernetes, docker, linux다.
- `IMPLEMENTED_ENVIRONMENTS`는 현재 kubernetes 하나뿐이다.
- AI 시나리오 시작 API는 environment를 받을 수 있지만 프론트가 보내지 않는다.
- 미션 목록 API는 `MissionResponse` 생성 시 DB의 environment를 넘기지 않아 현재는 기본값 kubernetes로만 응답한다.
- 터미널 세션 생성 API는 environment 요청 본문을 받지 않고 Kubernetes namespace만 만든다.
- WebSocket 명령 실행과 runtime context는 Kubernetes 전용이다.
- 대시보드 API는 환경 필터와 환경별 집계를 지원하지 않는다.

즉, 프론트 탭만 먼저 활성화하면 Docker/Linux처럼 보이지만 실제 명령과 장애는 Kubernetes에서 실행되는 치명적인 불일치가 생긴다. 환경별 백엔드 준비 상태가 확인되기 전에는 탭을 활성화하면 안 된다.

---

## 3. 2학기 완료 정의

### 3.1 사용자 관점 완료 흐름

1. 로그인하면 마지막으로 사용한 환경 또는 Kubernetes가 선택된다.
2. 사용 가능한 환경만 진입할 수 있고 준비 중인 환경은 이유와 예상 기능을 읽을 수 있다.
3. 환경을 선택하면 해당 환경의 미션만 표시되고 터미널 세션은 필요할 때 생성된다.
4. 미션을 시작하면 환경 탭이 잠기고, 같은 환경의 터미널·AI 튜터·관측 화면이 열린다.
5. 사용자는 Kubernetes에서는 kubectl, Docker에서는 docker CLI, Linux에서는 제한된 shell 명령으로 조사·복구한다.
6. 검증 결과와 현재 점수는 중복 요청 없이 화면에 반영된다.
7. AI 튜터는 현재 환경 배지, 사용한 관측 정보, 참고 문서를 함께 보여준다.
8. 미션이 완료·실패·포기되면 세션 상태가 정리되고 환경 전환이 다시 열린다.
9. 프로필에서 전체 또는 환경별 완료 수, 평균 MTTR, 점수, 힌트, 역량 레이더, 성장 곡선을 볼 수 있다.
10. 새로고침, 네트워크 단절, 인증 만료, WebSocket 재연결 후에도 잘못된 환경에서 명령을 보내지 않는다.

### 3.2 기술적 완료 조건

- `EnvironmentId = 'kubernetes' | 'docker' | 'linux'`가 프론트 전체의 단일 타입이다.
- 환경 라벨, 명령 예시, 터미널 프롬프트, 관측 설정은 하나의 config에서 관리한다.
- 활성 attempt와 terminal session은 environment가 일치하지 않으면 UI를 열지 않는다.
- 미션 중에는 환경 전환을 막거나 명시적 포기 확인을 거친다. 자동 포기는 금지한다.
- API 요청은 abort/cleanup을 지원해 환경 전환 뒤 이전 환경 응답이 화면을 덮지 않는다.
- 폴링은 탭 비활성·attempt 종료·컴포넌트 unmount 시 중지한다.
- 새 runtime dependency 없이 구현한다.
- `build`, `lint`, `test`가 모두 통과한다.
- 1366x768, 768x1024, 390x844에서 핵심 흐름을 완료할 수 있다.
- 버튼, 탭, 모달, 채팅, 차트에 키보드 접근과 읽을 수 있는 label이 있다.

### 3.3 하지 않을 것

- 브라우저에서 Docker socket, host shell, Kubernetes API를 직접 호출하지 않는다.
- 프론트에서 점수를 계산해 확정하지 않는다. 서버 응답을 유일한 기준으로 사용한다.
- 환경마다 MissionList, Terminal, TutorChat을 복제하지 않는다.
- 환경별 CSS 파일을 통째로 복제하지 않는다. 배지 색과 소수의 토큰만 config/class로 바꾼다.
- 백엔드가 준비되지 않은 기능을 localStorage mock으로 완료 처리하지 않는다.
- Redux/Zustand, Axios, React Router, Recharts 같은 의존성을 추가하지 않는다.

---

## 4. 프론트엔드가 요구할 백엔드 API 계약

이 절은 프론트 구현 전 백엔드 담당자와 합의해야 하는 최소 계약이다. 실제 FastAPI 스키마가 다르면 프론트만 임의로 맞추지 말고 이 계약을 먼저 갱신한다.

### API-01 환경 가용성

```http
GET /api/environments
Authorization: Bearer {token}
```

```json
{
  "items": [
    {
      "id": "kubernetes",
      "status": "available",
      "capabilities": ["static_mission", "ai_scenario", "terminal", "tutor", "observability"]
    },
    {
      "id": "docker",
      "status": "preparing",
      "capabilities": []
    },
    {
      "id": "linux",
      "status": "preparing",
      "capabilities": []
    }
  ]
}
```

- `status`: `available | degraded | preparing | disabled`.
- 라벨과 설명은 프론트 config가 담당하고, 서버는 실제 가용성과 capability만 제공한다.
- API가 실패하면 Kubernetes만 기본 제공한다고 가정하지 않는다. 재시도 가능한 오류 상태를 보여준다.

### API-02 환경별 터미널 세션

```http
POST /api/terminal/sessions
Content-Type: application/json
Authorization: Bearer {token}

{"environment":"docker"}
```

```json
{
  "id": "uuid",
  "namespace": "user-uuid",
  "environment": "docker",
  "created_at": "2026-09-01T00:00:00Z",
  "is_active": true
}
```

- 요청 환경이 미구현이면 400과 사람이 읽을 수 있는 `detail`을 반환한다.
- 응답 environment가 요청과 다르면 프론트는 세션을 폐기하고 오류를 표시한다.
- 로그아웃·만료 세션 정리를 위해 다음 중 하나를 확정한다.
  - 권장: `DELETE /api/terminal/sessions/{session_id}` -> 204.
  - 대안: 새 세션 생성 시 동일 사용자의 이전 동일 환경 세션을 서버가 비활성화한다.

### API-03 환경별 고정 미션

```http
GET /api/missions/?environment=linux
Authorization: Bearer {token}
```

각 항목에 반드시 다음 필드를 포함한다.

```json
{
  "id": "uuid",
  "name": "디스크가 멈춘 서버",
  "environment": "linux",
  "level": 1,
  "description": "...",
  "chaos_type": "disk_io_stress",
  "base_score": 100,
  "time_limit": 1200,
  "hint_penalty": 5,
  "is_unlocked": true
}
```

- 현재 `backend/app/api/missions.py`에서 누락된 `environment=m["mission"].environment` 전달을 먼저 고친다.
- 미션 시작 응답 또는 상태 응답에도 environment를 포함해 새로고침 복원이 가능해야 한다.

### API-04 환경별 AI 시나리오

기존 엔드포인트를 유지하고 요청·응답의 environment를 실제로 사용한다.

```http
POST /api/scenarios/start-random

{"difficulty":"beginner","environment":"linux","randomize":true,"demo_unlock":false}
```

- `GET /api/scenarios/status` 응답의 environment는 필수다.
- 현재 프론트 `startRandomScenario()`에 environment 인자를 추가한다.
- 선택 탭과 응답 environment가 다르면 활성 시나리오로 채택하지 않는다.

### API-05 통합 상태 식별

기존 정적 미션과 AI 시나리오 상태 API를 유지해도 되지만 두 응답 모두 아래 필드를 제공한다.

```json
{
  "attempt": {
    "id": "uuid",
    "attempt_type": "static_mission",
    "status": "in_progress",
    "environment": "docker"
  },
  "elapsed_seconds": 120,
  "remaining_seconds": 1080,
  "current_score": 96
}
```

브라우저 localStorage의 `activeAttemptType`은 복원 힌트일 뿐 서버 상태보다 우선하지 않는다.

### API-06 환경별 분석

기존 API에 optional query를 추가한다.

```http
GET /api/dashboard/stats?environment=all
GET /api/dashboard/learning-curve?environment=docker
```

통합 통계에는 최소 다음 구조를 추가한다.

```json
{
  "total_score": 830,
  "missions_completed": 10,
  "total_time_spent": 7200,
  "hints_used": 8,
  "environment_stats": {
    "kubernetes": {"completed": 4, "average_score": 88, "average_mttr": 520, "hints_used": 2, "competency": 82},
    "docker": {"completed": 3, "average_score": 79, "average_mttr": 680, "hints_used": 3, "competency": 71},
    "linux": {"completed": 3, "average_score": 76, "average_mttr": 740, "hints_used": 3, "competency": 67}
  }
}
```

학습 곡선 각 항목에도 `environment`를 추가한다.

### API-07 AI 튜터 근거

현재 `ChatResponse` 스키마에 이미 정의된 필드를 실제 응답하고 프론트에서 사용한다.

```json
{
  "response": "...",
  "hint_level": 1,
  "mission_name": "...",
  "sources": [{"title":"Docker network troubleshooting","path":"...","environment":"docker"}],
  "observations_used": ["docker ps: app exited", "network inspect: bridge missing"]
}
```

### API-08 관측 설정

초기 구현은 프론트 config의 환경별 Grafana UID와 Prometheus query를 사용한다. 운영 배포에서 UID가 자주 바뀐다면 API-01 항목에 `observability` 객체를 추가한다. 프론트 코드에 URL 전체를 하드코딩하지 않는다.

---

## 5. 목표 프론트엔드 구조

### 5.1 공통 타입

새 파일 `frontend/src/types/training.ts`를 만든다.

```ts
export type EnvironmentId = 'kubernetes' | 'docker' | 'linux'
export type EnvironmentStatus = 'available' | 'degraded' | 'preparing' | 'disabled'
export type AttemptType = 'static_mission' | 'ai_scenario'

export interface EnvironmentAvailability {
  id: EnvironmentId
  status: EnvironmentStatus
  capabilities: Array<'static_mission' | 'ai_scenario' | 'terminal' | 'tutor' | 'observability'>
}
```

- `api.ts`, `App.tsx`, Mission, Scenario, Session 타입이 이 타입을 import한다.
- 같은 union을 여러 파일에 다시 선언하지 않는다.
- 알 수 없는 environment 응답은 TypeScript cast로 통과시키지 말고 API 경계에서 오류로 처리한다.

### 5.2 환경 config

새 파일 `frontend/src/config/environments.ts`를 만든다.

```ts
interface EnvironmentConfig {
  id: EnvironmentId
  label: string
  subtitle: string
  terminalLabel: string
  promptLabel: string
  commandSuggestions: string[]
  grafanaDashboardUid: string
  prometheusReadinessQuery: (scope: string) => string
}
```

필수 값:

| 환경 | terminalLabel | 명령 예시 | 관측 준비 쿼리 방향 |
|---|---|---|---|
| kubernetes | `SHELL / KUBECTL` | `kubectl get pods`, `kubectl describe`, `kubectl logs` | namespace의 pod 상태 |
| docker | `SHELL / DOCKER` | `docker ps -a`, `docker inspect`, `docker logs`, `docker network ls`, `docker volume ls` | sandbox container 상태 |
| linux | `SHELL / LINUX` | `ps`, `free -m`, `df -h`, `journalctl`, `dmesg`, `top` | sandbox process/node exporter 상태 |

명령 허용 여부는 백엔드가 결정한다. 프론트 commandSuggestions는 자동완성과 교육용 예시일 뿐 보안 수단이 아니다.

### 5.3 상태 소유권

`App.tsx`가 다음 상태만 소유한다.

```ts
activeEnvironment
environmentAvailability
sessionsByEnvironment
activeAttemptSummary
activeWorkspaceTab
auth/profile/tour state
```

- MissionList는 `environment`를 prop으로 받고 그 환경의 미션·시나리오만 관리한다.
- Terminal은 `environment`, 해당 환경 sessionId, token을 받는다.
- DashboardOverview는 `environment: EnvironmentId | 'all'`을 받는다.
- 환경 세션 생성·캐시는 `src/hooks/useEnvironmentSessions.ts`로 분리한다.
- 전체 앱 상태 라이브러리는 만들지 않는다.

### 5.4 환경 전환 규칙

```text
탭 클릭
  -> 서버 가용성 확인
  -> 활성 attempt가 없으면 activeEnvironment 변경
  -> 해당 환경 세션이 없고 terminal capability가 있으면 지연 생성
  -> 미션/대시보드 재조회

활성 attempt가 있으면
  -> 다른 탭 비활성화
  -> "현재 미션을 완료하거나 포기한 뒤 환경을 변경하세요" 안내
  -> 탭 클릭만으로 미션을 포기하지 않음
```

### 5.5 최소 파일 변경 계획

| 파일 | 작업 |
|---|---|
| `src/types/training.ts` | 공통 환경·attempt 타입 신규 |
| `src/config/environments.ts` | 환경별 표시·터미널·관측 설정 신규 |
| `src/services/api.ts` | 환경 타입 반영, API-01~07 클라이언트 |
| `src/hooks/useEnvironmentSessions.ts` | 환경별 세션 지연 생성·재사용·오류 처리 신규 |
| `src/App.tsx` | WIP 분기 제거, 환경 상태와 workspace 연결 |
| `src/components/Mission/MissionList.tsx` | environment prop, 필터, 복원, AI 시나리오 전달 |
| `src/components/Mission/MissionCard.tsx` | 환경 배지와 올바른 key/상태 표시 |
| `src/components/Mission/MissionStatus.tsx` | 환경 표시, 폴링 cleanup, 종료 콜백 |
| `src/components/Mission/TutorChat.tsx` | environment 배지, sources/observations, 취소 처리 |
| `src/components/Terminal/Terminal.tsx` | 환경별 prompt/자동완성/label |
| `src/hooks/useTerminalWebSocket.ts` | 환경 일치 검증, stale 연결 차단 |
| `src/utils/terminal.ts` | environment를 받는 prompt 함수 |
| `src/components/Profile/DashboardOverview.tsx` | 환경 필터·MTTR·환경 레이더·성장 곡선 |
| 기존 CSS 파일 | 기존 디자인 토큰을 유지한 상태·반응형·접근성 스타일 |

`App.tsx`와 `MissionList.tsx`가 각각 498줄, 676줄이므로 기능을 더 넣기 전에 위 두 hook/config만 분리한다. 단순 JSX를 파일 수를 늘리기 위해 분리하지 않는다.

---

## 6. 스프린트별 구현 계획

## Sprint 0 - 1~2주차: 기준선 고정과 환경 도메인 연결

### 목표

현재 Kubernetes 기능을 깨뜨리지 않고 멀티 환경 구현의 타입·계약·검증 기반을 만든다.

### FE-00 범위와 API 계약 확정

선행 조건: 없음.

구현/협의 내용:

- 팀 회의에서 필수 환경을 Kubernetes/Docker/Linux로 확정한다.
- Application/DB는 조건부 확장으로 이슈를 분리한다.
- API-01~08의 요청·응답 예시를 백엔드 담당자와 검토한다.
- 각 환경의 Grafana UID, Prometheus readiness query, 터미널 허용 명령 목록의 소유자를 정한다.
- GitHub 이슈에 backend dependency label을 만들고 프론트 작업과 연결한다.

완료 조건:

- 모든 환경의 session, mission, scenario, status 응답에 environment가 어떻게 전달되는지 합의되어 있다.
- 준비 중 환경을 프론트가 식별할 방법이 있다.
- Application/DB 포함 여부가 문서로 결정되어 있다.

### FE-01 공통 타입과 API 응답 동기화

수정 파일:

- 신규 `frontend/src/types/training.ts`
- `frontend/src/services/api.ts`
- `frontend/src/App.tsx`
- `frontend/src/components/Mission/MissionList.tsx`

구현 지시:

- `EnvironmentId`, `AttemptType`, availability 타입을 추가한다.
- `SessionResponse`, `MissionResponse`, `ScenarioResponse`, `ScenarioStatusResponse`, attempt/status 타입에 environment를 반영한다.
- 외부에서 사용하는 응답 타입은 export한다.
- API 응답 environment를 검사하는 `isEnvironmentId()` type guard를 추가한다.
- 아직 UI 동작은 Kubernetes로 유지한다.
- `startRandomScenario(token, difficulty, environment, demoUnlock)` 시그니처로 바꾸고 호출부를 모두 수정한다.

인수 조건:

- 프론트 코드에 별도의 `'kubernetes' | 'docker' | 'linux'` 중복 union이 없다.
- 잘못된 environment 문자열이 오면 사용자에게 API 오류가 표시된다.
- Kubernetes 고정 미션과 AI 시나리오 시작이 기존처럼 동작한다.
- `npm.cmd run build`가 통과한다.

### FE-02 lint와 최소 테스트 기반

수정 파일:

- 신규 `frontend/eslint.config.js` 또는 현재 ESLint 8과 호환되는 `.eslintrc.cjs`
- `frontend/package.json`
- 신규 `frontend/vitest.config.ts`
- 신규 `frontend/src/config/environments.test.ts`
- 신규 `frontend/src/services/api.test.ts`

구현 지시:

- 현재 설치된 ESLint 8 플러그인만 사용해 lint 설정을 복구한다.
- 테스트를 위해 Vitest, jsdom, React Testing Library만 dev dependency로 추가한다. 런타임 dependency는 추가하지 않는다.
- environment type guard, config 완전성, API body에 environment가 포함되는지를 우선 테스트한다.
- fetch mock은 테스트 파일 내부에서 `vi.stubGlobal`로 최소 구성한다.

인수 조건:

- `npm.cmd run lint`, `npm.cmd run build`, `npm.cmd test -- --run`이 통과한다.
- lint 규칙 때문에 기존 코드를 대규모 포맷 변경하지 않는다.

스프린트 데모:

- 잘못된 환경 응답을 거부하는 테스트.
- Kubernetes 기존 화면과 빌드가 그대로 유지됨.

---

## Sprint 1 - 3~4주차: 실제 환경 탭과 세션 생명주기

### FE-03 환경 가용성 기반 탭

수정 파일:

- `src/services/api.ts`
- `src/config/environments.ts`
- `src/App.tsx`
- `src/App.css`

구현 지시:

- `getEnvironments(token)`을 추가한다.
- 로그인 복원 후 환경 목록을 조회한다.
- `available`만 선택 가능하게 하고 `preparing`, `disabled`는 `aria-disabled`, 상태 설명, tooltip 없이도 읽히는 보조 문구를 제공한다.
- `degraded`는 진입 가능하되 상단에 경고를 표시한다.
- Application 탭은 범위 결정에 따라 제거하거나 "후속 연구" 섹션으로 이동한다.
- 사용자별 마지막 환경을 `afterfail:environment:v1:{userId}`에 저장한다.
- 저장된 환경이 available이 아니면 Kubernetes, 그것도 불가능하면 첫 available 환경을 선택한다.

인수 조건:

- 가용성 API 로딩, 성공, 일부 degraded, 전체 실패 화면이 각각 존재한다.
- 준비 중 탭 클릭으로 API 요청이나 세션 생성이 발생하지 않는다.
- 키보드 화살표 또는 Tab/Enter로 환경을 선택할 수 있다.

### FE-04 환경별 터미널 세션 지연 생성

수정 파일:

- 신규 `src/hooks/useEnvironmentSessions.ts`
- `src/services/api.ts`
- `src/App.tsx`
- `src/components/Terminal/Terminal.tsx`

구현 지시:

- 로그인 즉시 무조건 세션을 만드는 기존 흐름을 제거한다.
- available 환경을 선택하고 workspace가 필요해질 때 `createTerminalSession(token, environment)`을 호출한다.
- `Record<EnvironmentId, SessionResponse | undefined>`로 세션을 메모리 캐시한다.
- 동시에 같은 환경 세션을 두 번 생성하지 않도록 in-flight Promise 또는 loading state를 환경별로 관리한다.
- token 변경·로그아웃·AUTH_EXPIRED_EVENT에서 모든 로컬 세션 상태를 비운다.
- 서버가 세션 종료 API를 제공하면 로그아웃 시 best-effort로 호출하되 로그아웃 화면 전환을 막지 않는다.
- 요청 environment와 응답 environment가 다르면 Terminal을 mount하지 않는다.

인수 조건:

- Kubernetes -> Docker -> Kubernetes 전환 시 각 환경 세션은 한 번만 생성된다.
- 세션 생성 중 로딩 상태와 실패 후 재시도 버튼이 보인다.
- 이전 환경 WebSocket output이 현재 환경 Terminal에 출력되지 않는다.

### FE-05 활성 attempt 환경 잠금과 복원

수정 파일:

- `src/App.tsx`
- `src/components/Mission/MissionList.tsx`
- `src/components/Mission/MissionStatus.tsx`

구현 지시:

- `onActiveMissionChange(boolean)`을 `onActiveAttemptChange(summary | null)`로 교체한다.
- summary에는 attemptId, attemptType, environment, status가 들어간다.
- 활성 attempt 중 다른 환경 탭을 disabled 처리하고 이유를 보여준다.
- 새로고침 시 서버 status의 environment로 activeEnvironment를 복원한다.
- localStorage attempt type은 서버 status 조회 순서를 정하는 용도로만 사용한다.
- 서버에 활성 attempt가 없으면 stale localStorage 값을 제거한다.

인수 조건:

- 활성 미션 중 탭을 바꿔 잘못된 환경 명령을 실행할 수 없다.
- 새로고침 후 활성 미션·환경·터미널이 동일 환경으로 복원된다.
- 완료/실패/포기 시 탭 잠금이 즉시 해제된다.

스프린트 데모:

- 서버가 Docker를 preparing으로 응답하는 화면.
- Kubernetes 활성 미션 중 Docker 탭이 잠기는 흐름.
- 새로고침 후 활성 미션 복원.

---

## Sprint 2 - 5~6주차: Docker 훈련 UI 연결

선행 조건: backend `feature/env-sandbox`, `feature/docker-env`, API-02~05.

### FE-06 환경별 미션과 AI 시나리오

수정 파일:

- `src/services/api.ts`
- `src/components/Mission/MissionList.tsx`
- `src/components/Mission/MissionCard.tsx`
- `src/components/Mission/MissionStatus.tsx`
- `src/components/Mission/Mission.css`

구현 지시:

- `listMissions(token, environment)`로 query를 보낸다.
- environment 변경 시 이전 요청을 AbortController로 취소하고 미션 목록·오류·선택 상태를 초기화한다.
- 응답 항목의 environment가 선택 환경과 다른 경우 해당 항목을 조용히 숨기지 말고 계약 오류를 표시한다.
- 카드에 환경 배지를 추가하되 색만으로 구분하지 않는다.
- AI 시나리오 시작 시 현재 environment를 보낸다.
- AI unlock 상태가 환경별인지 전체인지 API 계약에 따라 문구를 정확히 표시한다.
- 환경별 미션이 0개인 경우 "준비 중"과 "조회 실패"를 구분한다.

인수 조건:

- Docker 탭에는 Docker 미션만 보인다.
- 빠르게 환경을 전환해도 늦게 도착한 Kubernetes 응답이 Docker 화면을 덮지 않는다.
- Docker AI 시나리오 요청 body와 응답 environment가 docker다.

### FE-07 환경별 xterm 설정

수정 파일:

- `src/config/environments.ts`
- `src/utils/terminal.ts`
- `src/components/Terminal/Terminal.tsx`
- `src/hooks/useTerminalWebSocket.ts`
- `src/components/Terminal/Terminal.css`

구현 지시:

- `getTerminalPrompt(environment, namespace)`로 변경한다.
- 자동완성 배열을 Terminal 내부 하드코딩에서 config로 이동한다.
- Kubernetes만 허용하는 프론트 오류 문구를 환경 중립적으로 바꾼다.
- Docker 터미널 header는 `SHELL / DOCKER`, prompt는 sandbox임을 식별할 수 있게 표시한다.
- environment 또는 sessionId가 바뀌면 기존 WebSocket을 의도적으로 닫고 입력 queue와 현재 줄을 비운다.
- 연결 전 입력은 전송하지 않고 사용자에게 연결 상태를 알려준다.
- 서버 confirm 메시지는 기존 ConfirmModal을 그대로 재사용한다.

Docker 자동완성 최소 목록:

```text
docker ps -a
docker inspect
docker logs
docker stats --no-stream
docker network ls
docker network inspect
docker volume ls
docker volume inspect
```

인수 조건:

- Docker 탭에서 kubectl 전용 안내가 보이지 않는다.
- 명령 queue가 환경 전환을 넘어 전달되지 않는다.
- 연결 끊김 3회 재시도와 인증 만료 동작이 기존처럼 유지된다.

### FE-08 Docker 관측 패널

수정 파일:

- `src/config/environments.ts`
- `src/App.tsx`
- `src/App.css`

구현 지시:

- `getGrafanaUrl(environment, scope)`와 `getGrafanaDataProbeUrl(environment, scope)`로 일반화한다.
- Docker dashboard UID와 readiness query를 config에서 읽는다.
- iframe title에 환경을 포함한다.
- Prometheus 실패 3회 후 iframe load만으로 ready 처리하는 기존 fallback은 유지하되 degraded 경고를 표시한다.
- 미션이 없을 때는 학습 대시보드를 표시하고 불필요한 readiness polling을 하지 않는다.

인수 조건:

- Docker 미션 중 Docker dashboard만 열린다.
- 환경 전환/미션 종료 시 polling interval이 남지 않는다.
- Grafana가 차단돼도 터미널과 미션 액션은 계속 사용할 수 있다.

스프린트 데모:

- Docker 네트워크 단절 미션 선택 -> docker CLI 조사 -> AI 힌트 -> 복구 -> 검증 -> 점수 반영.

---

## Sprint 3 - 7~8주차: Linux 훈련 UI 연결과 중간 점검

선행 조건: backend `feature/linux-env`, API-02~05.

### FE-09 Linux 환경 연결

수정 파일: FE-06~08과 동일. 새 환경 전용 컴포넌트는 만들지 않는다.

구현 지시:

- config에 Linux label, prompt, command suggestions, Grafana UID, readiness query를 채운다.
- 기존 공용 MissionList, Terminal, TutorChat, MissionStatus를 그대로 사용한다.
- Linux 명령 출력은 ANSI escape와 긴 로그가 올 수 있으므로 xterm 렌더링을 유지한다.
- `journalctl`, `dmesg`처럼 출력이 긴 명령은 서버가 잘라서 보내거나 streaming하는 계약을 확인한다. 프론트가 전체 로그를 별도 state에 복제하지 않는다.
- 위험 명령 차단 메시지는 서버의 detail/code를 그대로 사용자 친화적으로 표시한다.

Linux 자동완성 최소 목록:

```text
ps aux
top
free -m
df -h
du -sh
systemctl status
journalctl -u
dmesg
ss -lntp
```

인수 조건:

- Linux 미션에서 Docker/kubectl 명령 가이드가 섞이지 않는다.
- OOM, disk I/O, zombie 시나리오의 상태·점수·힌트가 공용 UI에 정상 반영된다.
- 환경별 코드 분기가 config 조회 외에 MissionList/Terminal에 반복되지 않는다.

### FE-10 8주차 범위 게이트

검토 항목:

- Kubernetes 회귀 없음.
- Docker end-to-end 2개 이상 완료.
- Linux end-to-end 2개 이상 완료.
- 자동 채점과 UI 반영 지연 측정.
- 환경 탭·세션·attempt 불일치 0건.
- Application/DB 조건부 범위 착수 여부 결정.

Application/DB 착수 조건:

- Docker와 Linux 필수 데모가 모두 통과한다.
- 백엔드가 `application` environment, sandbox, 명령 정책, injector, validation, dashboard를 제공한다.
- 남은 핵심 버그가 P1 0개다.

조건을 충족하지 못하면 Application 탭을 추가하지 않고 안정화에 집중한다.

스프린트 데모:

- Linux OOM 또는 disk I/O 미션 전체 흐름.
- 3개 환경을 오가며 미션 목록과 대시보드가 올바르게 바뀌는 화면.

---

## Sprint 4 - 9~10주차: 크로스 레이어 AI 튜터 UX

### FE-11 환경 인지형 튜터 표시

수정 파일:

- `src/services/api.ts`
- `src/components/Mission/TutorChat.tsx`
- `src/components/Mission/Mission.css`

구현 지시:

- TutorChat에 environment prop을 추가하고 제목 옆에 환경 배지를 표시한다.
- ChatResponse에 `sources`, `observations_used` 타입을 추가한다.
- 답변 본문 아래에 "사용한 관측 정보"와 "참고 자료" 접기 영역을 표시한다.
- source path를 임의의 외부 링크로 만들지 않는다. 백엔드가 안전한 URL을 줄 때만 anchor로 렌더링한다.
- attempt/environment 변경 시 대화 state를 초기화한다.
- 질문 전송 중 AbortController를 보관하고 unmount·attempt 종료·환경 변경에서 취소한다.
- 오류 시 사용자의 마지막 질문은 유지하고 재전송 버튼을 제공한다.
- 힌트 단계 상승은 기존처럼 서버 hint API 성공 뒤에만 반영한다.

인수 조건:

- Docker 질문에 Kubernetes 배지가 표시되거나 반대 상황이 발생하지 않는다.
- sources가 없어도 레이아웃이 깨지지 않는다.
- 환경 전환 후 이전 AI 응답이 새 채팅에 추가되지 않는다.
- 채팅 입력은 label이 있고 Enter 제출, Shift+Enter 정책이 명확하다. 현재 input을 유지하면 Enter 제출만 지원한다.

### FE-12 AI 응답 시간과 사용자 피드백

수정 파일:

- `src/components/Mission/TutorChat.tsx`
- `src/components/Mission/Mission.css`

구현 지시:

- 질문 전송 시 즉시 사용자 메시지와 typing indicator를 표시한다.
- `performance.now()`로 응답 소요 시간을 측정해 개발 모드에서만 기록한다.
- 1.5초가 지나도 응답이 없으면 "환경 상태와 관련 문서를 분석 중" 보조 문구를 표시한다.
- 15초 이후에는 취소 버튼을 제공하되 자동 실패 처리하지 않는다.
- 중복 제출과 힌트 중복 감점을 막는다.

인수 조건:

- 느린 응답에도 화면이 멈춘 것처럼 보이지 않는다.
- 취소한 응답이 뒤늦게 메시지 목록에 추가되지 않는다.
- 1회 질문에 chat API가 정확히 1회 호출된다.

스프린트 데모:

- Kubernetes/Docker/Linux 동일 질문에 환경별 근거와 관측 정보가 다르게 표시됨.
- 느린 AI 응답, 취소, 재전송 흐름.

---

## Sprint 5 - 11~12주차: 환경별 통합 대시보드

### FE-13 환경 필터와 핵심 지표

수정 파일:

- `src/services/api.ts`
- `src/components/Profile/DashboardOverview.tsx`
- `src/components/Profile/ProfileDetails.tsx`
- `src/components/Profile/Profile.css`

구현 지시:

- DashboardOverview에 `environment: EnvironmentId | 'all'` prop을 추가한다.
- 전체, Kubernetes, Docker, Linux 필터를 제공한다.
- 선택 환경에 따라 stats와 learning curve를 다시 조회한다.
- 환경 전환 시 이전 요청을 취소한다.
- 표시 지표: 완료 미션, 평균 점수, 평균 MTTR, 총 힌트, 누적 학습 시간.
- 서버 응답이 없는 지표를 0으로 위조하지 않고 "데이터 없음"으로 표시한다.

인수 조건:

- 필터 변경 시 숫자·곡선·목록이 같은 환경 데이터로 함께 바뀐다.
- 0회 완료와 API 실패가 시각적으로 구분된다.
- MTTR은 초를 받아 사람이 읽을 수 있는 분/초로 표시한다.

### FE-14 환경 역량 레이더와 성장 곡선

수정 파일:

- `src/components/Profile/DashboardOverview.tsx`
- `src/components/Profile/Profile.css`

구현 지시:

- 기존 직접 작성 SVG 방식을 재사용한다.
- 전체 보기에서는 Kubernetes/Docker/Linux 3축 환경 역량 레이더를 표시한다.
- 단일 환경 보기에서는 기존 Troubleshooting/Resource/Network/Ops 4축 레이더를 유지한다.
- 축 개수에 따라 좌표를 계산하는 일반 함수로 바꾸고 3축/4축을 모두 테스트한다.
- 학습 곡선은 완료 시간뿐 아니라 score 토글을 제공하거나, 복잡도를 줄이려면 score를 점 label로 함께 표시한다.
- SVG에 `role="img"`, 동적 aria-label, 텍스트 대체 요약을 제공한다.

인수 조건:

- 0, 1, 3개 데이터에서도 NaN 좌표가 생성되지 않는다.
- 모바일에서 SVG가 잘리지 않고 텍스트 대체 정보로 수치를 읽을 수 있다.
- 새 차트 라이브러리가 package.json에 추가되지 않는다.

### FE-15 미션 종료 후 통계 동기화

수정 파일:

- `src/App.tsx`
- `src/components/Mission/MissionList.tsx`
- `src/components/Profile/DashboardOverview.tsx`

구현 지시:

- 미션 완료 이벤트에 단조 증가하는 `dashboardRefreshKey`를 사용한다.
- 완료 직후 profile과 dashboard를 한 번 갱신한다.
- 기존 15초 profile polling은 유지하되 같은 시점 중복 요청을 막는다.
- 프론트에서 점수/MTTR을 계산해 미리 더하지 않는다.

인수 조건:

- 완료 모달/Toast 이후 1회 서버 갱신으로 점수와 환경 통계가 바뀐다.
- 동일 attempt 완료 이벤트가 중복 반영되지 않는다.

스프린트 데모:

- 환경 필터별 MTTR/점수/힌트 비교.
- 3축 환경 레이더와 환경별 성장 곡선.

---

## Sprint 6 - 13~14주차: 안정성, 접근성, 반응형, 성능

### FE-16 폴링과 네트워크 안정화

수정 파일:

- `src/components/Mission/MissionStatus.tsx`
- `src/components/Mission/MissionList.tsx`
- `src/hooks/useTerminalWebSocket.ts`
- `src/App.tsx`

구현 지시:

- status polling은 기본 5초, 브라우저 tab hidden일 때 15초로 완화한다.
- 완료·실패·포기·404에서 즉시 중단한다.
- 연속 네트워크 실패는 지수 backoff를 적용하되 최대 30초로 제한한다.
- check/hint/abandon 버튼은 요청 중 중복 클릭을 막고 액션별 loading 문구를 표시한다.
- 인증 만료는 기존 AUTH_EXPIRED_EVENT 한 경로로 통합한다.
- 환경 또는 attempt가 바뀌면 이전 timer, fetch, websocket을 모두 정리한다.

인수 조건:

- React StrictMode에서도 중복 interval과 중복 WebSocket이 남지 않는다.
- 10분 사용 후 DevTools에서 계속 증가하는 요청·listener가 없다.
- 네트워크가 복구되면 새로고침 없이 상태 조회가 재개된다.

### FE-17 접근성과 반응형 완성

수정 파일: 기존 TSX와 CSS. 새 UI 라이브러리는 추가하지 않는다.

검수 목록:

- 환경 탭에 `role="tablist"`, 각 탭에 `role="tab"`, `aria-selected`, 연결된 `aria-controls`.
- disabled 이유는 색과 tooltip에만 의존하지 않는다.
- Toast는 성공 `status`, 오류 `alert` live region을 사용한다.
- ConfirmModal은 focus trap, Escape 닫기, 닫힌 뒤 원래 버튼 focus 복귀.
- xterm 바깥에 연결 상태 텍스트가 존재한다.
- 차트는 텍스트 요약을 제공한다.
- 390px 화면에서 미션 액션 3개가 잘리지 않는다.
- 768px 이하에서 미션/터미널 전환 시 Terminal을 unmount하지 않아 연결을 유지한다.
- 1366x768에서 Terminal과 Tutor가 동시에 사용 가능하다.

### FE-18 자동화 테스트 확대

필수 테스트:

1. 환경 config에 3개 환경 값이 모두 존재한다.
2. 준비 중 환경은 세션을 만들지 않는다.
3. 활성 attempt 중 환경 전환이 차단된다.
4. 환경 변경 시 이전 mission fetch가 취소된다.
5. startRandomScenario body에 선택 environment가 들어간다.
6. 터미널 prompt와 suggestions가 환경에 맞게 바뀐다.
7. environment/session mismatch면 WebSocket을 열지 않는다.
8. TutorChat이 stale 응답을 무시한다.
9. 3축/4축 레이더 좌표가 유효하다.
10. 미션 완료 후 dashboard refresh가 한 번 발생한다.

인수 조건:

- build/lint/test 전부 통과.
- 테스트가 실제 네트워크나 Docker/Kubernetes 설치를 요구하지 않는다.
- E2E 통합은 mock backend와 실제 backend를 구분해 기록한다.

스프린트 데모:

- 모바일·태블릿·데스크톱 동일 미션 흐름.
- WebSocket 단절과 API 일시 장애 복구.
- 자동화 테스트 결과.

---

## Sprint 7 - 15~16주차: 통합 검증, 시연, 제출

### FE-19 실제 환경 통합 테스트

환경별로 아래 시나리오를 최소 2회 수행한다.

| 환경 | 필수 시나리오 | 확인 사항 |
|---|---|---|
| Kubernetes | ImagePullBackOff, OOM/Probe | 기존 기능 회귀, Grafana, kubectl |
| Docker | 네트워크 단절, 볼륨/리소스 오류 | docker CLI, 환경 격리, 검증 |
| Linux | OOM, disk I/O 또는 zombie | shell CLI, 긴 로그, 검증 |

각 실행에서 기록할 값:

- 로그인부터 미션 시작까지 시간.
- AI 튜터 첫 응답 시간과 95 percentile.
- 검증 클릭부터 점수 화면 반영까지 시간.
- WebSocket 재연결 성공 여부.
- 환경/세션/attempt ID 불일치 여부.
- 1366x768과 390x844의 화면 결함.

### FE-20 성능 목표 검증

- AI 1.5초 목표는 네트워크·LLM을 포함한 백엔드 목표이므로 프론트는 측정값을 숨기지 않는다.
- 자동 채점 300ms 목표는 check API response time과 UI commit까지 구분해 측정한다.
- 프론트 자체 목표:
  - 탭 클릭 후 로딩 상태 표시 100ms 이내.
  - status 응답 수신 후 수치 반영 다음 frame 이내.
  - 중복 API 호출 0건.
  - production JS gzip 크기가 기준선 133.75kB에서 20% 이상 증가하면 원인을 검토한다.

### FE-21 시연 모드와 문서화

수정 파일:

- `frontend/README.md`
- `frontend/ENV_SETUP.md`
- 필요 시 `docs/terminal-test-guide.md`

문서 내용:

- 3개 환경 실행 전제와 필요한 backend branch/config.
- 환경별 Grafana/Prometheus URL 설정.
- 환경별 미션 데모 순서.
- mock validation과 실제 validation 구분.
- 알려진 제한: privileged sandbox, Application/DB 제외 여부, 브라우저 지원 범위.
- 장애 발생 시 복구 절차와 로그 위치.

시연 체크리스트:

1. 새 계정 로그인.
2. Kubernetes 미션 완료.
3. Docker 탭으로 전환해 Docker 명령과 관측 화면 확인.
4. Docker 장애 복구와 AI 튜터 근거 확인.
5. Linux 미션 완료.
6. 프로필에서 환경별 MTTR·점수·레이더·성장 곡선 확인.
7. 네트워크 단절 또는 터미널 재연결 한 번 시연.

최종 완료 조건:

- P0/P1 버그 0개.
- 세 환경 end-to-end 성공.
- build/lint/test 성공 로그 확보.
- README와 시연 대본이 현재 구현과 일치.
- Application/DB 제외 시 그 이유와 후속 계획이 최종 발표 자료에 명시됨.

---

## 7. 작업 의존성 및 우선순위

```text
FE-00 API 계약
  -> FE-01 타입
  -> FE-03 환경 탭
  -> FE-04 세션
  -> FE-05 활성 attempt 잠금
       -> backend env-sandbox
          -> FE-06/07/08 Docker
          -> FE-09 Linux
              -> FE-11/12 튜터
              -> FE-13/14/15 대시보드
                  -> FE-16/17/18 품질
                      -> FE-19/20/21 제출
```

우선순위:

- P0: 환경/세션/attempt 불일치, 다른 사용자 세션 연결, 명령이 잘못된 sandbox로 전송됨.
- P1: 미션 시작·검증·포기 불가, 새로고침 복원 실패, 점수 중복 반영, 환경 탭 오표시.
- P2: Grafana 로딩 실패, AI 근거 표시 오류, 모바일 레이아웃 결함.
- P3: 문구·애니메이션·세부 시각 개선.

P0/P1이 남아 있으면 Application/DB, 추가 애니메이션, 신규 차트 작업을 중단한다.

---

## 8. PR 단위와 브랜치 권장안

| PR | 브랜치 예시 | 포함 작업 |
|---|---|---|
| 1 | `feature/frontend-env-types` | FE-01, FE-02 |
| 2 | `feature/frontend-env-tabs` | FE-03, FE-05 |
| 3 | `feature/frontend-env-sessions` | FE-04, FE-07 공통 기반 |
| 4 | `feature/frontend-docker` | FE-06~08 Docker 부분 |
| 5 | `feature/frontend-linux` | FE-09 |
| 6 | `feature/frontend-cross-layer-tutor` | FE-11, FE-12 |
| 7 | `feature/frontend-env-dashboard` | FE-13~15 |
| 8 | `feature/frontend-hardening` | FE-16~18 |
| 9 | `feature/frontend-release` | FE-19~21 문서·최종 수정 |

PR 하나에서 백엔드 계약 변경과 대규모 UI 변경을 섞지 않는다. 단, 동일 계약을 맞추는 작은 타입 변경은 통합 PR에 포함할 수 있다.

---

## 9. Definition of Done 체크리스트

각 작업 공통:

- [ ] 작업 ID의 선행 조건을 확인했다.
- [ ] 현재 환경과 API 응답 environment 일치를 검사한다.
- [ ] 로딩, 빈 데이터, API 오류, 인증 만료 상태가 있다.
- [ ] unmount·환경 전환에서 fetch/timer/WebSocket을 정리한다.
- [ ] 모바일과 키보드 사용을 확인했다.
- [ ] 서버 점수를 프론트에서 재계산하지 않았다.
- [ ] 새 runtime dependency를 추가하지 않았다.
- [ ] `npm.cmd run build` 통과.
- [ ] `npm.cmd run lint` 통과.
- [ ] `npm.cmd test -- --run` 통과.
- [ ] 변경한 사용자 흐름을 README 또는 이 문서에 반영했다.

환경 기능 완료:

- [ ] 해당 환경의 availability가 available이다.
- [ ] 해당 환경 session 생성/응답 environment가 일치한다.
- [ ] 해당 환경 미션만 조회된다.
- [ ] 정적 미션과 AI 시나리오 모두 environment가 일치한다.
- [ ] 터미널 prompt, label, suggestions가 환경에 맞다.
- [ ] 관측 dashboard와 readiness query가 환경에 맞다.
- [ ] 튜터 environment, sources, observations가 환경에 맞다.
- [ ] 완료 후 해당 환경 통계가 갱신된다.
- [ ] 다른 환경과 사용자에게 장애·명령·통계가 섞이지 않는다.

---

## 10. 예상 위험과 대응

| 위험 | 조기 신호 | 프론트 대응 |
|---|---|---|
| 백엔드 sandbox 지연 | 4주차에도 Docker session 생성 불가 | 탭 가용성·공통 타입·테스트·대시보드 기반을 먼저 완료하고 가짜 실행 UI는 만들지 않음 |
| 환경 응답 불일치 | mission은 docker인데 session은 kubernetes | P0로 차단하고 Terminal을 mount하지 않음 |
| 폴링 증가 | 환경/화면 전환 뒤 request 수 증가 | AbortController, interval cleanup, visibility 기반 완화 |
| xterm 재생성 | 탭 전환마다 연결·기록 소실 | 모바일 CSS로 숨기되 mount 유지, 환경 변경 때만 의도적 재연결 |
| AI 지연 | 1.5초 초과 빈번 | 단계별 로딩 문구, 취소, 재전송, 측정값 기록 |
| Grafana 미가용 | iframe load 또는 Prometheus CORS 실패 | 훈련 액션과 분리하고 degraded 경고·새 창 링크 제공 |
| 대시보드 0 왜곡 | API 오류가 0점처럼 표시 | `null/loading/error/empty` 상태 분리 |
| 범위 과다 | Application 요구가 중간에 재등장 | 8주차 gate 조건을 충족할 때만 추가 |
| 접근성 후순위 | 모달 focus·탭 label 누락 | 공용 컴포넌트 단위로 Sprint 6 이전부터 인수 조건에 포함 |

---

## 11. 최종 산출물

프론트엔드 담당자가 2학기 말까지 제출해야 할 결과물:

- Kubernetes/Docker/Linux 환경 탭 기반 훈련 UI.
- 환경별 xterm.js 터미널과 안전한 세션 전환 UX.
- 공용 정적 미션·AI 시나리오·채점·힌트 흐름.
- 환경 인지형 AI 튜터와 근거/관측 정보 UI.
- 환경별 Grafana 관측 화면.
- 환경별 MTTR·점수·힌트·역량 레이더·성장 곡선 대시보드.
- 인증 만료, 재연결, 새로고침 복원, 네트워크 실패 대응.
- build/lint/test 자동 검증 기반.
- 환경 설정, 실행법, 시연 대본, 알려진 제한 문서.

이 계획의 핵심은 환경마다 새 화면을 복제하는 것이 아니라, 현재 Kubernetes 흐름에 이미 존재하는 MissionList, Terminal, TutorChat, DashboardOverview에 environment를 끝까지 관통시키는 것이다. 백엔드가 실제 환경을 제공할 때 탭만 활성화하면 동일한 사용자 흐름으로 동작하도록 만드는 것이 가장 작은 구현으로 가장 큰 확장성을 얻는 경로다.
