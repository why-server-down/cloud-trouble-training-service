# Frontend — AfterFail

React 18 + TypeScript + Vite. 3개 훈련 환경(Kubernetes / Docker / Linux)의 장애 대응 훈련 콘솔.

```bash
cd frontend
npm install
npm run dev     # http://localhost:3000
npm run build   # tsc && vite build
npm run lint
npx vitest run  # 236 tests
```

---

## 1. 실행 전제

프론트만 띄워서는 아무것도 할 수 없다. 백엔드·DB·Qdrant 가 함께 떠 있어야 한다.

```bash
# 저장소 루트에서
docker compose up -d postgres qdrant
docker compose build backend
```

### 로컬 검증용 백엔드 기동

저장소 `.env` 는 `AI_BACKEND=gemini`, `CHAOS_BACKEND=chaos_mesh` 로 되어 있다.
클러스터에 Chaos Mesh CRD 가 없고 Gemini 는 실제 과금이므로, 프론트 확인에는
`.env` 를 고치지 말고 `-e` 로만 덮어쓴다.

```bash
docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE k8s_survival_local;"

docker compose run -d --service-ports --name afterfail-backend-local \
  -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/k8s_survival_local \
  -e CHAOS_BACKEND=mock \
  -e VALIDATION_BACKEND=mock \
  -e AI_BACKEND=mock \
  -e DEMO_UNLOCK_AI_SCENARIOS=true \
  -e MOCK_VALIDATION_AUTO_PASS=true \
  backend
```

> **DB 를 새로 만드는 이유:** 기존 `k8s_survival` 볼륨은 BE-02(Alembic 도입) 이전
> 스키마로 만들어져 `mission_attempts.environment` 컬럼과 `alembic_version` 테이블이
> 없다. 현재 코드로 붙으면 attempt 조회가 깨진다. 기존 DB 를 살릴지(stamp + upgrade)
> 볼륨을 지울지는 백엔드 담당이 결정한다.

기동 확인: `curl http://localhost:8000/health` → `{"status":"ok"}`

정리: `docker rm -f afterfail-backend-local`

### mock 과 실제 검증의 차이

| 설정 | mock | 실제 |
|---|---|---|
| `CHAOS_BACKEND` | 장애를 주입하지 않고 주입한 것으로 기록 | `chaos_mesh` — 실클러스터에 주입 |
| `VALIDATION_BACKEND` | `MOCK_VALIDATION_AUTO_PASS=true` 면 완료 확인이 항상 통과 | `k8s` / `prometheus` — 실제 리소스 상태로 판정 |
| `AI_BACKEND` | 고정 문구 응답. `fallback_used: true` 로 내려오고 화면에도 그렇게 표시된다 | `openai` / `gemini` — 실제 LLM |

**mock 으로 확인한 것은 "화면이 계약대로 동작한다"까지다.** 채점 정확도·AI 응답 품질은
실환경(FE-19)에서만 확인된다.

---

## 2. 환경변수

`frontend/.env.development`:

```env
VITE_API_BASE_URL=
VITE_WS_BASE_URL=
```

**비워 두는 것이 기본이다.** 비우면 요청이 상대 경로로 나가 Vite dev proxy
(`vite.config.ts` 의 `/api`, `/ws`)를 타므로 same-origin 이 되고 CORS 가 관여하지 않는다.

값을 채울 때는 CORS 를 함께 확인해야 한다 — 자세한 판정 표는
[ENV_SETUP.md](ENV_SETUP.md) 를 본다. 요약하면 `api.ts` 의 `normalizeApiBaseUrl` 이
**hostname 이 브라우저 주소와 같을 때만** 상대 경로로 접으므로,
`127.0.0.1:3000` 이나 LAN IP 로 열면 cross-origin 이 되어 백엔드 `CORS_ORIGINS` 에
그 origin 을 넣어야 한다 (`localhost` 와 `127.0.0.1` 은 다른 origin 이다).

### 환경별 Grafana / Prometheus

```env
VITE_GRAFANA_BASE_URL=http://localhost:3001
VITE_PROMETHEUS_BASE_URL=http://localhost:9090
```

