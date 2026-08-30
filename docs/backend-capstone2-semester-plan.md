# 캡스톤디자인 II 백엔드 2학기 구현 계획

> 프로젝트: AfterFail - 멀티 레이어 클라우드 인프라 기반 지능형 장애 대응 훈련 플랫폼
> 작성 기준: 2026-08-26, `dev` 브랜치 `36b1415`
> 원문 기준: `서버가왜죽었조_캡스톤디자인II_계획서.pdf`
> 대상 기간: 2026학년도 2학기, 16주, 2주 단위 8개 스프린트
> 담당 역할: Backend Engineer, Cloud Architect
> 주 작업 범위: `backend/app/api`, `backend/app/core`, `backend/app/services`, DB migration, sandbox manifest, backend tests

## 0. 이 문서의 사용법

이 문서는 백엔드 담당자 또는 AI 코딩 에이전트가 작업 ID 단위로 바로 구현할 수 있는 실행 명세다.

1. 한 번에 하나의 `BE-xx` 작업만 구현한다.
2. 각 작업의 선행 조건과 API 계약을 먼저 확인한다.
3. AI 생성·RAG·프롬프트 품질은 AI 담당 문서의 범위다. 백엔드는 AI가 사용할 안전한 입력·출력 계약과 실행 환경을 제공한다.
4. 프론트 UI를 임의로 수정하지 않는다. 계약 변경이 필요하면 `docs/frontend-capstone2-semester-plan.md`와 함께 갱신한다.
5. 기존 `BaseChaosInjector`, `BaseValidationService`, factory registry, FastAPI dependency를 재사용한다. 같은 목적의 새 프레임워크를 만들지 않는다.
6. 사용자 명령은 host shell에서 실행하지 않는다. 입력 검증만으로 `shell=True` 실행을 안전하다고 간주하지 않는다.
7. 장애 주입·복구·채점은 재시작 후에도 복구할 수 있도록 필요한 식별자를 DB에 저장한다.
8. 작업 종료 전 `python -m pytest -q`를 실행하고 실패가 있으면 작업으로 인한 회귀와 기존 실패를 구분해 보고한다.

AI 전달 프롬프트:

```text
docs/backend-capstone2-semester-plan.md를 읽고 [작업 ID]만 구현해라.
현재 호출 흐름과 모든 caller를 먼저 확인한 뒤 가장 작은 변경으로 인수 조건을 만족시켜라.
host shell 실행, 사용자 간 namespace 접근, 미구현 환경 fallback은 절대 허용하지 마라.
변경 파일, DB/API 호환성, 실행한 테스트, 남은 frontend/AI 의존성을 마지막에 보고해라.
```

---

## 1. 백엔드 최종 책임 범위

PDF 계획서와 현재 팀 역할을 기준으로 백엔드는 다음을 책임진다.

- Kubernetes, Docker, Linux 환경을 사용자별로 격리해 생성·재사용·정리한다.
- `BaseChaosInjector` 기반 환경별 장애 주입기와 복구 로직을 구현한다.
- 환경별 안전한 명령 정책과 WebSocket 터미널 실행 경로를 제공한다.
- Kubernetes API, sandbox exec, Prometheus를 이용해 복구 여부를 결정한다.
- 미션·AI 시나리오·세션·시도 기록에 environment를 끝까지 전달한다.
- 시간, 힌트, MTTR을 반영한 점수와 환경별 통계를 제공한다.
- JWT, 세션 소유권, RBAC, ResourceQuota, NetworkPolicy, timeout을 적용한다.
- 장애 주입 실패, 서버 재시작, 사용자 이탈 후에도 정리 가능한 상태를 유지한다.
- 프론트엔드와 AI 계층에 안정된 API/서비스 계약과 관측 메트릭을 제공한다.

### 범위 기준

- 필수 환경: `kubernetes | docker | linux`.
- `application/db`는 현재 저장소 공식 범위에서 제외한다.
- 8주차 필수 환경 통합이 완료되고 Application sandbox/injector/validator 요구가 확정될 때만 별도 이슈로 추가한다.
- AWS EKS 배포는 환경 기능과 병렬 가능한 별도 트랙이지만 최종 통합은 Sprint 7에서 수행한다.

---

## 2. 현재 백엔드 기준선

### 2.1 이미 구현된 기반

- FastAPI, Pydantic v2, SQLAlchemy async, PostgreSQL.
- JWT 인증, 회원가입·로그인·프로필·로그아웃.
- Kubernetes 사용자 namespace와 nginx Deployment/Service 생성.
- xterm WebSocket 명령 수신, command log 저장.
- 고정 미션 4개와 AI 시나리오 attempt 흐름.
- `BaseChaosInjector`, `BaseValidationService` 추상 인터페이스.
- chaos type별 `_CHAOS_HANDLERS`, `_CHECKS`, `_RULE_RUNNERS` registry.
- Kubernetes/Chaos Mesh 장애 주입과 K8s/Prometheus 검증.
- 점수, 티어, 리더보드, 업적, 학습 곡선.
- `Mission`, `GeneratedScenario`, `TerminalSession`의 environment 컬럼.
- `SUPPORTED_ENVIRONMENTS`에 Kubernetes/Docker/Linux 등록.

### 2.2 현재 테스트 기준선

2026-08-26 현재 `backend/`에서 `python -m pytest -q` 실행 결과:

- 28 passed.
- 4 failed.
- `kubectl create secret`이 허용되어 command validator 기대와 불일치.
- 현재 실행 환경에 pytest-asyncio plugin이 없어 async validation test 3개가 실행되지 않음.
- Pydantic class Config deprecation warning이 발생함.

새 기능 착수 전에 이 기준선을 녹색으로 만든다. 실패 테스트를 삭제하거나 xfail로 숨기지 않는다.

### 2.3 치명적 결손

