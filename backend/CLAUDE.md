# Backend - AfterFail

## 개요
FastAPI 기반 백엔드. 웹 터미널, AI 튜터, 게임 로직, 채점 시스템, AI 시나리오 생성 담당.

## 캡스톤2 작업 기준

구현은 [docs/backend-capstone2-semester-plan.md](../docs/backend-capstone2-semester-plan.md)의
작업 ID(`BE-00`~`BE-28`) 단위로 진행한다. **한 번에 하나의 `BE-xx`만** 구현하고,
선행 조건과 API 계약을 먼저 확인한다. 로드맵 표와 팀 협업·Git 규칙은 루트 [AGENTS.md](../AGENTS.md) 참고.

### 현재 P0 결손

| 결손 | 위험 | 해소 |
|---|---|---|
| ~~`CommandExecutor`가 host에서 `shell=True` 실행~~ | ~~host RCE~~ | **BE-05 완료** |
| ~~WebSocket이 session 소유권을 검증하지 않음~~ | ~~타 사용자 세션 오용~~ | **BE-06 완료** |
| environment가 session 생성·명령 실행까지 미연결 | Docker 탭에서 K8s 명령 실행 | BE-03·BE-07 |
| ~~active chaos ID가 프로세스 메모리 dict에만 존재~~ | ~~서버 재시작 시 정리 불가~~ | **BE-08 완료** |

### 테스트 기준선 (BE-01 완료 기준)

```bash
cd backend && source venv/bin/activate && python -m pytest -q
# → 38 passed
```
`pytest.ini`에서 `asyncio_mode = strict`를 명시한다. 기존 async 테스트가
`@pytest.mark.asyncio`를 붙여 쓰고 있어 strict가 의도에 맞고, 마크를 빠뜨린 async
테스트가 조용히 통과하지 않고 드러난다. `pytest-asyncio==0.23.3`은 requirements와
venv 양쪽에 있으며 async 테스트는 skip되지 않는다.

**실패 테스트를 삭제하거나 xfail로 숨겨서 녹색을 만들지 않는다.**

## 기술 스택
- Python 3.11, FastAPI, Pydantic v2
- SQLAlchemy async + PostgreSQL (asyncpg)
- JWT 인증 (python-jose, passlib)
- LangChain + Qdrant (RAG)
- Kubernetes Python Client
- WebSocket (실시간 터미널)
- OpenAI gpt-4o-mini / Google Gemini (시나리오 생성 + 튜터)

## 프로젝트 구조
```
app/
├── main.py              # FastAPI 앱, 라우터 등록, lifespan (DB init → seed → Qdrant auto-ingest)
├── models.py            # SQLAlchemy 모델
│                        #   User, TerminalSession, CommandLog
│                        #   Mission, MissionAttempt (attempt_type, scenario_id, environment, chaos_id, sandbox_id)
│                        #   GeneratedScenario, ValidationRule
│                        #   TutorMessage (DB 모델 정의 완료, 인메모리 히스토리 병행)
├── schemas.py           # Pydantic 스키마 (요청/응답)
├── api/
│   ├── deps.py          # 의존성 (get_db, get_current_user)
│   ├── auth.py          # POST /api/auth/register, /api/auth/login
│   ├── terminal.py      # WS /ws/terminal/{session_id}, POST /api/terminal/sessions
│   ├── missions.py      # 고정 4개 미션 API (AI 시나리오 attempt 혼용 방어 처리됨)
│   ├── scenarios.py     # AI 시나리오 API (/api/scenarios/*)
│   ├── dashboard.py     # 대시보드/리더보드/업적 API
│   ├── environments.py  # GET /api/environments (환경 가용 상태)
│   └── chat.py          # AI 튜터 채팅 API (정적 미션 + AI 시나리오 모두 지원)
├── core/
│   ├── config.py        # Settings (환경변수, AI 백엔드 선택 - mock/openai/gemini)
│   ├── environments.py  # 환경 상수·EnvironmentId(Literal)·검증·가용성(availability)
│   ├── database.py      # async engine, session (스키마 관리는 Alembic 담당)
│   ├── metrics.py       # Prometheus 메트릭
│   └── security.py      # JWT, 비밀번호 해싱
├── services/
│   ├── command_validator.py      # 환경별 명령 정책 (Kubectl | Docker | Linux)
│   ├── command_executor.py       # 샌드박스 Pod exec 실행 (Sandbox | Mock)
│   ├── websocket_handler.py      # WebSocket 연결·동시성·CommandLog
│   ├── mission_service.py        # 고정 미션 오케스트레이터
│   ├── chaos_injector.py         # 장애 주입 (Mock | ChaosMesh), _CHAOS_HANDLERS 레지스트리
│                                 #   revert(chaos_id, namespace) — 재시작 후에도 복구 가능
│   ├── chaos_plan.py             # ChaosPlan, ChaosPlanCompiler (allowlist 안전장치)
│   ├── scenario_service.py       # AI 시나리오 생성/시작/완료 오케스트레이터
│   ├── validation_service.py     # 해결 검증 (Mock | K8s API | Prometheus), chaos_type → _CHECKS 레지스트리
│   ├── validation_rule_service.py # AI 생성 검증 조건 저장/실행 + K8s fallback, rule_type → _RULE_RUNNERS 레지스트리
│   ├── promql_guard.py           # PromQL 안전성 검사 (namespace 격리, allowlist)
│   ├── runtime_context.py        # 환경별 관측 수집 → 공통 스키마 (AI 계층 계약)
│   ├── runtime_redaction.py      # AI 로 나가는 값에서 토큰·비밀번호 제거
│   ├── reconciliation_service.py # 재시작 시 진행 중 attempt·장애 정리
│   ├── scoring_service.py        # 점수 계산 (시간/힌트 감점)
│   ├── analytics_service.py      # 대시보드/리더보드/업적/티어 계산
│   ├── k8s_setup.py              # 사용자 K8s 네임스페이스 자동 생성
│   ├── sandbox_service.py        # 환경별 샌드박스 (kubernetes=toolbox, docker=DinD)
│   ├── docker_chaos_injector.py  # Docker 환경 장애 주입 (DinD 안 docker CLI)
│   ├── docker_validation_service.py # Docker 환경 해결 검증 (샌드박스 exec)
│   ├── linux_chaos_injector.py   # Linux 환경 장애 주입 (supervisor 신호 방식)
│   ├── linux_validation_service.py # Linux 환경 해결 검증 (/proc·df 구조적 판독)
│   └── sandbox_assets/           # 샌드박스에 넣는 스크립트 (linux_supervisor.sh)
│   ├── service_factory.py        # (environment, backend) 조합 레지스트리로 구현체 선택
│   ├── seed_data.py              # 미션 시드. (environment, level) 기준 upsert
│   └── qdrant_init.py            # 서버 시작 시 Qdrant knowledge-base 자동 ingestion
└── ai/
    ├── __init__.py
    ├── tutor_service.py      # AI 튜터 어댑터 (Mock/OpenAI/Gemini, K8s Pod 상태 실시간 조회)
    ├── scenario_agent.py     # 시나리오 생성 AI (Mock fixture + OpenAI/Gemini)
    └── validation_agent.py   # LLM 기반 AI 시나리오 완료 판정 (Mock + OpenAI/Gemini 구현 완료)
```

## API 엔드포인트