대시보드 UID·slug·readiness PromQL 은 `src/config/environments.ts` 의
`ENVIRONMENT_OBSERVABILITY` 에 있다.

| 환경 | 대시보드 | 비고 |
|---|---|---|
| Kubernetes | `k8s-survival-overview` | `infra/monitoring/grafana/dashboards/` |
| Docker | **없음** | 관측 패널에 "대시보드가 아직 없습니다" 안내 |
| Linux | **없음** | 같음 |

대시보드가 추가되면 `ENVIRONMENT_OBSERVABILITY` 표에 UID·slug·scopeVar·PromQL 만
채우면 화면이 열린다. **없는 환경에서 K8s 대시보드로 대체하지 않는다** — 남의 환경
지표를 자기 것으로 읽게 되기 때문이다.

---

## 3. 구조

```
frontend/src/
├── components/
│   ├── Login/Login.tsx                 로그인 / 회원가입
│   ├── Environment/
│   │   ├── EnvironmentTabs.tsx          환경 탭 (가용성·활성 attempt 잠금)
│   │   └── EnvironmentRoadmap.tsx       준비 중 환경 안내
│   ├── Mission/
│   │   ├── MissionList.tsx              미션 목록 + AI 시나리오 + 액션
│   │   ├── MissionCard.tsx              개별 카드
│   │   ├── MissionStatus.tsx            진행 상태 폴링 + 액션 버튼
│   │   └── TutorChat.tsx                AI 튜터 (근거·응답시간·호출제한)
│   ├── Terminal/Terminal.tsx            xterm.js + WebSocket
│   ├── Profile/
│   │   ├── DashboardOverview.tsx        환경별 대시보드 (필터·레이더·곡선)
│   │   └── ProfileDetails.tsx           프로필 상세
│   ├── Feedback/
│   │   ├── ConfirmModal.tsx             focus trap + Escape
│   │   └── Toast.tsx                    오류는 alert, 나머지는 status
│   └── Onboarding/OnboardingTour.tsx    최초 진입 투어
├── config/
│   ├── environments.ts                  환경별 표시·터미널·관측 설정
│   └── polling.ts                       폴링 간격
├── hooks/
│   ├── useEnvironmentSessions.ts        환경별 세션 지연 생성·캐시
│   ├── useTerminalWebSocket.ts          WebSocket 생명주기·재연결
│   └── usePolling.ts                    가시성·backoff 폴링
├── services/api.ts                      API 클라이언트 + 계약 타입
└── utils/
    ├── terminal.ts                      프롬프트·오프라인 안내
    ├── dashboard.ts                     레이더·곡선 좌표, MTTR 표기
    ├── tutorSources.ts                  근거 링크 안전성
    └── perf.ts                          성능 측정 (User Timing)
```

### 환경을 추가할 때

`src/types/training.ts` 의 `ENVIRONMENT_IDS` 에 넣으면 `config/environments.ts` 의
`Record<EnvironmentId, ...>` 들이 **컴파일 단계에서 누락을 드러낸다.**
전용 컴포넌트를 만들지 않는다 — 공용 MissionList / Terminal / TutorChat 이
config 조회로 환경을 처리한다.

### 자동완성·명령 정책의 원본

`ENVIRONMENT_TERMINAL` 의 `binary` / `allowedCommands` / `completions` 는
**계획서가 아니라 `backend/app/services/command_validator.py` 를 원본으로 삼는다.**
프론트가 더 넓게 제안하면 사용자는 서버가 거절할 명령을 Tab 으로 완성하게 된다.

- Kubernetes / Docker: argv[0] 이 고정 실행 파일 → `binary`
- Linux: 명령 자체가 argv[0] → `allowedCommands`
  (`systemctl` / `journalctl` / `dmesg` 는 **제외** — 샌드박스에 systemd 가 없고
  커널 링 버퍼도 막혀 있다, BE-16 실측)

---

## 4. 환경별 데모 순서

전제: 위 mock 백엔드 기동 + `npm run dev`.

### 공통

1. 회원가입 → 온보딩 투어 SKIP
2. 환경 탭 3개가 열려 있는지 확인 (`GET /api/environments` 의 status)

### Kubernetes