| 우선순위 | 현재 상태 | 위험 |
|---|---|---|
| P0 | `CommandExecutor`가 host에서 `shell=True` 실행 | validator 우회 시 host RCE |
| P0 | WebSocket이 session ID와 JWT user 소유권을 비교하지 않음 | 타 사용자 세션 오용·로그 오염 |
| P0 | environment가 session 생성·명령 실행까지 연결되지 않음 | Docker 탭에서 Kubernetes 명령 실행 |
| P0 | active chaos ID가 process memory dict에만 존재 | 서버 재시작 시 장애 정리 불가 |
| P1 | factory가 environment 인자를 받지만 실제 registry는 backend 이름만 사용 | Docker/Linux injector 선택 불가 |
| P1 | MissionService singleton이 Kubernetes injector 한 개를 고정 | 환경별 미션 실행 불가 |
| P1 | 미션 목록·잠금이 environment로 필터되지 않음 | 환경 간 레벨·잠금 섞임 |
| P1 | `seed_missions()`가 미션이 하나라도 있으면 전체 seed를 건너뜀 | 신규 환경 seed 추가 불가 |
| P1 | attempt에 environment·chaos ID가 직접 저장되지 않음 | 복원·정리·통계가 join과 memory에 의존 |
| P1 | `scalar_one_or_none()` 전제만 있고 활성 attempt 유일성 DB 제약 없음 | 동시 요청 시 MultipleResultsFound |
| P2 | CORS `*`와 credentials 조합 | 운영 origin 통제 불가 |
| P2 | `Base.metadata.create_all` + 수동 ALTER | 배포 migration 이력·rollback 없음 |
| P2 | 로그에 명령과 출력이 print됨 | 운영 로그 노출·소음 |
| P2 | 환경별 분석·MTTR API 없음 | 통합 대시보드 구현 불가 |

### 2.4 현재 environment 관통 상태

| 계층 | 상태 |
|---|---|
| DB Mission/Scenario/Session | 컬럼 존재 |
| MissionAttempt | environment 없음 |
| Pydantic Mission/Scenario/Session | 일부 기본값 존재 |
| mission list API | DB environment를 response에 넘기지 않음 |
| scenario start API | environment를 받지만 Kubernetes만 implemented |
| terminal session API | body 없이 Kubernetes setup만 실행 |
| WebSocket | environment를 로드하지 않음 |
| command validator/executor | kubectl + host shell 전용 |
| injector/validator factory | environment 실제 분기 없음 |
| analytics | 전체 합계, environment 없음 |

---

## 3. 2학기 백엔드 완료 정의

### 3.1 사용자 흐름

1. 사용자는 가용 환경 목록을 조회한다.
2. 선택 환경으로 터미널 세션을 생성한다.
3. 서버는 사용자 namespace 안에 해당 환경 sandbox를 준비한다.
4. WebSocket 연결 시 JWT user, session owner, session environment, sandbox readiness를 검증한다.
5. 명령은 환경별 allowlist를 통과한 argv로 sandbox Pod 안에서 실행된다.
6. 미션 시작 시 같은 environment의 injector가 같은 sandbox에 장애를 주입한다.
7. 검증기는 같은 environment와 sandbox만 조회한다.
8. 완료·포기·시간 초과 시 chaos와 임시 리소스를 idempotent하게 정리한다.
9. 서버 재시작 뒤에도 DB의 attempt/chaos/sandbox 상태로 복구·정리할 수 있다.
10. 환경별 완료 수, 점수, 평균 MTTR, 힌트, competency를 API로 제공한다.

### 3.2 보안 완료 조건

- host `subprocess.run(..., shell=True)`와 `create_subprocess_shell` 사용 0건.
- session 조회 조건에 `session_id + user_id + is_active`가 항상 포함된다.
- WebSocket connection에서 client가 보내는 namespace/environment를 신뢰하지 않는다.
- 모든 실행 대상 namespace, pod, container는 DB session과 서버 config에서 결정한다.
- Kubernetes toolbox ServiceAccount는 사용자 namespace 범위를 벗어나는 권한이 없다.
- Docker/Linux sandbox에는 CPU, memory, ephemeral-storage limit이 있다.
- 가능하면 rootless container를 사용하고 privileged가 필요하면 환경별로 명시·격리한다.
- pipe, redirect, command substitution, shell chaining은 argv parser 이전에 거부한다.
- 명령 timeout, output byte limit, concurrent command limit이 있다.
- secrets, token, 전체 민감 출력은 log/metrics에 남기지 않는다.

### 3.3 데이터 완료 조건

- attempt가 environment, chaos_id, sandbox identifier를 가진다.
- 사용자당 `in_progress` attempt는 DB partial unique index로 최대 1개다.
- mission level 잠금은 environment별로 계산한다.
- seed는 `(environment, level)` 또는 안정된 key로 upsert한다.
- schema 변경은 Alembic migration으로 재현된다.
- API response에서 environment는 default로 숨겨진 값이 아니라 실제 DB 값이다.

### 3.4 하지 않을 것

- environment마다 MissionService 전체를 복제하지 않는다.
- 브라우저가 보낸 pod/container 이름을 그대로 exec target으로 사용하지 않는다.
- AI 판정만으로 점수를 확정하지 않는다.
- 미구현 environment를 Kubernetes로 fallback하지 않는다.
- 실제 사용자가 고칠 수 없는 장애를 injector에 추가하지 않는다.
- host kernel OOM, host disk fill 같은 노드 전체 장애를 교육용 local/EKS 환경에 직접 주입하지 않는다.

---

## 4. 확정할 API 계약

프론트 계획서와 동일한 계약을 백엔드 기준으로 구체화한다.

### API-BE-01 환경 가용성

```http
GET /api/environments
Authorization: Bearer {token}
```

```json
{
  "items": [
    {"id":"kubernetes","status":"available","capabilities":["static_mission","ai_scenario","terminal","tutor","observability"]},
    {"id":"docker","status":"preparing","capabilities":[]},
    {"id":"linux","status":"preparing","capabilities":[]}
  ]
}
```

- source of truth는 `core/environments.py`와 실제 factory/sandbox readiness다.
- label·설명은 프론트 책임이다.
- `available`은 session 생성, injector, validator가 모두 등록된 경우에만 반환한다.

### API-BE-02 환경별 터미널 세션

```http
POST /api/terminal/sessions
Content-Type: application/json

{"environment":"docker"}
```

```json
{
  "id":"uuid",
  "namespace":"user-uuid",
  "environment":"docker",
  "created_at":"...",
  "is_active":true
}
```

- 동일 사용자의 동일 environment active session이 있으면 재사용하거나 기존 세션을 비활성화한 뒤 새로 만든다. 정책은 한 가지로 고정한다.
- 권장: 준비된 session 재사용.
- `DELETE /api/terminal/sessions/{id}`는 소유권 확인 후 session 비활성화와 sandbox lease 정리를 수행한다.

### API-BE-03 WebSocket

기존 URL은 유지한다.

```text
WS /ws/terminal/{session_id}?token={JWT}
```

연결 시 서버가 DB에서 결정할 값:

```text
user_id <- JWT
session <- id + user_id + is_active
environment <- session.environment
namespace <- session.namespace
sandbox pod/container <- server-side SandboxLocator
```

