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
│   ├── command_validator.py      # argv allowlist 검증 (셸 메타문자 거절, namespace 강제)
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
│   ├── runtime_context.py        # K8s/Prometheus/CommandLog 수집 (구현 완료, 튜터 연결됨)
│   ├── scoring_service.py        # 점수 계산 (시간/힌트 감점)
│   ├── analytics_service.py      # 대시보드/리더보드/업적/티어 계산
│   ├── k8s_setup.py              # 사용자 K8s 네임스페이스 자동 생성
│   ├── service_factory.py        # (environment, backend) 조합 레지스트리로 구현체 선택
│   ├── seed_data.py              # 미션 초기 데이터 (4개 레벨)
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

- `GET /api/missions/` - 미션 목록 (잠금 상태 포함)
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
- `GET /api/dashboard/stats` - 내 통계 (총 점수, 티어, 스킬 점수) 🔒
- `GET /api/dashboard/learning-curve` - 미션 시도 히스토리 🔒
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
> - mission 목록·잠금이 environment로 필터되지 않는다. → BE-09
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