### 인증
- `POST /api/auth/register` - 회원가입
- `POST /api/auth/login` - 로그인 (JWT 발급, form-data 형식)
- `GET /api/auth/me` - 프로필 조회 (완료 미션 수, 총 점수 포함) 🔒
- `POST /api/auth/logout` - 로그아웃 (204 반환) 🔒

### 환경
- `GET /api/environments` - 훈련 환경 가용 상태 목록 🔒
  - Response: `{"items":[{"id":"kubernetes","status":"available","capabilities":[...]}, ...]}`
  - `available`은 실제로 세션 생성·주입·검증이 가능한 환경, `preparing`은 계약상 존재하나 미구현
  - source of truth는 `core/environments.py`. label·설명 문구는 프론트 책임

### 터미널
- `POST /api/terminal/sessions` - 터미널 세션 생성 + K8s 네임스페이스/nginx Pod 자동 생성 🔒
- `WS /ws/terminal/{session_id}?token=JWT` - 웹 터미널
  - 연결 시 서버가 결정하는 값: `user_id`←JWT, `session`←`id + user_id + is_active`,
    `namespace`·`environment`←session, `sandbox`←`SandboxService.reference_for(...)`
  - **클라이언트가 보낸 namespace/pod는 어느 단계에서도 쓰지 않는다.**
  - close code (전달을 위해 거절 시에도 `accept()` 후 `close()`)

  | code | 의미 |
  |---|---|
  | 4000 | 같은 세션에 새 연결이 들어와 이전 연결 종료 |
  | 4001 | 토큰 없음·무효 |
  | 4003 | 세션 소유자 불일치 또는 비활성 |
  | 4004 | 세션·샌드박스 없음 (세션 id 형식 오류 포함) |
  | 4010 | 환경 미가용 |

### 고정 미션 (4개 레벨 튜토리얼)
> AI 시나리오 attempt가 진행 중일 때 이 API들은 404를 반환한다 (혼용 방지)

- `GET /api/missions/?environment=kubernetes` - 미션 목록 (잠금 상태 포함)
  - **잠금은 같은 환경 안에서만 계산된다.** Kubernetes level 4 완료가 Docker level 2를
    열지 않는다. `environment`는 호환을 위해 기본값이 있지만 프론트는 명시적으로 보낸다.
- `POST /api/missions/start` - 미션 시작
- `GET /api/missions/status` - 진행 중 미션 상태
- `POST /api/missions/check` - 해결 여부 확인
- `POST /api/missions/abandon` - 미션 포기
- `POST /api/missions/hint` - 힌트 사용
- `POST /api/missions/debug/resolve` - (Mock 전용) 수동 해결

### AI 시나리오 (캡스톤 1 핵심)
- `GET /api/scenarios/unlock-status` - AI 모드 잠금 해제 상태 (기본 4개 미션 완료 필요) 🔒
- `POST /api/scenarios/start-random` - 난이도 선택 → AI 시나리오 생성+장애 주입 원스텝 🔒
- `GET /api/scenarios/status` - 현재 AI 시나리오 진행 상태 🔒
- `POST /api/scenarios/current/check` - AI 시나리오 완료 검증 🔒
- `POST /api/scenarios/current/abandon` - AI 시나리오 포기 🔒
- `POST /api/scenarios/current/hint` - 힌트 사용 (감점) 🔒
- `POST /api/scenarios/debug/resolve` - (Mock 전용) 수동 해결 🔒

### 대시보드 / 게이미피케이션
- `GET /api/dashboard/stats?environment=all|kubernetes|docker|linux` - 내 통계 🔒
  - `all`이면 전체 합계와 `environment_stats`(환경별 분해)를 함께 준다
  - 특정 환경이면 그 환경만 집계하고 `environment_stats`는 비운다
- `GET /api/dashboard/learning-curve?environment=...` - 미션 시도 히스토리 🔒
- `GET /api/leaderboard` - 전체 리더보드 🔒
- `GET /api/achievements` - 업적 목록 및 달성 여부 🔒

### AI 튜터
- `POST /api/chat/` - AI 튜터에게 질문 🔒
  - Request: `{ "message": str, "hint_level": 0~3 }`
  - Response: `{ "response": str, "hint_level": int, "mission_name": str }`
  - 진행 중인 미션(고정/AI) 있어야 사용 가능
  - AI 시나리오와 정적 미션 모두 지원 (attempt_type 자동 분기)

## 미션 시스템 아키텍처

### 터미널 명령 실행 경로 (BE-05)

```
사용자 입력
  → CommandValidator: 셸 메타문자 거절 → shlex.split → argv allowlist → namespace 강제
  → SandboxRef (서버가 DB 세션에서 생성)
  → SandboxCommandExecutor: connect_get_namespaced_pod_exec 로 Pod 안에서 argv 실행
```

- **호스트 셸을 쓰지 않는다.** `shell=True` / `create_subprocess_shell` /
  `subprocess.run` 은 `tests/test_terminal_security.py`가 AST로 검사해 0건을 강제한다.
- 셸 메타문자(`|`, `>`, `<`, `&&`, `;`, 백틱, `$(`, 개행)는 파싱 이전에 거절한다.
  argv로 넘기면 리터럴이 되지만, 사용자가 기대한 동작과 달라지므로 조용히 삼키지 않는다.
- 한 세션의 동시 실행은 1개(`asyncio.Lock`). 실행 중 추가 명령은 오류로 알린다.
- 명령 원문과 출력 본문은 info 로그에 남기지 않는다(session_id·exit_code·소요시간만).

### 고정 미션 (튜토리얼)
- 환경변수 `CHAOS_BACKEND=mock|chaos_mesh`, `VALIDATION_BACKEND=mock|k8s|prometheus`로 전환
- `POST /api/terminal/sessions` 호출 시 K8s 네임스페이스(`user-{uuid}`) + nginx Deployment 자동 생성
- 미션 시작 시 해당 네임스페이스에 chaos 주입

### Chaos Mesh 장애 주입 방식 (chaos_injector.py)
| chaos_type | 방식 | 사용자 Fix |
|---|---|---|
| `pod_failure` | nginx 이미지를 `nginx:wrongtag`로 패치 → ImagePullBackOff | `kubectl set image deployment/nginx nginx=nginx:latest` |
| `memory_stress` | nginx 메모리 limit을 6Mi로 낮춤 + StressChaos 64MB 압박 → OOMKilled | `kubectl patch deployment/nginx`으로 memory limit 상향 |
| `service_misconfig` | webapp Deployment + 잘못된 selector의 Service 생성 | `kubectl patch svc webapp-svc -p '{"spec":{"selector":{"app":"webapp"}}}'` |
| `network_latency` | nginx readinessProbe에 존재하지 않는 경로 주입 + 롤아웃 전략을 `maxSurge=0`으로 조정 | `kubectl patch deployment nginx -p '...'`으로 readinessProbe 제거 |
| `wrong_image_registry` | private registry 이미지로 패치 → unauthorized ImagePullBackOff | `kubectl set image deployment/nginx nginx=nginx:latest` |
| `secret_ref_missing` | 존재하지 않는 Secret envFrom 참조 → CreateContainerConfigError | Secret 생성 또는 envFrom 제거 |
| `pvc_unbound` | 존재하지 않는 storageClass PVC 생성 + 마운트 → Pod Pending | PVC 삭제 및 deployment에서 volume/volumeMount 제거 |
| `cpu_throttle` | CPU limit 1m + 빡빡한 readinessProbe → Running이지만 0/1 Not Ready | `kubectl patch deployment nginx`로 CPU limit 상향 + readinessProbe 제거 |