close code:

| code | 의미 |
|---|---|
| 4001 | token invalid/expired |
| 4003 | session owner mismatch 또는 inactive |
| 4004 | session/sandbox not found |
| 4010 | environment unavailable |

### API-BE-04 환경별 미션

```http
GET /api/missions/?environment=linux
```

- environment query는 필수로 전환하되 한 번의 호환 기간 동안 default kubernetes를 허용할 수 있다.
- response에 실제 `mission.environment`를 넣는다.
- start response와 status response의 attempt에 environment를 넣는다.
- environment별 level 잠금을 계산한다.

### API-BE-05 AI 시나리오 연동

- `POST /api/scenarios/start-random` environment를 injector/validator/runtime context까지 전달한다.
- AI가 생성한 scenario environment와 요청 environment가 다르면 422 또는 generation failure로 처리한다.
- 동일 환경 fixture fallback만 허용한다. Docker 요청을 Kubernetes fixture로 fallback하지 않는다.

### API-BE-06 환경별 분석

```http
GET /api/dashboard/stats?environment=all|kubernetes|docker|linux
GET /api/dashboard/learning-curve?environment=...
```

`environment_stats` 항목:

```json
{
  "kubernetes": {
    "completed": 4,
    "average_score": 88,
    "average_mttr": 520,
    "hints_used": 2,
    "competency": 82
  }
}
```

- MTTR은 completed attempt만 사용한다.
- competency 계산식은 문서화하고 서버가 계산한다.
- 데이터 없음과 0점을 구분할 수 있도록 completed를 함께 제공한다.

### API-BE-07 AI 계층 내부 계약

백엔드가 AI 담당 코드에 전달할 공통 context:

```python
TrainingContext(
    environment="docker",
    user_id=...,
    attempt_id=...,
    namespace=...,
    sandbox_id=...,
    fault_type=...,
    recent_commands=[...],
    observations={...},
)
```

- AI는 브라우저 입력으로 execution target을 바꾸지 않는다.
- context collector는 환경별 adapter를 사용하되 출력 schema는 동일하게 유지한다.

---

## 5. 목표 실행/격리 구조

```text
user-{id} namespace
  ├─ ResourceQuota / LimitRange / NetworkPolicy
  ├─ afterfail-k8s-toolbox
  │    └─ namespace-scoped ServiceAccount + kubectl
  ├─ afterfail-k8s-target
  │    └─ 기존 nginx/webapp 훈련 리소스
  ├─ afterfail-docker-sandbox
  │    └─ rootless DinD 우선, 불가능하면 제한된 privileged DinD
  └─ afterfail-linux-sandbox
       └─ 제한된 shell + stress 도구 + resource/ephemeral limits
```

### 5.1 SandboxService

신규 `backend/app/services/sandbox_service.py` 하나로 다음을 담당한다.

```python
async def ensure(environment, user_id, namespace) -> SandboxRef
async def get_ref(environment, user_id, namespace) -> SandboxRef
async def is_ready(ref) -> bool
async def cleanup(ref) -> None
```

`SandboxRef` 최소 필드:

```python
environment
namespace
pod_name
container_name
service_account_name
```

- environment별 private ensure method를 사용한다.
- provisioner class를 환경마다 새로 만들 필요는 없다. 구현이 실제로 분리될 만큼 커질 때만 파일을 나눈다.
- 모든 ensure/cleanup은 idempotent해야 한다.

### 5.2 CommandPolicy와 Executor

기존 `CommandValidator`는 registry 기반 environment policy로 확장한다.

```python
validate(command: str, environment: str, namespace: str) -> ValidationResult
```

`ValidationResult.command`는 문자열 대신 `argv: list[str]`를 가진다.

```python
execute(argv: list[str], sandbox: SandboxRef, timeout: int) -> CommandResult
```

- `shlex.split`로 parsing하고 shell을 사용하지 않는다.
- Kubernetes client `stream(...connect_get_namespaced_pod_exec...)`로 sandbox 안에서 argv를 실행한다.
- 환경별 허용 command:
  - Kubernetes: kubectl의 제한된 subcommand.
  - Docker: docker ps/inspect/logs/stats/network/volume와 제한된 update/restart 명령.
  - Linux: ps/free/df/du/top/systemctl status/journalctl/dmesg/ss와 시나리오 복구에 필요한 제한 명령.
- security blacklist는 보조 방어다. 핵심은 argv allowlist와 sandbox exec다.

### 5.3 환경별 injector/validator

| 환경 | injector 파일 | validator 파일 | 최소 장애 |
|---|---|---|---|
| Kubernetes | 기존 `chaos_injector.py` | 기존 `validation_service.py` | 현재 4개 회귀 유지 |
| Docker | 신규 `docker_chaos_injector.py` | 신규 `docker_validation_service.py` | network disconnect, volume/mount, memory/CPU |
| Linux | 신규 `linux_chaos_injector.py` | 신규 `linux_validation_service.py` | cgroup OOM, disk I/O saturation, zombie/orphan |

새 구현체는 반드시 `environment`, `supports(chaos_type)`, `inject`, `revert` 계약을 따른다.

---

## 6. 스프린트별 구현 계획

## Sprint 0 - 1~2주차: 보안 기준선, 테스트, DB 계약

### BE-00 실행·격리 결정 기록

협의 내용:

- Kubernetes toolbox image와 namespace-scoped RBAC.
- Docker rootless DinD 가능 여부. 불가 시 privileged 사용 조건, node 격리, resource limit.
- Linux에서 안전하게 재현할 장애 범위. host OOM/disk fill은 제외.
- session 재사용·만료·sandbox cleanup 정책.
- Application/DB 제외 여부.

완료 조건:

- 위 결정이 `agent.md`와 이 문서에 일치한다.
- 프론트·AI 담당자가 environment 계약을 확인했다.

### BE-01 기존 테스트 녹색화

수정 파일:

- `backend/tests/test_command_validator.py`
- `backend/tests/test_validation_service.py`
- 신규 `backend/pytest.ini`
- 필요 시 개발 환경 의존성 설치 문서

구현 지시:

- `kubectl create secret` 허용 여부를 실제 미션 요구와 맞춘다. 허용한다면 resource/name/flag까지 제한하고 테스트를 수정한다. 무제한 create는 허용하지 않는다.
- pytest-asyncio가 requirements와 실제 venv에 설치되도록 setup 문서를 고친다.
- `asyncio_mode = auto` 또는 mark 정책을 명시한다.
- 기존 32개 테스트가 전부 실행되게 한다.