1. Kubernetes 탭 → 미션 선택 → 확인 모달에서 시작
2. 터미널 헤더 `SHELL / KUBECTL`, 프롬프트 `[kubernetes:...]$`
3. `kubectl get pods` 로 상태 조사 (Tab 자동완성 확인)
4. 관측 패널에 `OBSERVABILITY / KUBERNETES` + Grafana iframe
5. AI 튜터 질문 → 답변 아래 "사용한 관측 정보 / 참고 자료 / 응답 N초"
6. 완료 확인 → 점수 반영

### Docker

1. Docker 탭 → 미션 시작
2. 터미널 헤더 `SHELL / DOCKER`, field guide 에 `docker ps -a` 등 (kubectl 없음)
3. **관측 패널에 "Docker 환경은 관측 대시보드가 아직 없습니다"** — iframe 없음
4. 나머지는 Kubernetes 와 동일 경로

### Linux

1. Linux 탭 → 미션 시작 (`늘어나는 그림자` / `가득 찬 창고` / `보이지 않는 과부하`)
2. field guide 에 `ps aux`, `df -h`, `top -b -n 1`, `cat /proc/loadavg`
3. 장애 유형은 **disk pressure / CPU saturation / process flood** 이다
   (계획서의 OOM·zombie 는 백엔드가 실측 후 제외했다)
4. 복구 명령은 `pkill -f afterfail-`, `rm /tmp/afterfail/...` — 확인 모달을 거친다

### 환경별 대시보드

1. 미션을 포기·완료해 활성 attempt 를 비운다 (탭 잠금이 풀린다)
2. 학습 대시보드에서 전체 / Kubernetes / Docker / Linux 필터 전환
3. 전체 = 3축 환경 역량 레이더, 단일 환경 = 4축 스킬 레이더
4. 완료가 0건이면 레이더 대신 안내가 뜬다 (0 으로 위조하지 않는다)

### AI 시나리오

`DEMO_UNLOCK_AI_SCENARIOS=true` 또는 화면의 "시연용 잠금 해제" 버튼.
해금 조건은 **전 환경 기본 미션 10개 완료**다(`unlock-status` 는 environment 로
필터되지 않는다).

---

## 5. 시연 체크리스트

- [ ] 새 계정 로그인
- [ ] Kubernetes 미션 완료
- [ ] Docker 탭 전환 → docker 명령 안내와 관측 패널 확인
- [ ] Docker 장애 복구 + AI 튜터 근거 확인
- [ ] Linux 미션 완료
- [ ] 프로필에서 환경별 MTTR·점수·레이더·성장 곡선 확인
- [ ] 네트워크 단절 또는 터미널 재연결 1회 시연

---

## 6. 성능 목표와 실측값

측정은 User Timing API 로 남긴다 (`src/utils/perf.ts`). DevTools Performance 패널과
`performance.getEntriesByType('measure')` 양쪽에서 읽힌다 — **프론트가 측정값을
숨기지 않는다**는 원칙을 코드로 지킨 것이다.

| measure 이름 | 뜻 |
|---|---|
| `afterfail:tutor-response` | 질문 전송 → 답변 도착 |
| `afterfail:mission-check-api` | 완료 확인 클릭 → check API 응답 |
| `afterfail:mission-check-commit` | 완료 확인 클릭 → 화면 반영 |
| `afterfail:dashboard-filter-loading` | 필터 클릭 → 로딩 표시 |

실측 (2026-09-01, mock 백엔드 · Chromium · 1440x900):

| 항목 | 목표 | 실측 |
|---|---|---|
| 필터 클릭 → 로딩 표시 | 100ms 이내 | **11ms** |
| 자동 채점 API | 300ms | **16ms** |
| 채점 → 화면 반영 | — | **80ms** (UI 추가분 64ms) |
| 중복 API 호출 | 0건 | **0건** |
| production JS gzip | 기준선 133.75kB +20% 이내 | **141.5kB (+5.8%)** |
| AI 튜터 응답 | 1.5초 (백엔드 목표) | 538ms — **mock 이라 참고값** |

**AI 1.5초는 mock 으로 검증할 수 없다.** 실제 LLM 응답 시간은 FE-19 에서 측정한다.

### 폴링 간격