### AI 시나리오 시스템 (scenario_service.py)

**흐름:**
```
POST /api/scenarios/start-random
  → ScenarioAgent.generate() (Mock or OpenAI/Gemini)
  → ChaosPlanCompiler.compile() (allowlist 안전장치)
  → ValidationRuleService.guard_and_store() (PromQLGuard 검사)
  → ChaosInjector.inject(chaos_type, namespace) (기존 inject() 재사용)
  → MissionAttempt 생성 (attempt_type="ai_scenario")
```

**검증 흐름:**
```
POST /api/scenarios/current/check
  → ValidationRuleService.check_rules() (k8s 타입 룰 우선)
  → 미검증 시 k8s_check_by_fault_type() fallback (fault_type → K8s API 직접 검증)
  → 통과 시 chaos cleanup + 점수 계산
```

**fault_type → K8s 검증 쿼리 매핑:**
| fault_type | K8s 검증 쿼리 |
|---|---|
| image_pull_error, pod_failure, crash_loop, probe_failure, oom_killed, memory_stress, network_latency | `deployment:nginx:running` |
| service_selector_mismatch, service_misconfig | `service:webapp-svc:endpoints` |

### 동시성과 재시작 복구 (BE-22)

#### 시간 초과 정리가 status 조회에만 의존했다

지금까지 timeout 처리는 **사용자가 status를 조회할 때만** 일어났다. 사용자가 브라우저를
닫고 돌아오지 않으면 **주입된 장애가 클러스터에 그대로 남고**, 서버가 재시작되면 그
사실조차 아무도 모른다.

startup에서 `in_progress` attempt를 훑어 시간 초과된 것을 정리한다. BE-08에서 `chaos_id`를
DB에 저장하도록 바꿨기 때문에 프로세스 메모리 없이도 되돌릴 수 있다.

- 아직 시간이 남은 시도는 건드리지 않는다 (사용자가 계속 풀고 있다)
- 되돌린 뒤 `chaos_id`를 비운다. 다음 정리에서 같은 작업을 반복하지 않는다
- **정리에 실패해도 attempt는 종료 처리한다.** 열린 채로 두면 사용자가 새 미션을
  시작할 수 없다
- **하나가 실패해도 나머지는 계속 처리하고, 예외를 기동 밖으로 내보내지 않는다.**
  기동 경로에서 예외가 나가면 서버가 뜨지 않는다

#### 동시 시작은 사용자 오류로 돌려준다

사용자당 `in_progress` attempt는 DB partial unique index로 1개다(BE-02). 동시 요청 두
개가 앞의 조회를 모두 통과하면 커밋 시점에 하나가 걸린다. 이는 서버 오류가 아니라
설명 가능한 상황이므로 `IntegrityError`를 **"이미 진행 중인 미션이 있습니다"**로 바꾼다.

이때 **이미 주입된 장애를 되돌린다.** 기록이 실패했는데 장애가 남으면 고아가 된다.

### 환경별 분석 (BE-21)

```json
"environment_stats": {
  "kubernetes": {"completed": 4, "average_score": 88, "average_mttr": 520,
                 "hints_used": 2, "competency": 82},
  "docker": {"completed": 0, "average_score": 0, "average_mttr": 0,
             "hints_used": 0, "competency": null}
}
```

**시도가 없으면 `competency`는 `null`이다.** 0으로 두면 "해봤는데 못했다"와
"아직 안 했다"가 구분되지 않는다.

`completed` 상태만 집계한다. **포기하거나 실패한 시도를 MTTR에 넣으면 시간 지표가
실제 복구 능력을 나타내지 못한다.**

#### competency 계산식

```
speed  = clamp(100 - average_mttr / TARGET_MTTR_SECONDS * 50, 0, 100)
hint   = clamp(100 - hints_per_completion * 15, 0, 100)
competency = round(0.5 * average_score + 0.3 * speed + 0.2 * hint)
```

`TARGET_MTTR_SECONDS`(기본 900초)는 설정값이다. 미션 `time_limit`이 600~2100초로
환경마다 달라 대표값을 기준으로 삼는다.

#### 학습 곡선의 키 분리

`mission_id`만으로 묶으면 **AI 시나리오는 전부 `None`이라 한 덩어리가 된다.**
서로 다른 시나리오가 같은 과제를 반복 시도한 것처럼 집계돼 `attempt_number`가
계속 증가한다.

```python
"scenario:{scenario_id}"  if attempt_type == "ai_scenario" else  "mission:{mission_id}"
```

### AI 시나리오 실행 계약 (BE-20)

#### 점수를 승인하는 유일한 기준은 mechanical validation

이전 구현은 LLM 판정이 confidence 0.7 이상이면 **`resolved`를 덮어썼다.**

```python
if ai_judgment.confidence >= 0.7:
    resolved = ai_judgment.resolved   # ← LLM 오판이 곧 완료 처리
```

LLM이 오판하는 순간 **사용자가 고치지 않았는데도 완료 처리된다.** 지금은 LLM 판정을
`advisory_only: True`로 저장만 하고 `resolved`는 mechanical 결과만 따른다.
테스트가 이 코드가 되돌아오지 않는지 감시한다.

#### 환경별 허용 fault type

`allowed_fault_types(environment)`가 AI에 전달되는 목록이자 컴파일 단계의 거절 기준이다.
각 환경의 목록이 **그 환경 injector가 지원하는 chaos_type과 정확히 일치**하는지
테스트가 확인한다.

| 환경 | fault type |
|---|---|
| kubernetes | 19종 (`image_pull_error`, `oom_killed`, …) |
| docker | `docker_network_disconnect`, `docker_container_stopped`, `docker_cpu_throttle` |
| linux | `linux_disk_pressure`, `linux_cpu_saturation`, `linux_process_flood` |

- 다른 환경의 fault를 주면 `ChaosPlanCompileError`로 거절한다
- **AI가 만든 시나리오의 environment가 요청과 다르면 거절한다.** 미구현 환경 요청을
  다른 환경 시나리오로 대체하지 않는다
- docker/linux는 injector가 고정 절차로 주입하므로 **AI가 임의 step을 끼워 넣을 수 없다**

#### 검증 기록

`last_validation_result`에 `environment` · `rules` · `checked_at` · `duration_ms`를 남긴다.
LLM 판정은 `advisory_only` 표시와 함께 저장된다.

#### AI 계층이 돌려주는 형태 (schemas.py)

```python
TutorResult(message, hint_level, environment, sources, observations_used,
            token_usage, latency_ms, fallback_used, error_code)
ValidationJudgment(resolved, reason, confidence, advisory_only=True)
```

`TutorSource`에는 **외부 URL 필드가 없다.** 링크를 그대로 렌더링하면 프론트가 임의
외부 주소를 열게 된다. 표시 가능한 `title` / `path` / `snippet`만 넘긴다.

### RuntimeContext — AI 계층 계약 (BE-19)

환경마다 수집 방법이 다르지만 **출력 스키마는 같다.** AI 담당이 환경별로 분기하지
않아도 되도록 하기 위한 계약이다.

```json
{
  "environment": "docker",
  "scope": {"namespace": "user-...", "sandbox_id": "..."},
  "mission": {"title": "...", "difficulty": "...", "student_brief": "..."},
  "recent_user_commands": [],
  "observations": {},
  "metrics": {},
  "logs": []
}
```

| 환경 | observations |
|---|---|
| kubernetes | `kubernetes_state` (pods / deployments / services / events) |
| docker | `containers`, `networks` |
| linux | `processes`, `disk`, `memory`, `load` |