인수 조건:

- `python -m pytest -q` 0 failure.
- async test가 skip되지 않는다.

### BE-02 정식 migration과 데이터 제약

수정 파일:

- Alembic 초기 설정 및 migration 파일
- `backend/app/models.py`
- `backend/app/core/database.py`
- `backend/app/main.py`

구현 지시:

- 현재 수동 `ensure_schema_compatibility()` 변경을 첫 migration에 반영한다.
- MissionAttempt에 `environment`, `chaos_id`, `sandbox_id` nullable 컬럼을 추가하고 기존 데이터는 join을 통해 kubernetes로 backfill한다.
- `attempt_type`에 허용 값 check constraint를 추가한다.
- `environment`에 허용 값 check constraint를 추가한다.
- user별 status=`in_progress` partial unique index를 추가한다.
- 정적 mission/AI scenario FK 조합이 attempt_type과 일치하도록 application validation과 가능한 DB check를 추가한다.
- `create_all`은 테스트/초기 개발에만 남기고 운영 startup migration은 배포 단계에서 수행한다.

인수 조건:

- 빈 DB upgrade 성공.
- 기존 데이터 DB upgrade 성공.
- downgrade 또는 명시된 non-reversible 사유가 있다.
- 중복 active attempt insert가 DB에서 거부된다.

### BE-03 API environment 필드 누락 수정

수정 파일:

- `backend/app/schemas.py`
- `backend/app/api/missions.py`
- `backend/app/api/scenarios.py`
- API test 신규

구현 지시:

- MissionResponse 생성 시 DB environment를 전달한다.
- MissionAttemptResponse에 environment를 넣는다.
- Scenario request/response/status의 environment 일치를 검사한다.
- environment는 Pydantic Literal 또는 enum으로 검증한다.
- Pydantic class Config를 `ConfigDict(from_attributes=True)`로 갱신한다.

인수 조건:

- DB docker mission이 API에서 kubernetes로 바뀌지 않는다.
- 잘못된 environment는 422.
- 기존 kubernetes client 호환 테스트 통과.

---

## Sprint 1 - 3~4주차: 샌드박스와 안전한 터미널

### BE-04 사용자 sandbox 기반

수정 파일:

- 신규 `backend/app/services/sandbox_service.py`
- `backend/app/services/k8s_setup.py`
- sandbox unit test

구현 지시:

- 기존 namespace ensure를 재사용한다.
- ResourceQuota, LimitRange, 기본 deny NetworkPolicy를 idempotent 생성한다.
- Kubernetes toolbox ServiceAccount, Role, RoleBinding, Pod를 생성한다.
- Pod label에 user ID 원문 대신 stable server identifier와 environment를 넣는다.
- readiness를 제한 시간 동안 확인하고 실패 시 생성 리소스를 정리한다.
- namespace 전체 삭제는 개별 session cleanup에 사용하지 않는다.

인수 조건:

- 두 사용자의 sandbox resource가 namespace 밖으로 섞이지 않는다.
- toolbox ServiceAccount로 다른 namespace 조회가 거부된다.
- ensure를 두 번 호출해도 duplicate error가 없다.

### BE-05 host shell 제거

수정 파일:

- `backend/app/services/command_validator.py`
- `backend/app/services/command_executor.py`
- `backend/app/services/websocket_handler.py`
- validator/executor tests

구현 지시:

- `shell=True`, `create_subprocess_shell` 경로를 제거한다.
- validator output을 argv list로 바꾼다.
- executor는 server가 찾은 SandboxRef만 사용한다.
- output 최대 64KiB, DB 저장 5KiB, 기본 timeout 5초를 유지하고 환경별 override 상한을 둔다.
- 한 session의 동시 실행은 1개로 제한한다.
- print 디버깅을 구조화 logger로 교체하고 command output 본문은 info log에 남기지 않는다.

인수 조건:

- repository backend code에서 host shell 실행 0건.
- pipe, redirect, command substitution, encoded separator test가 거부된다.
- timeout 후 sandbox process와 server task가 정리된다.

### BE-06 WebSocket session 소유권

수정 파일:

- `backend/app/api/terminal.py`
- `backend/app/services/websocket_handler.py`
- WebSocket API tests

구현 지시:

- session을 `id == session_id AND user_id == JWT sub AND is_active`로 조회한다.
- 조회 실패 원인에 맞는 close code를 사용한다.
- namespace와 environment를 session에서 읽는다.
- session.last_activity를 연결 시와 명령 성공 시 갱신한다.
- 동일 session 중복 WebSocket 정책을 정한다. 권장: 새 연결이 이전 연결을 4000으로 종료.
- disconnect에서 active connection registry와 실행 lock을 정리한다.

인수 조건:

- 사용자 A token으로 사용자 B session 연결이 4003.
- 존재하지 않는 session은 4004.
- 정상 소유자만 CommandLog를 해당 session에 저장한다.

### BE-07 환경별 session API

수정 파일:

- `backend/app/schemas.py`
- `backend/app/api/terminal.py`
- `backend/app/services/sandbox_service.py`
- API tests

구현 지시:

- SessionCreate에 environment를 추가한다.
- `assert_implemented()`와 sandbox readiness를 모두 검사한다.
- 동일 환경 active session 재사용 정책을 구현한다.
- DELETE session API를 추가한다.
- sandbox 준비 실패 시 DB active session을 남기지 않는다.

인수 조건:

- kubernetes session 생성/재사용/삭제 흐름 통과.
- preparing environment는 400과 구체적 detail.
- response environment가 실제 DB와 일치.

---

## Sprint 2 - 5~6주차: 환경별 서비스 선택과 Kubernetes 회귀

### BE-08 environment 기반 factory

수정 파일:

- `backend/app/services/service_factory.py`
- `backend/app/services/mission_service.py`
- `backend/app/services/scenario_service.py`
- factory tests

구현 지시:

- factory key를 `(environment, configured_backend)`로 바꾼다.
- mock도 environment를 명시한 구현체를 반환한다.
- MissionService/ScenarioService가 시작 시 attempt environment로 injector/validator를 선택하게 한다.
- 환경별 service singleton을 만들기보다 stateless service + factory lookup을 우선한다.
- in-memory `_active_chaos_ids` 의존을 제거하고 DB chaos_id를 사용한다.

인수 조건:

- docker 요청이 Kubernetes injector를 받지 않는다.
- 미등록 조합은 명확한 ValueError/503.
- 서버 재시작 후 attempt.chaos_id로 cleanup 가능.