`src/config/polling.ts`. 탭이 백그라운드면 늘어나고, 연속 실패는 지수 backoff
(상한 30초)를 받는다.

| 대상 | 보임 | 숨김 |
|---|---|---|
| 미션·시나리오 상태 | 5초 | 15초 |
| 프로필 | 15초 | 60초 |
| 대시보드 | 15초 | 60초 |
| Grafana readiness | 1초 (시도 20회 상한) | 5초 |

남은 시간 표시는 서버 폴링과 분리된 로컬 1초 tick 이다 — 폴링을 늦춰도
카운트다운이 튀지 않는다.

---

## 7. 장애 시 확인 순서

| 증상 | 먼저 볼 것 |
|---|---|
| 로그인은 되는데 탭이 안 보임 | `GET /api/environments` 응답. 백엔드 `core/environments.py` |
| CORS 오류 | 브라우저 주소창의 **origin**. [ENV_SETUP.md](ENV_SETUP.md) 판정 표 |
| "터미널 세션을 준비하는 중"이 오래 지속 | 백엔드 로그의 `sandbox probe failed`. Linux 최초 생성은 20여 회 반복 후 성공한다 |
| 터미널 명령이 거절됨 | `command_validator.py` 의 해당 환경 정책. 서버 detail 이 이유를 담고 있다 |
| 튜터가 "질문 횟수 제한" | 백엔드 `CHAT_RATE_LIMIT_PER_MINUTE` (기본 12/분, 사용자당) |
| 튜터 응답에 "준비된 안내로 대체" | `AI_BACKEND=mock` 이거나 프로바이더 실패 (`fallback_used`) |
| 관측 패널이 비어 있음 | 그 환경에 대시보드가 없는 것이 정상이다 (위 §2 표) |
| 대시보드 숫자가 "데이터 없음" | 완료 0건과 조회 실패는 다르게 표시된다. 조회 실패면 상단에 경고가 함께 뜬다 |

로그 위치:

- 프론트: 브라우저 콘솔 (Grafana probe 실패는 `console.warn` 으로 남는다)
- 백엔드: `docker logs afterfail-backend-local`
- Vite dev: 실행한 터미널

---

## 8. 알려진 제한

- **Docker 샌드박스는 privileged DinD 다.** 사용자가 칠 수 있는 명령을 좁히는 것이
  실질적 방어선이므로 자동완성이 백엔드 정책보다 넓어지면 안 된다.
- **Application / Database 환경은 캡스톤2 스코프에서 제외**됐다. 탭이 아니라
  "후속 연구"로 표기한다 (`RESEARCH_TOPICS`).
- **Docker / Linux 관측 대시보드가 없다.** `infra/monitoring` 은 백엔드 소유 경로다.
- **AI 시나리오 해금은 계정 단위**다. 환경별로 따로 열리지 않는다.
- 브라우저: 최신 Chromium 계열에서 확인했다. xterm.js 와 WebSocket 을 쓰므로
  IE 계열은 지원하지 않는다.
- 반응형은 390px / 1366x768 / 1440x900 에서 확인했다. 768px 이하에서는 미션·터미널을
  탭으로 전환하며, 전환 시 Terminal 을 unmount 하지 않아 연결이 끊기지 않는다.

---

## 9. 백엔드에 요청해 둔 것

프론트가 우회해 둬서 화면은 동작하지만, 반영되면 우회를 걷어내야 한다.

| 내용 | 영향 |
|---|---|
| `CORSMiddleware` 에 `expose_headers=["Retry-After"]` | cross-origin 에서 429 남은 초를 못 읽어 "잠시 후"로만 안내한다 |
| `ChatResponse` 에 `environment` 추가 | 튜터 환경 배지를 응답으로 교차 검증할 수 없다 |
| `_CAPABILITIES` 갱신 | docker/linux 의 `ai_scenario`·`tutor` 가 실제로 동작하는데 목록에 없다 |
| `LinuxPolicy._check_paths` 플래그 값 오인 | `truncate -s 0 <path>` 가 거절돼 복구 명령으로 못 쓴다 |
| `websocket_handler.py` 의 kubectl 배너 | Linux 터미널에도 "Type 'kubectl' commands" 가 출력된다 |