**부분 실패를 허용한다.** 수집 하나가 실패하거나 느려도(기본 3초 timeout) 나머지는
그대로 넘긴다. 관측 실패 때문에 튜터 응답이 통째로 막히면 안 된다.

**정답이 아니라 관측값만 넘긴다.** 무엇이 문제인지는 AI가 판단한다.

#### 민감정보 제거 (runtime_redaction.py)

관측값은 그대로 LLM 프로바이더로 나간다. 토큰·비밀번호·환경변수를 지운다.

```
--from-literal=password=hunter2  → --from-literal=password=***REDACTED***
Authorization: Bearer abc.def.ghi → Authorization=***REDACTED***
{"env": {...}}                    → {"env": "***REDACTED***"}
```

키가 붙은 값은 **줄 끝까지** 지운다. `Authorization: Bearer a.b.c`처럼 값이 여러
토큰인 경우 한 토큰만 지우면 나머지가 남는다. 정상 명령(`kubectl get pods`)은
건드리지 않는다.

> **하위 호환**: `namespace` / `kubernetes_state` / `prometheus` 키를 함께 남긴다.
> 튜터 구현(`app/ai/`)은 AI 담당 소유라 한 PR에서 함께 바꿀 수 없다. AI가 새 스키마로
> 옮긴 뒤 제거한다.

### Linux 환경 활성화 (BE-18)

**필수 환경 3종이 모두 열렸다.** `GET /api/environments`가 kubernetes·docker·linux를
전부 `available`로 반환한다.

| level | 미션 | chaos_type | 사용자 복구 |
|---|---|---|---|
| 1 | 늘어나는 그림자 | `linux_process_flood` | `pkill -f afterfail-worker` |
| 2 | 가득 찬 창고 | `linux_disk_pressure` | `rm /tmp/afterfail/afterfail-fill.dat` |
| 3 | 보이지 않는 과부하 | `linux_cpu_saturation` | `pkill -f afterfail-cpuburn` |

난이도는 **발견하기 쉬운 순서**다. 프로세스 폭증은 `ps`에 바로 드러나고, 디스크 압박은
`df`를 봐야 알며, CPU 포화는 프로세스가 둘뿐이라 목록만 봐서는 눈에 띄지 않는다.

Linux capabilities도 Docker와 같이 `static_mission` / `terminal`만 알린다.

#### 검증에서 반드시 지켜야 하는 것 — 자기 명령줄 제외

`grep -c afterfail-worker`를 쓰면 **검사를 실행하는 `sh`와 `grep` 자신의 명령줄에도**
그 문자열이 들어가 항상 2 이상이 나온다. 사용자가 제대로 복구해도 영영 통과하지 못한다.
`pkill -f afterfail-`도 같은 이유로 **자기를 먼저 죽여** 정리가 중단된다.

첫 글자를 문자 클래스로 감싸 해결한다.

```
grep -c '[a]fterfail-worker'      pkill -f '[a]fterfail-'
```

패턴 자체는 매치되지 않고 실제 프로세스만 잡힌다. 회귀 테스트가 이 패턴을 고정한다.

#### 검증 지연

외부 의존이 없다. Kubernetes API도 Prometheus도 쓰지 않고 샌드박스 exec 한 번으로
끝난다. 실측 **평균 92ms**로 계획서의 300ms 목표 안에 든다. `details.duration_ms`로
매 검증의 소요 시간을 남긴다.

### Linux 장애 (linux_chaos_injector.py, BE-17)

**장애 워크로드를 exec으로 직접 띄울 수 없다.** Kubernetes exec으로 만든 백그라운드
프로세스는 세션이 끝나면 containerd가 프로세스 그룹째 정리한다(실측: `setsid`/`nohup`/
`</dev/null` 모두 무효). 그래서 샌드박스의 **PID 1을 supervisor 스크립트**로 두고,
injector는 신호 파일만 만든다.

```
injector → /tmp/afterfail/.signals/<name> 생성
              ↓ (supervisor 가 2초마다 폴링)
supervisor → 워크로드 실행 → .done 표시
```

`.done` 표시가 있으면 다시 실행하지 않는다. **사용자가 워크로드를 정리하면 그대로
복구된다.** 재실행하면 복구가 불가능해진다.

| chaos_type | 장애 | 사용자 복구 |
|---|---|---|
| `linux_disk_pressure` | 작업 디렉터리(tmpfs)를 채움 | `rm /tmp/afterfail/afterfail-fill.dat` |
| `linux_cpu_saturation` | CPU를 태우는 워커 2개 | `pkill -f afterfail-cpuburn` |
| `linux_process_flood` | 프로세스 120개 생성 | `pkill -f afterfail-worker` |

#### 계획서의 zombie/orphan을 제외한 이유 (실측)

이 이미지의 busybox sh는 자식을 곧바로 회수해 **좀비가 유지되지 않는다.**
중첩 셸로 exec 세션 안에서는 좀비를 만들 수 있었지만 supervisor가 띄운 워크로드에서는
재현되지 않았다. 관측되지 않는 장애는 훈련이 될 수 없어 CPU 포화로 대체했다.

#### 워크로드 이름 규칙

명령 정책이 `afterfail-`로 시작하는 대상만 신호를 허용하므로 워크로드를 그 이름으로
띄워야 한다. **바이너리를 복사해 이름을 바꾸는 방식은 쓸 수 없다** — 이 이미지의 명령은
전부 busybox 심볼릭 링크이고 busybox는 `argv[0]`으로 applet을 고르기 때문에
`applet not found`로 실행되지 않는다. 대신 그 이름의 셸 스크립트를 만들어 띄운다.
스크립트 안에서 `exec`을 쓰지 않는다 — `exec`하면 명령줄에서 이름이 사라져
`pkill -f`로 찾을 수 없다.

#### 안전 기준

- 작업 디렉터리가 **크기 제한된 tmpfs**라 호스트 디스크를 채우지 않는다
- 프로세스 생성 수를 PID 상한보다 낮게 묶는다. **PID 고갈로 샌드박스가 마비되면
  복구도 못 한다**
- 모든 워크로드에 종료 시점(24시간)이 있고 revert가 즉시 정리한다
- 모든 장애가 컨테이너 cgroup 안에서 끝나 호스트 OOM-Killer를 유발하지 않는다

### Linux 샌드박스와 명령 정책 (BE-16)

**허용 명령은 실제 컨테이너에서 동작하는 것만 넣었다.** 되지 않는 명령을 목록에 두면
사용자가 그것을 정답으로 착각한다.

| 동작 | 명령 |
|---|---|
| 조회 | `ps` `free` `df` `du` `top` `uptime` `iostat` `ss` `netstat` `lsof` `pstree` |
| 파일 읽기 | `cat` `head` `tail` `wc` `ls` `stat` `find` — **경로 제한** |
| 복구 (확인 필요) | `kill` `pkill` `rm` `truncate` — **대상 제한** |

#### 계획서가 언급했지만 제외한 명령 (실측)

| 명령 | 이유 |
|---|---|
| `journalctl` / `systemctl` | systemd가 없다. 어떤 이미지에서도 동작하지 않는다 |
| `dmesg` | 커널 링 버퍼 접근이 막혀 있다 (privileged가 필요한데 주지 않는다) |

계획서의 "systemctl status 대체"는 `ps` / `top`이 담당한다.

#### 경로·대상 제한