### BE-09 환경별 mission 조회·잠금·seed

수정 파일:

- `backend/app/api/missions.py`
- `backend/app/services/mission_service.py`
- `backend/app/services/seed_data.py`
- models/migration
- tests

구현 지시:

- list query를 environment로 필터한다.
- 이전 level 완료 조건도 같은 environment mission만 계산한다.
- start 시 mission.environment가 implemented인지 확인한다.
- seed에 stable key를 도입하고 upsert한다.
- `(environment, level)` unique constraint를 추가한다.
- Kubernetes 기존 4개 seed를 보존한다.

인수 조건:

- Kubernetes level 4 완료가 Docker level 2를 자동 unlock하지 않는다.
- 기존 DB에 Docker/Linux seed만 추가 가능하다.
- seed 재실행이 중복 행을 만들지 않는다.

### BE-10 Kubernetes toolbox 회귀

수정 파일:

- 기존 Kubernetes injector/validator/terminal 관련 파일
- integration tests

구현 지시:

- 기존 4개 미션을 toolbox kubectl 경로로 해결한다.
- Chaos Mesh와 toolbox RBAC가 필요한 resource patch/delete를 허용하는지 검증한다.
- forbidden cluster-wide command는 계속 차단한다.
- abandon/timeout/restart cleanup을 검증한다.

인수 조건:

- 기존 4개 미션 end-to-end 성공.
- 다른 namespace 접근 불가.
- host kubectl subprocess 0회.

---

## Sprint 3 - 7~8주차: Docker 환경

### BE-11 Docker sandbox

수정 파일:

- `sandbox_service.py`
- Kubernetes manifest/config
- tests

구현 지시:

- rootless DinD를 먼저 검증한다.
- rootless로 필수 network/volume/resource 시나리오가 불가능하면 제한된 privileged DinD를 사용하고 이유를 문서화한다.
- memory, CPU, ephemeral-storage limit과 readiness probe를 설정한다.
- 사용자 namespace 밖 network 접근을 최소화한다.
- sandbox 안에 훈련용 app container를 idempotent 생성한다.

인수 조건:

- `docker ps`가 sandbox 내부 container만 보여준다.
- host Docker daemon과 다른 사용자 DinD에 접근하지 못한다.
- Pod 삭제 후 ensure로 재생성 가능.

### BE-12 Docker command policy

수정 파일:

- `command_validator.py`
- tests

허용 최소 범위:

- read: ps, inspect, logs, stats --no-stream, network ls/inspect, volume ls/inspect.
- recovery: start, restart, update의 제한된 옵션, network connect, volume 관련 시나리오별 명령.
- block: run arbitrary image, exec arbitrary shell, system prune, rm -f broad target, context/host/socket 변경.

인수 조건:

- 모든 target 이름은 scenario가 허용한 resource set에 포함돼야 한다.
- `docker -H`, socket mount, privileged run이 차단된다.
- delete 계열은 confirmation 계약을 따른다.

### BE-13 DockerChaosInjector

신규 파일: `backend/app/services/docker_chaos_injector.py`.

최소 장애:

1. network disconnect: app container를 training network에서 분리.
2. volume/mount error: expected volume 연결을 끊거나 잘못된 mount target을 적용.
3. resource exhaustion: container memory/CPU limit을 안전한 sandbox 한도 안에서 낮춤.

구현 지시:

- inject 전 원상태 snapshot을 chaos metadata 또는 DB JSON에 저장한다.
- 동일 chaos_id inject/revert는 idempotent하다.
- revert가 실패하면 retry 가능한 상태와 원인을 기록한다.
- 사용자가 터미널로 실제 복구 가능한 장애만 등록한다.

### BE-14 DockerValidationService와 seed

신규 파일: `backend/app/services/docker_validation_service.py`.

- docker inspect/network/volume/container health를 sandbox exec로 검증한다.
- 문자열 출력만 보지 말고 JSON inspect 결과를 parse한다.
- 최소 3개 고정 mission seed를 추가한다.
- validation 결과 details는 내부 로그에 저장하되 정답을 API 메시지로 누설하지 않는다.

인수 조건:

- 주입 직후 false, 사용자가 복구한 뒤 true.
- revert 후 baseline true.
- 다른 sandbox 상태가 검증에 영향을 주지 않는다.

### BE-15 8주차 범위 게이트

- Kubernetes 회귀 4개 통과.
- Docker 고정 미션 3개 통과.
- session ownership 침투 테스트 통과.
- host shell 사용 0건.
- P0/P1 0개일 때만 Application/DB 또는 고급 Docker 장애를 검토한다.

#### 판정 결과 (2026-08-30, dev `0c4a573` 기준)

| 게이트 | 결과 | 근거 |
|---|---|---|
| Kubernetes 회귀 4개 | **4/4 통과** | 실클러스터에서 주입→장애감지→toolbox 복구→검증→revert 전 사이클 |
| Docker 고정 미션 3개 | **3/3 통과** | 동일. 복구 명령이 BE-12 정책을 통과하는 것까지 확인 |
| session ownership 침투 | **통과** | 사용자 A 토큰으로 B 세션 연결 시 4003, 없는 세션 4004 |
| host shell 사용 0건 | **통과** | `app/**` 전체 AST 검사(문자열 grep 아님) |
| P0/P1 0개 | **통과** | P0 4/4, P1 6/6 해소 |

**P0 (4/4 해소)**

| 결손 | 해소 |
|---|---|
| `CommandExecutor` host shell 실행 | BE-05 |
| WebSocket 세션 소유권 미검증 | BE-06 |
| environment 가 세션·명령 실행까지 미연결 | BE-03 / BE-07 |
| active chaos ID 가 프로세스 메모리에만 존재 | BE-02 / BE-08 |

**P1 (6/6 해소)**

| 결손 | 해소 |
|---|---|
| factory 가 environment 로 분기하지 않음 | BE-08 |
| MissionService 가 injector 를 고정 | BE-08 |
| 미션 목록·잠금이 environment 로 필터되지 않음 | BE-09 |
| `seed_missions()` 가 새 환경을 추가할 수 없음 | BE-09 |
| attempt 에 environment·chaos ID 없음 | BE-02 |
| 활성 attempt 유일성 DB 제약 없음 | BE-02 |

**P2 (1/4 해소, 게이트 조건 아님)**

| 결손 | 상태 |
|---|---|
| `create_all` + 수동 ALTER | 해소 (BE-02 Alembic) |
| CORS wildcard | 미해소 → BE-23 |
| print 디버깅 (`app/**` 21건) | 미해소 → BE-23 |
| 환경별 분석 API 없음 | 미해소 → BE-21 |

> 게이트를 통과했으므로 Application/DB 또는 고급 Docker 장애를 **검토할 수 있다.**
> 다만 필수 환경 3종 중 Linux 가 아직 없고, Application 은 목업 한정으로 이미
> 결정돼 있다(AGENTS.md). 범위 확대보다 Sprint 4(Linux)를 계획대로 진행하는 것을
> 권고한다. 최종 결정은 팀이 한다.

---

## Sprint 4 - 9~10주차: Linux 환경

### BE-16 Linux sandbox와 command policy

수정 파일:

- `sandbox_service.py`
- `command_validator.py`
- tests

구현 지시:

- 범용 Linux image에 필요한 관측 도구만 포함한다.
- container cgroup/ephemeral storage 범위 안에서 장애를 재현한다.
- host PID, host filesystem, host network를 mount하지 않는다.
- `ps`, `free`, `df`, `du`, `systemctl status` 대체, `journalctl`, `dmesg`, `ss` 중 실제 container에서 동작하는 명령만 노출한다.
- shell built-in이 필요하면 고정된 server script를 실행하고 사용자 문자열을 shell에 삽입하지 않는다.

### BE-17 LinuxChaosInjector

신규 파일: `backend/app/services/linux_chaos_injector.py`.

최소 장애:

1. OOM: child workload에 낮은 cgroup memory limit을 적용해 sandbox 내부 OOM 유도.
2. disk I/O: 제한된 ephemeral volume에서 `dd`/stress-ng workload로 I/O 포화.
3. zombie/orphan: 고정된 교육용 helper process로 생성.

안전 기준:

- host OOM-Killer를 직접 유발하지 않는다.
- host disk를 채우지 않는다.
- process count/PID limit을 설정한다.
- 모든 workload에 duration/timeout과 cleanup handler가 있다.

### BE-18 LinuxValidationService와 seed

신규 파일: `backend/app/services/linux_validation_service.py`.

- OOM workload/서비스 정상화, disk usage/I/O worker 종료, zombie count를 검증한다.
- 가능하면 `/proc`, process exit code, cgroup 파일을 구조적으로 읽는다.
- 최소 3개 고정 mission seed를 추가한다.
- 검증 결과 반영 시간 300ms 목표를 측정한다. 외부 Prometheus 의존 검증은 별도 latency로 기록한다.

인수 조건:

- 세 장애 주입/복구/검증 반복 성공.
- sandbox 밖 process/filesystem에 영향 0건.
- timeout/포기 cleanup 성공.

---

## Sprint 5 - 11~12주차: AI·대시보드 통합 계약

### BE-19 환경별 RuntimeContext 제공

수정 파일:

- `backend/app/services/runtime_context.py`
- context tests

구현 지시:

- collector 입력에 environment와 SandboxRef를 추가한다.
- 공통 출력 schema를 유지한다.

```json
{
  "environment":"docker",
  "scope":{"namespace":"...","sandbox_id":"..."},
  "mission":{},
  "recent_user_commands":[],
  "observations":{},
  "metrics":{},
  "logs":[]
}
```

- Kubernetes/Docker/Linux 수집 함수를 registry로 선택한다.
- timeout을 환경별로 적용하고 부분 실패를 허용한다.
- token, secret, password, 전체 환경변수는 redaction한다.
- AI 담당자에게 정답이 아닌 관측값만 전달한다.

### BE-20 AI scenario 실행 계약

수정 파일:

- `scenario_service.py`
- `validation_rule_service.py`
- `chaos_plan.py`
- API tests

구현 지시:

- environment별 allowed fault type을 AI에 전달한다.
- AI output environment가 요청과 일치하는지 검사한다.
- ChaosPlanCompiler가 environment별 허용 step만 컴파일한다.
- mechanical validation이 score의 유일한 승인 기준이다.
- LLM ValidationAgent는 설명/advisory로 저장하되 mechanical false를 true로 뒤집지 않는다.
- last_validation_result에 environment, rules, timings를 저장한다.

인수 조건:

- Docker AI scenario가 Docker injector/validator만 사용한다.
- AI가 허용되지 않은 command/fault를 생성하면 reject.
- LLM 오판으로 완료 처리되지 않는다.

### BE-21 환경별 analytics

수정 파일:

- `analytics_service.py`
- `api/dashboard.py`
- schemas/tests

구현 지시:

- attempt.environment로 필터한다.
- average MTTR, average score, hints, completed를 집계한다.
- competency 기본식:

```text
score_component = average_score
speed_component = clamp(100 - average_mttr / target_mttr * 50, 0, 100)
hint_component = clamp(100 - hints_per_completion * 15, 0, 100)
competency = round(0.5*score + 0.3*speed + 0.2*hint)
```

- target_mttr은 mission time limit 기반 또는 환경 config로 문서화한다.
- attempt 0건은 competency null을 권장한다.
- AI scenario의 mission_id null 때문에 기존 learning curve counting이 잘못되지 않게 key를 분리한다.

인수 조건:

- 환경별 집계와 all 합계가 일치한다.
- abandoned/failed를 completed MTTR에 포함하지 않는다.
- 동일 AI scenario attempt가 mission_id None key로 모두 합쳐지지 않는다.

---

## Sprint 6 - 13~14주차: 신뢰성·성능·운영 보안

### BE-22 동시성·idempotency·복구

수정 파일:

- mission/scenario/sandbox services
- models/migration
- tests

구현 지시:

- 미션 시작 transaction에서 active attempt 제약 충돌을 사용자 오류로 변환한다.
- inject 성공 후 DB commit 실패 시 즉시 revert한다.
- DB attempt 생성 후 inject 실패 시 attempt를 failed/rejected 상태로 남기거나 transaction rollback 정책을 고정한다.
- cleanup 작업에 retry count, last_error, next_retry_at을 저장하거나 최소 startup reconciliation job을 둔다.
- startup에서 running attempt와 실제 sandbox/chaos 상태를 대조한다.
- timeout cleanup을 status 조회에만 의존하지 않도록 주기 작업 또는 요청 기반 reconciliation을 둔다.

인수 조건:

- 동시 start 2개 중 하나만 성공.
- 서버 재시작 뒤 active attempt status/cleanup 복원.
- revert 두 번 호출 안전.

### BE-23 운영 설정과 관측

수정 파일:

- `core/config.py`
- `core/metrics.py`
- `main.py`
- `.env.example`