- **읽기 허용**: `/proc`, `/sys/fs/cgroup`, `/tmp/afterfail`, 상대경로.
  `..`로 탈출하는 경로는 거절한다
- **쓰기·삭제 허용**: `/tmp/afterfail`만
- **신호 대상**: PID 또는 `afterfail-`로 시작하는 훈련 프로세스만.
  **PID 1은 샌드박스 자체라 거절한다**

#### 확인 요청 전에 정책을 먼저 검사한다

`rm -rf /`나 `kill 1`처럼 **확인해도 통과할 수 없는 명령은 즉시 거절**한다.
"확인 필요"로 답하면 사용자가 잘못된 방향으로 시도하게 된다. Docker 환경에도 같은
개선이 적용돼, 허용되지 않은 대상은 확인 단계 이전에 거절된다.

#### 샌드박스 격리

Docker 환경과 달리 **privileged를 쓰지 않는다.** 데몬이 필요 없기 때문이다.

- `hostPID` / `hostNetwork` / `hostIPC` 모두 비활성 — 장애는 컨테이너 cgroup 범위 안에서만
- ServiceAccount 토큰 미마운트
- `allowPrivilegeEscalation: false`
- CPU / 메모리 / **ephemeral-storage** 상한

> **`IMPLEMENTED_ENVIRONMENTS`에 linux는 아직 없다.** 샌드박스는 뜨지만
> injector/validator가 없어(BE-17/BE-18) 미션을 시작할 수 없다.

### Docker 환경 활성화 (BE-14)

`IMPLEMENTED_ENVIRONMENTS`에 docker가 들어가 **`GET /api/environments`에서 Docker가
`available`로 나간다.** 프론트 Docker 탭이 열린다.

```json
{"id": "docker", "status": "available", "capabilities": ["static_mission", "terminal"]}
```

**capabilities는 실제로 제공하는 것만 알린다.** 없는 기능을 광고하면 프론트가 열 수 없는
화면을 그린다.

| 기능 | Docker | 이유 |
|---|---|---|
| `static_mission` | 제공 | 미션 3개 시드 + injector + validator |
| `terminal` | 제공 | 샌드박스 exec + 명령 정책 |
| `ai_scenario` | 미제공 | 시나리오 생성이 Kubernetes fault type 기준 (BE-20) |
| `tutor` | 미제공 | RuntimeContext 수집이 Kubernetes 전용 (BE-19) |
| `observability` | 미제공 | Grafana/Prometheus 대시보드가 K8s 메트릭 기준 |

#### Docker 미션 시드

난이도는 **발견하기 쉬운 순서**로 매겼다.

| level | 미션 | chaos_type |
|---|---|---|
| 1 | 멈춰버린 컨테이너 | `docker_container_stopped` — `docker ps -a`로 바로 보인다 |
| 2 | 고립된 컨테이너 | `docker_network_disconnect` — running이라 알아채기 어렵다 |
| 3 | 숨 막히는 컨테이너 | `docker_cpu_throttle` — running이고 연결도 되는데 느리다 |

#### 검증 (docker_validation_service.py)

`docker inspect`를 **필드별 `--format`으로 구조적으로 읽는다.** inspect 전체 출력은
exec 채널을 거치며 표준 JSON으로 오지 않아 `json.loads`가 실패한다(BE-13 실측).

- CPU 회복은 기준값의 50% 이상이면 통과한다. 사용자가 정확히 같은 값을 넣지 않아도
  훈련 목적은 달성되고, `--cpus`로 제한을 아예 푼 경우(`0`)도 해결로 본다
- `details`는 내부 진단용이고 **`message`에는 정답을 담지 않는다**

### Docker 장애 (docker_chaos_injector.py, BE-13)

Chaos Mesh는 Kubernetes 전용이라 이 환경에는 쓸 수 없다. DinD 샌드박스 안에서
docker 명령으로 장애를 만든다.

| chaos_type | 장애 | 사용자 복구 |
|---|---|---|
| `docker_network_disconnect` | 훈련 컨테이너를 training-net에서 분리 | `docker network connect training-net training-app` |
| `docker_container_stopped` | 컨테이너 중지 | `docker start training-app` |
| `docker_cpu_throttle` | CPU 상한을 0.05로 축소 | `docker update --cpus 1 training-app` |

**등록 기준: 사용자가 BE-12 명령 정책 안에서 실제로 복구할 수 있는 장애만 넣는다.**
테스트가 각 복구 명령을 실제 validator에 통과시켜 이 계약을 고정한다.

#### 계획서의 volume/mount error를 제외한 이유 (실측)

- `docker update`에 볼륨·마운트 옵션이 없어 실행 중 변경이 불가능하다
- 사용 중인 볼륨은 삭제가 거부된다 (`volume is in use`)
- 컨테이너를 멈춰도 참조가 남아 삭제되지 않는다

유일한 경로가 `docker rm` 후 볼륨 없이 `docker run`인데, 복구하려면 사용자가
`docker run`을 칠 수 있어야 한다. 그 명령은 임의 이미지 실행 위험 때문에 BE-12에서
차단했다. 대신 컨테이너 중지 장애를 넣었다.

#### 메모리 대신 CPU를 쓰는 이유 (실측)

docker는 메모리 상한을 올릴 때 `memory+swap >= memory`를 요구한다. 사용자가
`--memory`만 쳐서는 `memory+swap limit should be >= memory limit`으로 복구가 실패하고,
항상 `--memory-swap`을 짝으로 요구하는 것은 훈련 난이도가 아니라 함정이다.
CPU는 낮추기/올리기 왕복이 그대로 동작한다.

### Docker 명령 정책 (BE-12)

샌드박스가 privileged DinD 이므로 **사용자가 칠 수 있는 명령을 좁히는 것이 실질적인
방어선**이다. privileged 커널 권한은 데몬이 쓰는 것이고, 사용자는 제한된 명령만 보낸다.

| 구분 | 허용 |
|---|---|
| 조회 | `ps` `images` `inspect` `logs` `stats` `port` `top` `diff`, `network/volume/container ls·inspect` |
| 복구 | `start` `restart` `stop` `unpause` `update`, `network connect/disconnect`, `volume create` |
| 확인 필요 | `rm` `kill` (confirmation 계약) |
| 차단 | `run` `exec` `build` `commit` `push/pull` `cp` `system` `swarm` `compose` `login` `context` 등 |

**전역 옵션 차단**: `-H` / `--host` / `--context` / `--config` / `--tlsverify` 는 어느 위치에
있어도 거절한다. 데몬을 다른 곳으로 돌리면 격리가 무의미해진다.

**`update` 는 자원 조정만**: `--memory` `--cpus` `--pids-limit` 등만 허용하고 특권 상승
옵션은 막는다.

**대상 제한**: 모든 target 이름은 훈련이 허용한 리소스 집합 안에 있어야 한다.
시나리오가 집합을 넘기지 않으면 기본값(`SANDBOX_TRAINING_CONTAINER` / `_NETWORK` / `_VOLUME`)만
허용한다. 플래그의 **값**(`--memory 256m` 의 `256m`)을 대상으로 오인하지 않도록
`VALUE_FLAGS` 로 걸러낸다.

### Docker 샌드박스와 privileged 결정 (BE-11)

**rootless DinD는 이 클러스터에서 기동하지 않는다.** 세 가지 방식을 실제로 시도했다.

| 시도 | 결과 |
|---|---|
| 기본 (rootlesskit builtin) | `ip tuntap add name tap0` 실패 |
| `DOCKERD_ROOTLESS_ROOTLESSKIT_NET=slirp4netns` | 이미지에 바이너리 없음 |
| `NET_ADMIN` + `SYS_ADMIN` capability 추가 | sysfs mount 거부, TAP 실패 |