추가 설정:

- `CORS_ORIGINS`.
- sandbox image/tag, resource limits, command timeout/output limit.
- session idle TTL.
- cleanup interval.

추가 메트릭:

- sandbox provision duration/result by environment.
- command duration/result by environment와 command category. 원문 command label 금지.
- chaos inject/revert duration/result.
- validation duration/result.
- active sessions/attempts by environment.
- cleanup failures.
- **AI 호출 duration/result/token by provider·용도(scenario|tutor|validation).**
  AI 담당 문서 §8이 요구하는 "AI metrics endpoint/registry"가 이 항목이다.
  registry는 기존 `/metrics`를 공유하고 AI 담당은 계측 지점만 호출한다.

추가 rate limit:

- **`POST /api/chat/`에 사용자당 rate limit.** AI 담당 문서 §8이 백엔드에 요구한 항목이며
  백엔드 계획서에는 배정돼 있지 않았다(2026-08-28 확인).
- 한도 초과는 429와 재시도 가능 시각을 함께 응답한다. 프론트가 화면에 표시할 수 있어야 한다.
- LLM 호출 비용과 직결되므로 AI_BACKEND가 mock이 아닐 때 반드시 적용한다.

인수 조건:

- 운영 모드에서 wildcard CORS가 아니다.
- metrics label에 user ID, namespace, command, scenario title이 없다.
- health와 readiness를 구분하고 PostgreSQL/K8s/Qdrant 의존 상태를 적절히 노출한다.
- 한도를 넘긴 chat 요청이 429로 거절되고 정상 요청은 영향받지 않는다.
- AI 호출 메트릭 label에 프롬프트·응답 본문이 들어가지 않는다.

### BE-24 테스트 확대

필수 테스트:

1. session owner mismatch WebSocket 거부.
2. environment/session/sandbox mismatch 거부.
3. host shell 실행 경로 없음.
4. 환경별 command allow/block matrix.
5. factory 조합 선택.
6. mission environment filter/unlock.
7. concurrent active attempt constraint.
8. inject 실패 rollback.
9. restart reconciliation.
10. Docker/Linux inject-revert-validation.
11. analytics environment 집계.
12. AI scenario environment mismatch reject.

테스트 단계:

- unit: mock Kubernetes client와 fake executor.
- API: FastAPI dependency override + test DB.
- integration: Docker Desktop Kubernetes에서 marker `integration`.
- 실제 privileged/DinD test는 기본 unit suite와 분리한다.

### BE-29 TutorMessage 보존 정책

수정 파일:

- `backend/app/models.py` (기존 `TODO(phase7)` 주석 해소)
- 신규 정리 작업 또는 startup reconciliation
- migration
- tests

배경: AI 담당 문서 §8이 "TutorMessage retention job"을 백엔드에 요구하지만
백엔드 계획서에 배정돼 있지 않았다(2026-08-28 확인). `models.py`에는
`TODO(phase7): created_at 기준 30일 경과 레코드 자동 삭제 배치 추가 예정` 주석만 있다.

구현 지시:

- 보존 기간을 설정값으로 두고(기본 30일) 경과 레코드를 주기적으로 삭제한다.
- 삭제 주기는 BE-22의 cleanup/reconciliation 경로에 얹고 별도 스케줄러를 새로 만들지 않는다.
- 진행 중인 attempt의 대화는 기간이 지나도 삭제하지 않는다.
- 삭제 건수를 메트릭 또는 로그로 남기되 메시지 본문은 남기지 않는다.

인수 조건:

- 보존 기간이 지난 메시지가 삭제되고 진행 중 attempt의 메시지는 남는다.
- 반복 실행해도 안전하다.
- 삭제가 실패해도 요청 처리 경로에 영향을 주지 않는다.

---

## Sprint 7 - 15~16주차: EKS·통합·제출

### BE-25 EKS 배포 보안

- namespace-scoped Role/RoleBinding 검증.
- toolbox/DinD/Linux image를 immutable tag 또는 digest로 고정.
- Secret은 Kubernetes Secret/배포 환경에서 주입하고 repo에 저장하지 않는다.
- privileged workload는 별도 node pool 또는 local demo 한정 여부를 확정한다.
- Pod Security, NetworkPolicy, ResourceQuota 적용 결과를 기록한다.
- database migration을 배포 전 job으로 실행한다.

### BE-26 환경별 end-to-end 검증

| 환경 | 최소 반복 | 검증 |
|---|---:|---|
| Kubernetes | 2회 x 4미션 | kubectl, Chaos Mesh, K8s validation |
| Docker | 2회 x 3미션 | DinD 격리, Docker injector/validator |
| Linux | 2회 x 3미션 | cgroup/ephemeral/PID 격리, Linux validator |

각 실행에서 session user/environment, sandbox ID, inject/revert, validation latency, cleanup을 기록한다.

### BE-27 성능 검증

- 자동 검증 API 처리 목표 300ms. 외부 Prometheus/LLM 단계는 분리 측정.
- session 재사용 시 API p95 목표 300ms, 신규 sandbox provision은 별도 지표.
- WebSocket command 응답은 command 자체 실행 시간을 제외한 server overhead를 측정한다.
- 3명 동시 사용자 x 3환경 resource 사용량을 측정한다.

### BE-28 문서와 시연

갱신 파일:

- `backend/CLAUDE.md`
- `README.md`
- `docs/api-guide.md`
- `agent.md`
- `.env.example`

필수 문서:

- API request/response와 WebSocket close code.
- sandbox/RBAC/privileged 결정.
- environment별 command policy.
- injector/validator 추가 방법.
- migration/rollback.
- cleanup/reconciliation.
- local mock, local Kubernetes, EKS 실행법.
- 알려진 제한과 Application/DB 후속 범위.

최종 완료 조건:

- P0/P1 0개.
- backend unit/API test green.
- 세 환경 end-to-end 통과.
- 다른 사용자 namespace/session 접근 실패 증빙.
- host shell 실행 0건.
- 서버 재시작 복구 시나리오 통과.
- 프론트·AI 계약과 실제 OpenAPI가 일치.

---

## 7. 작업 의존성

```text
BE-00 결정
  -> BE-01 테스트 기준선
  -> BE-02 migration/attempt state
  -> BE-03 API environment
      -> BE-04 sandbox
      -> BE-05 safe executor
      -> BE-06 ownership
      -> BE-07 session API
          -> BE-08 factory
          -> BE-09 mission/seed
          -> BE-10 K8s regression
              -> BE-11~14 Docker
              -> BE-16~18 Linux
                  -> BE-19 context
                  -> BE-20 AI scenario
                  -> BE-21 analytics
                      -> BE-22~24, BE-29 hardening
                          -> BE-25~28 release
```