같은 클러스터에서 **privileged DinD는 정상 기동**한다(docker 27.5.1). 그래서 계획서 방침대로
privileged를 쓰되 격리를 다음으로 좁혔다.

- 사용자 네임스페이스 안에서만 생성되고 기본 deny NetworkPolicy가 적용된다
- **호스트 `docker.sock`을 마운트하지 않는다.** 데몬을 컨테이너 안에서 새로 띄운다
- **ServiceAccount 토큰을 마운트하지 않아** Kubernetes API에 접근할 수 없다
  (Docker 환경은 K8s API를 쓰지 않으므로 Role/RoleBinding도 붙이지 않는다)
- CPU/메모리/**ephemeral-storage** 상한 (디스크를 채우는 훈련이 노드를 위협하면 안 된다)
- 데몬은 유닉스 소켓만 쓴다 (`DOCKER_TLS_CERTDIR=""`)

실측 격리: 샌드박스에서 `docker ps`가 **호스트의 컨테이너 9개를 전혀 보지 못하고**
자기 안의 것만 보여준다. `/var/run/secrets/kubernetes.io/`도 존재하지 않는다.

훈련 대상 컨테이너는 `ensure_training_workload()`가 멱등 생성한다. Kubernetes 환경의
nginx Deployment에 해당하는 역할이며, 이미 있으면 다시 만들지 않고 멈춰 있으면 다시 띄운다.

> **아직 `IMPLEMENTED_ENVIRONMENTS`에 docker를 넣지 않았다.** 샌드박스는 뜨지만
> injector/validator가 없어서(BE-13/BE-14) 미션을 시작할 수 없다. 활성화는 BE-14에서 한다.

### 미션 시드 (seed_data.py, BE-09)

`(environment, level)`을 stable key로 **upsert**한다. 이전에는 미션이 하나라도 있으면
전체를 건너뛰어서, Kubernetes 미션이 있는 DB에 Docker/Linux 미션을 추가할 방법이 없었다.

- 재실행해도 중복이 생기지 않는다
- 기존 행은 내용만 갱신한다. **id가 바뀌면 진행 중인 attempt의 FK가 끊긴다**
- 새 환경 시드만 선택적으로 추가된다

### 환경별 구현체 선택 (service_factory.py, BE-08)

레지스트리 키가 `(environment, configured_backend)`다. 같은 백엔드 이름이라도 환경마다
구현체가 다르고, **등록되지 않은 조합은 kubernetes로 조용히 대체되지 않고 실패한다.**

```python
_INJECTOR_FACTORIES = {
    (KUBERNETES, "mock"): lambda: MockChaosInjector(environment=KUBERNETES),
    (KUBERNETES, "chaos_mesh"): ChaosMeshInjector,
}
```

docker/linux 구현체가 붙을 때 이 표에 줄만 추가하면 된다.

`MissionService` / `ScenarioService`는 **환경별 인스턴스를 두지 않는다.** 서비스는 상태를
갖지 않고 `attempt.environment`로 그때그때 구현체를 조회한다(`injector_for(environment)`).

### 장애 복구와 재시작 (BE-08)

`revert(chaos_id, namespace)`가 namespace를 인자로 받는 이유는 **서버 재시작 후에도
되돌릴 수 있어야 하기 때문**이다. 프로세스 메모리의 주입 이력은 보조 정보로만 쓴다.

- `chaos_id` 형식은 `{chaos-type}-{uuid8}` (예: `compound-probe-cascade-a1b2c3d4`)
- `BaseChaosInjector.chaos_type_from_id()`로 타입을 복원하므로 인메모리 dict가 비어도 동작
- 정리는 `attempt.chaos_id`(DB)를 근거로 하고, 되돌린 뒤 `None`으로 비워 재정리에 안전하다
- 주입 성공 후 DB commit이 실패하면 즉시 revert해 고아 장애를 남기지 않는다

### 실클러스터 회귀 (BE-10, 2026-08-29)

Docker Desktop Kubernetes(v1.34.3) + Chaos Mesh로 고정 미션 4개를 end-to-end 검증했다.
각 미션마다 **주입 → 장애 감지 → toolbox Pod에서 복구 명령 → 검증 통과 → revert** 전 사이클.

| 미션 | chaos_type | 결과 |
|---|---|---|
| 1. 사라진 웹페이지 | `pod_failure` | 통과 |
| 2. 터져버린 쇼핑몰 | `memory_stress` | 통과 |
| 3. 끊어진 연결고리 | `service_misconfig` | 통과 |
| 4. 좀비 서버의 습격 | `network_latency` | 통과 (아래 결함 수정 후) |

**격리 실증**: validator를 우회해 `kubectl get pods -n kube-system`을 직접 실행해도
toolbox ServiceAccount의 RBAC이 `Forbidden`으로 거절한다. validator와 RBAC 이중 방어가
실제로 동작한다.

이 회귀에서 발견해 고친 결함 3가지는 모두 **실클러스터에서만 드러나는 것**이었다.
단위 테스트로는 잡히지 않으므로 환경이 바뀌면 다시 확인해야 한다.

1. toolbox 이미지 `bitnami/kubectl:1.29`가 Docker Hub에 존재하지 않아 샌드박스가
   `ImagePullBackOff`로 뜨지 못했다 → `SANDBOX_TOOLBOX_IMAGE` 설정으로 분리하고
   `alpine/k8s:1.34.1`(shell 포함, 클러스터와 마이너 일치)로 교체
2. Chaos Mesh 네임스페이스가 `chaos-testing`으로 하드코딩돼 있었으나 실제 설치 위치는
   `chaos-mesh`였다 → `CHAOS_MESH_NAMESPACE` 설정으로 분리
3. 미션 4가 장애를 만들지 못했다 → 위 표 참고

### 검증 백엔드 (validation_service.py)
| VALIDATION_BACKEND | 설명 |
|---|---|
| `mock` | 인메모리 수동 해결 (개발용) |
| `k8s` | Kubernetes API로 실제 리소스 상태 검증 |
| `prometheus` | Prometheus PromQL로 메트릭 기반 검증 |

### AI 시나리오 잠금 해제 조건
- 기본 4개 미션 전체 완료 필요
- 미완료 상태에서 start-random 호출 시 400 에러 반환

## 데이터 모델

> **환경(environment) 필드 (캡스톤2):** `Mission`, `GeneratedScenario`, `TerminalSession`은
> `environment` 컬럼(`kubernetes` | `docker` | `linux`, default `kubernetes`)을 가진다.
> 상수·검증은 `core/environments.py`. 현재 실제 장애 주입/검증은 kubernetes만 구현됐고
> docker/linux는 `assert_implemented`로 막혀 있다(선택 시 400).
> `application`은 목업 한정이라 `SUPPORTED_ENVIRONMENTS`에 넣지 않는다.
>
> **아직 관통되지 않은 구간:**
> - ~~`MissionAttempt`에 `environment`·`chaos_id`·`sandbox_id` 컬럼이 없다.~~ (BE-02 완료)
> - ~~mission list API가 DB의 `mission.environment`를 응답에 싣지 않는다.~~ (BE-03 완료)
> - ~~`GET /api/environments`(환경 가용성) 미구현.~~ (BE-03 완료)
> - `POST /api/terminal/sessions`가 body 없이 kubernetes setup만 수행한다. → BE-07
> - ~~WebSocket이 session의 environment를 로드하지 않는다.~~ (BE-06 완료)
> - factory가 `environment` 인자를 받지만 registry key는 backend 이름만 쓴다. → BE-08
> - ~~mission 목록·잠금이 environment로 필터되지 않는다.~~ (BE-09 완료)
>
> **API 계약 검증:** `environment`는 `EnvironmentId`(Literal) 타입이라 허용 외 값은
> Pydantic이 422로 거절한다. `EnvironmentId`와 `SUPPORTED_ENVIRONMENTS`가 갈라지지
> 않도록 `core/environments.py` import 시점에 일치를 단언하고 테스트로도 고정한다.
>
> **마이그레이션:** Alembic이 스키마의 단일 출처다(BE-02 완료).
> 자세한 내용은 아래 "데이터베이스 마이그레이션" 참고.

### 현재 모델
- `User` - 사용자 (username, email, hashed_password, total_score)
- `Mission` - 고정 미션 정의 (level, chaos_type, `environment`, base_score 등)
- `MissionAttempt` - 미션 시도 기록
  - `attempt_type`: `static_mission` | `ai_scenario`
  - `mission_id`: 정적 미션 attempt 시 필수, AI 시나리오 attempt 시 NULL
  - `scenario_id`: AI 시나리오 attempt 시 필수, 정적 미션 attempt 시 NULL
  - `last_validation_result`: 마지막 검증 결과 JSON
  - `environment`: 이 시도가 수행된 훈련 환경. mission/scenario를 join하지 않고도
    정리·복구·통계가 가능하도록 attempt에 직접 저장한다
  - `chaos_id`, `sandbox_id`: 주입된 장애와 샌드박스 식별자. 서버 재시작 후에도
    DB만으로 정리할 수 있어야 한다 (BE-08에서 실제로 이 값을 쓰도록 전환)
  - DB 제약: `attempt_type` 허용값 CHECK, `attempt_type`↔FK 조합 일치 CHECK,
    사용자당 `in_progress` 1개 partial unique index
- `TerminalSession` - 터미널 세션 (`environment` 포함)
- `CommandLog` - kubectl 명령 실행 기록
- `GeneratedScenario` - AI 생성 시나리오
  - `difficulty`, `environment`, `title`, `student_brief`, `fault_type`
  - `scenario_json`, `chaos_plan_json`, `validation_json`
  - `status`: generated | running | completed | failed
  - `base_score`, `time_limit`, `hint_penalty`
- `ValidationRule` - AI 생성 검증 조건
  - `rule_type`: `k8s` | `promql` | `mock`
  - `query`: k8s 타입은 `deployment:nginx:running` 형식, promql은 PromQL 문자열
  - `guard_status`: `accepted` | `rejected`

- `TutorMessage` - 튜터 대화 영구 저장. 모델과 저장 로직 모두 구현 완료
  (`ai/tutor_service.py`에서 user/assistant 메시지를 DB에 저장하고 최근 이력을 조회한다.
  저장 실패는 무시하고 응답을 계속한다.)

## AI 백엔드 구성

### ScenarioAgent (scenario_agent.py)
- **Mock 모드**: 난이도별 fixture JSON 반환 (API 키 불필요)
  - beginner: image_pull_error (ImagePullBackOff)
  - intermediate: service_selector_mismatch (서비스 연결 실패)
  - advanced: oom_killed (OOMKilled 반복)
  - expert: probe_failure (간헐적 503)
- **OpenAI/Gemini 모드**: `ai-data/prompts/scenario_gen.md` 시스템 프롬프트 기반 생성
  - 생성 실패 시 Mock fixture로 자동 fallback
  - validation rules는 반드시 `k8s` 타입으로 생성하도록 프롬프트 지시

### TutorService (tutor_service.py)
- `AI_BACKEND=mock`: 고정 힌트 반환 (개발용)
- `AI_BACKEND=openai|gemini`: AITutorEngine (RAG + LLM) 사용
- `VALIDATION_BACKEND=k8s` 시 K8s API로 실제 Pod 상태 + 이벤트 조회
- 힌트 레벨 0~3: 방향제시 → 리소스지목 → kubectl 명령어 → 전체 해결

### Qdrant 자동 초기화 (qdrant_init.py)
서버 시작(lifespan) 시 `auto_ingest_if_empty()` 호출:
- `AI_BACKEND=mock` → skip (임베딩 API 없음)
- Qdrant 컬렉션에 문서 있음 → skip
- 비어있을 때만 `ai-data/knowledge-base` 전체 ingestion 실행
- 임베딩 생성은 `ThreadPoolExecutor`에서 실행 (blocking I/O 비동기 격리)

## 게이미피케이션 (analytics_service.py)
- 티어: Bronze(0) → Silver(201) → Gold(501) → Platinum(1001) → DevOps Master(2001+)
- 업적: First Recovery, Environmentalist(힌트 없이 클리어), Speed Runner(5분 이내), Persistent Resolver(10회 시도)
- 스킬 점수: troubleshooting / resource / network / ops 카테고리별

## 환경변수
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival
AUTO_CREATE_SCHEMA=true      # 로컬 개발/테스트 편의용. 배포 환경에서는 false

# 샌드박스 / Chaos Mesh
SANDBOX_TOOLBOX_IMAGE=alpine/k8s:1.34.1   # shell 포함 필수(distroless 불가), 클러스터와 마이너 일치
SANDBOX_READINESS_TIMEOUT_SECONDS=90
CHAOS_MESH_NAMESPACE=chaos-mesh           # Chaos Mesh 설치 위치

# Docker 환경 샌드박스 (DinD)
SANDBOX_DIND_IMAGE=docker:27-dind
SANDBOX_DIND_CPU_LIMIT=1
SANDBOX_DIND_MEMORY_LIMIT=1Gi
SANDBOX_DIND_STORAGE_LIMIT=2Gi
SANDBOX_TRAINING_IMAGE=nginx:alpine       # DinD 안 훈련 대상 컨테이너
SANDBOX_TRAINING_CONTAINER=training-app
SANDBOX_TRAINING_NETWORK=training-net
SANDBOX_TRAINING_VOLUME=training-data
SANDBOX_TRAINING_CPUS=1                   # 훈련 컨테이너 정상 상태의 CPU 상한

# Linux 환경 샌드박스
SANDBOX_LINUX_IMAGE=nicolaka/netshoot:v0.13   # 관측 도구 포함
SANDBOX_LINUX_CPU_LIMIT=500m
SANDBOX_LINUX_MEMORY_LIMIT=512Mi
SANDBOX_LINUX_STORAGE_LIMIT=1Gi
SANDBOX_LINUX_PID_LIMIT=256

# 터미널 실행 (BE-05)
TERMINAL_BACKEND=sandbox          # sandbox | mock
COMMAND_TIMEOUT_SECONDS=5         # 기본 명령 timeout
COMMAND_TIMEOUT_MAX_SECONDS=30    # 환경별 override 상한
COMMAND_OUTPUT_LIMIT_BYTES=65536  # 사용자에게 보내는 출력 상한 (64KiB)
COMMAND_LOG_LIMIT_BYTES=5120      # CommandLog 저장 상한 (5KiB)

AI_BACKEND=mock              # mock | openai | gemini

# OpenAI
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
SCENARIO_MODEL=gpt-4o-mini
TUTOR_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

# Gemini (OpenAI 호환 API)
GEMINI_API_KEY=
GEMINI_MODEL=models/gemini-2.0-flash-lite
GEMINI_EMBEDDING_MODEL=models/text-embedding-004

CHAOS_BACKEND=mock           # mock | chaos_mesh
VALIDATION_BACKEND=mock      # mock | k8s | prometheus
MOCK_VALIDATION_AUTO_PASS=false
PROMETHEUS_URL=http://localhost:9090

# RAG (Qdrant 벡터 DB)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=              # Qdrant Cloud 사용 시 (로컬은 불필요)
KNOWLEDGE_BASE_DIR=          # knowledge-base 절대 경로 (기본값: ai-data/knowledge-base)
```

## 컨벤션
- PEP8 준수, 타입 힌트 필수
- Pydantic 모델로 요청/응답 정의
- 환경 변수는 .env + pydantic-settings
- 비동기 우선 (async/await)
- K8s 동기 API는 `run_in_executor` 패턴으로 비동기 래핑

### 보안 규칙 (캡스톤2 이후 필수)
- 사용자 명령을 host shell에서 실행하지 않는다. `shell=True`,
  `create_subprocess_shell` 경로를 새로 추가하지 않는다.
- 입력 검증만으로 shell 실행을 안전하다고 간주하지 않는다. 핵심 방어는
  **argv allowlist + sandbox exec**이고 blacklist는 보조 수단이다.
- 실행 대상 namespace/pod/container는 **서버가 DB session과 config에서 결정**한다.
  브라우저가 보낸 값을 execution target으로 쓰지 않는다.
- session 조회 조건에는 항상 `session_id + user_id + is_active`가 들어간다.
- 미구현 environment를 kubernetes로 fallback하지 않는다.
- 장애 주입·복구·채점에 필요한 식별자는 재시작 후 복구할 수 있도록 DB에 저장한다.
- 사용자에게 내부 정답·secret·stack trace를 노출하지 않고, metrics label에
  user ID·namespace·명령 원문·시나리오 제목을 넣지 않는다.
- 작업 종료 전 `python -m pytest -q`를 실행하고, 실패가 있으면 이번 변경으로 인한
  회귀와 기존 실패를 구분해 보고한다.

## 실행
```bash
cd backend
python -m venv venv && source venv/bin/activate   # 최초 1회
pip install -r requirements.txt                   # pytest, pytest-asyncio 포함
uvicorn app.main:app --reload --port 8000
```

### 테스트
```bash
cd backend && source venv/bin/activate
python -m pytest -q          # 전체
python -m pytest -q -rs      # skip된 테스트까지 확인
```
설정은 `backend/pytest.ini` (`testpaths = tests`, `asyncio_mode = strict`).

## 데이터베이스 마이그레이션

스키마의 단일 출처는 **Alembic**이다(`backend/alembic/`). 모델을 바꾸면 반드시
리비전을 만들고, `Base.metadata.create_all`에 의존하지 않는다.

```bash
cd backend && source venv/bin/activate
alembic upgrade head                          # 최신 스키마로 적용
alembic revision --autogenerate -m "설명"      # 모델 변경 후 리비전 생성
alembic downgrade -1                          # 한 단계 되돌리기
alembic current                               # 현재 리비전 확인
```

접속 URL은 `alembic.ini`가 아니라 `alembic/env.py`가 `app.core.config.settings`에서
주입한다. 따라서 `DATABASE_URL` 환경변수만 맞추면 된다.

### 리비전 이력
| 리비전 | 내용 |
|---|---|
| `0001` | baseline 스키마. 빈 DB면 전체 생성, Alembic 이전에 만들어진 기존 DB면 예전 `ensure_schema_compatibility()`가 하던 idempotent 보정을 수행해 같은 상태로 수렴시킨다 (`alembic stamp` 불필요) |
| `0002` | `mission_attempts`에 `environment`·`chaos_id`·`sandbox_id` 추가 + backfill, environment/attempt_type/FK조합 CHECK, 사용자당 `in_progress` partial unique index |
| `0003` | `missions`에 `(environment, level)` unique 제약. 시드의 stable key를 DB로 못 박는다. 중복 행이 있으면 정리 안내와 함께 실패한다 |

> `0001`은 테이블이 **전부 있거나 전부 없는** DB를 가정한다. 일부 테이블만 있는
> DB는 대상이 아니므로 재생성한다.

> `0002`의 downgrade는 스키마만 되돌린다. upgrade 중 수행한 데이터 보정(중복
> `in_progress`를 `abandoned`로 정리)은 어떤 행이 원래 진행 중이었는지 기록하지
> 않으므로 되돌리지 않는다.

### 기존 로컬 DB를 쓰던 경우 (팀원 공통 안내)

Alembic 도입(BE-02) 전에 만들어진 로컬 `k8s_survival` DB는 `mission_attempts.environment`
컬럼과 `alembic_version` 테이블이 없다. **`create_all`은 기존 테이블을 ALTER하지 않으므로
앱을 띄우는 것만으로는 고쳐지지 않는다.**

```bash
cd backend && source venv/bin/activate
alembic upgrade head
```

**이 한 줄이면 된다. `alembic stamp`는 필요 없고, 볼륨을 버릴 필요도 없다.**
`0001`이 옛 DB를 감지해 baseline으로 보정한 뒤 `0002`를 적용하며, 기존 데이터는 보존된다.

스키마가 낡은 상태로 앱을 띄우면 attempt 조회가 조용히 깨지는 대신
**startup에서 위 명령을 안내하며 기동을 중단**한다.

### 새 로컬 DB 준비
```bash
docker compose up -d postgres
cd backend && source venv/bin/activate && alembic upgrade head
```

`AUTO_CREATE_SCHEMA=true`(기본값)이면 앱 startup에서도 `create_all`로 빈 스키마를
만든다. 이때 **스키마가 실제로 head 상태일 때만 `alembic_version`을 head로 표시**한다.
- 빈 DB → `create_all`이 최신 스키마 생성 → stamp → 이후 `upgrade head`는 no-op
- 옛 DB → `create_all`은 기존 테이블을 건드리지 않으므로 stamp하지 않는다.
  여기서 stamp하면 거짓이 되어 보정이 영영 적용되지 않는다.

이 장치가 없으면 이력 없이 최신 스키마만 있는 DB에서 `upgrade head`가
`DuplicateColumnError`로 실패한다. `0002`도 같은 이유로 idempotent하게 작성돼 있다.

배포 환경에서는 `AUTO_CREATE_SCHEMA=false`로 두고 배포 단계에서
`alembic upgrade head`를 실행한다.

## 의존 서비스
- PostgreSQL: localhost:5432 (k8s_survival DB)
- Qdrant: localhost:6333 (벡터 DB)
- Prometheus: localhost:9090 (모니터링 프로필 실행 시)
- Grafana: localhost:3001 (모니터링 프로필 실행 시)

## 주요 버그 수정 이력
- `tutor_service.py`: K8s 이벤트 datetime 정렬 TypeError 수정 (isoformat() 사용)
- `missions.py`: AI 시나리오 attempt 진행 중 정적 미션 API 호출 시 NoneType 크래시 수정
- `validation_rule_service.py`: mock 타입 룰이 항상 False 반환하던 문제 → K8s fallback 추가
- `scenario_agent.py`: 잘못된 PromQL 메트릭명(`kube_endpoint_address`) → k8s 타입 룰로 교체
- `scenario_gen.md`: Gemini가 mock 타입 룰 생성하던 문제 → k8s 타입으로 프롬프트 수정