---

## 8. 팀 간 인계점

> **계약을 바꾼 PR은 머지 직후 담당자에게 직접 알린다.** PR 본문에 적는 것만으로는
> 전달되지 않는다. 아래 항목이 바뀌면 해당 담당자에게 알린 뒤 다음 작업으로 넘어간다.
> `schemas.py` / WebSocket close code / 환경 가용성 status 값 / 명령 정책 / 응답 필드 추가·삭제.

### 프론트엔드에 제공할 것

- API-BE-01~06 OpenAPI 예시.
- environment availability 기준.
- WebSocket close code와 error message.
- 환경별 command capability.
- Grafana UID/readiness query 또는 조회 API.
- mock/real validation 구분.

### AI 담당자에게 제공할 것

- environment별 allowed fault types.
- TrainingContext schema.
- sandbox observations 수집 함수.
- environment별 mechanical validation rule 계약.
- scenario output에서 허용할 chaos plan step.
- latency/token metrics 저장 경계.

### 백엔드 계획서에 배정되지 않았던 요구 (2026-08-28 정리)

AI·프론트 계획서가 백엔드에 요구하지만 이 문서의 작업 ID에 없던 항목이다.
발견 시점에 아래처럼 배정했다. 같은 누락이 또 나오면 여기에 추가한다.

| 요구 출처 | 항목 | 배정 |
|---|---|---|
| 프론트 API-01 | `GET /api/environments` 환경 가용성 | BE-03에서 구현 완료 |
| AI §8 | chat rate limit | BE-23 |
| AI §8 | AI metrics endpoint/registry | BE-23 |
| AI §8 | TutorMessage retention job | **BE-29 신설** |
| 프론트 API-08 | 환경별 Grafana UID 조회 API | 조건부. 초기에는 프론트 config를 쓰고, 운영에서 UID가 자주 바뀌면 `GET /api/environments` 응답에 `observability` 객체를 추가한다 |
| 프론트 5.1 | `EnvironmentStatus`의 `degraded` / `disabled` | 백엔드는 현재 `available` / `preparing`만 내보낸다. 프론트는 화면을 먼저 갖췄으므로, 이 값을 실제로 쓰려면 백엔드가 판정 기준(무엇을 degraded로 볼 것인가)을 먼저 정해야 한다. BE-23의 health/readiness 작업과 함께 결정한다 |

### AI 담당자에게 요구할 것

- environment가 포함된 scenario candidate.
- 허용 fault type 이외 생성 금지.
- source/observation을 포함한 tutor result.
- validation advisory 결과와 confidence. 최종 score 승인은 backend mechanical validator.

---

## 9. PR 권장안

| PR | 브랜치 예시 | 작업 |
|---|---|---|
| 1 | `feature/backend-baseline` | BE-01~03 |
| 2 | `feature/env-sandbox` | BE-04, BE-07 |
| 3 | `feature/safe-terminal-exec` | BE-05, BE-06 |
| 4 | `feature/env-runtime` | BE-08~10 |
| 5 | `feature/docker-env` | BE-11~14 |
| 6 | `feature/linux-env` | BE-16~18 |
| 7 | `feature/cross-layer-contracts` | BE-19~21 |
| 8 | `feature/backend-hardening` | BE-22~24, BE-29 |
| 9 | `feature/aws-migration` | BE-25 |
| 10 | `feature/backend-release` | BE-26~28 |

---

## 10. Definition of Done

각 작업:

- [ ] 입력 environment를 검증했다.
- [ ] session owner와 execution target을 서버에서 결정한다.
- [ ] shell 문자열 실행을 추가하지 않았다.
- [ ] 실패 시 DB와 sandbox/chaos 상태가 일관된다.
- [ ] cleanup/retry 경로가 있다.
- [ ] 사용자에게 내부 정답·secret·stack trace를 노출하지 않는다.
- [ ] unit 또는 API test를 추가했다.
- [ ] `python -m pytest -q` 결과를 기록했다.
- [ ] OpenAPI/문서와 구현이 일치한다.

환경 완료:

- [ ] sandbox ensure/ready/cleanup.
- [ ] command allow/block matrix.
- [ ] 최소 3개 mission seed.
- [ ] injector inject/revert idempotency.
- [ ] validator false-before/true-after.
- [ ] timeout/abandon/restart cleanup.
- [ ] AI scenario environment 관통.
- [ ] analytics environment 집계.
- [ ] 사용자 간 격리 테스트.

---

## 11. 위험과 대응

| 위험 | 대응 |
|---|---|
| DinD privileged 필요 | rootless 우선 검증, 불가 시 local demo/전용 node/strict quota로 범위 제한 |
| Linux host 수준 장애 요구 | container cgroup/ephemeral/PID 범위로 교육 목표를 재정의하고 host 장애 금지 |
| sandbox 생성 지연 | session 재사용, readiness 분리, provision latency 별도 표시 |
| 서버 재시작 후 chaos 유실 | attempt에 chaos_id/sandbox_id 저장, startup reconciliation |
| AI가 허용되지 않은 장애 생성 | environment allowlist + ChaosPlanCompiler reject |
| validator false positive | deterministic mechanical check만 score 승인 |
| 환경별 코드 복제 | 기존 registry/factory와 공통 service 흐름 재사용 |
| migration 실패 | Alembic upgrade test와 백업/rollback 문서 |
| 로그 민감정보 | 구조화 logger, output truncation/redaction, metrics low-cardinality |

---

## 12. 최종 산출물

- Kubernetes/Docker/Linux 사용자별 sandbox와 격리 정책.
- 환경별 안전한 WebSocket terminal executor.
- DockerChaosInjector, LinuxChaosInjector와 각 validator.
- environment가 관통된 mission/scenario/session/attempt API.
- DB 기반 chaos 상태와 재시작 reconciliation.
- 환경별 미션 seed·잠금·점수·MTTR·analytics.
- AI 환경 context와 mechanical validation 계약.
- 단위/API/integration test.
- local Docker Desktop과 EKS 실행·보안·복구 문서.

백엔드의 핵심 성공 기준은 장애 종류의 개수가 아니라, 사용자가 선택한 환경·세션·sandbox·injector·validator가 하나의 동일한 environment로 연결되고 다른 사용자나 host에 영향을 주지 않는 것이다.
