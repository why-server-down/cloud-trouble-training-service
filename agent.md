# AI Agent Implementation Plan

## 목표

이 프로젝트를 정적 미션 기반의 Kubernetes 장애 훈련 서비스에서, AI가 장애 시나리오 생성, 장애 주입 계획, 검증 조건 생성, 로그 기반 튜터링, RAG 지식 검색까지 담당하는 동적 클라우드 장애 대응 훈련 플랫폼으로 개편한다.

현재 구조는 이미 좋은 출발점이 있다.

- `backend/`: FastAPI, 미션 시작/상태/검증 API, 터미널 WebSocket, 명령 로그 저장
- `backend/app/services/chaos_injector.py`: Chaos Mesh 기반 장애 주입
- `backend/app/services/validation_service.py`: Kubernetes API 또는 Prometheus 기반 검증
- `backend/app/ai/tutor_service.py`: AI 튜터 어댑터
- `ai-data/`: RAG, Qdrant, 프롬프트 엔진, 지식 문서
- `infra/monitoring/`: Prometheus, recording rules, alert rules, Loki, Grafana

개편 방향은 기존 4개의 정적 미션을 보존하면서, 그 아래에 `AI 문제 더 풀기` 흐름을 추가하는 것이다. 기본 미션은 온보딩과 핵심 개념 학습용으로 유지하고, AI 미션은 사용자가 난이도를 고르면 AI가 생성한 `TrainingScenario`를 백엔드가 검증한 뒤 실행하는 확장 훈련 모드로 제공한다.

## 훈련 모드

### 기본 미션 모드

현재 구현된 4개 미션은 그대로 유지한다.

- Level 1: `pod_failure`
- Level 2: `memory_stress`
- Level 3: `service_misconfig`
- Level 4: `network_latency`

이 모드는 사용자가 Kubernetes 장애 대응 기본 흐름을 순서대로 익히는 고정 커리큘럼이다. 기존 `/api/missions` API, `Mission` 테이블, 순차 잠금 해제, 점수 계산, 힌트 감점은 계속 유지한다.

### AI 문제 더 풀기 모드

기본 4개 미션 목록 아래에 `AI 문제 더 풀기` 영역을 추가한다.

사용자 흐름:

1. 기본 미션 목록을 본다.
2. 아래의 `AI 문제 더 풀기` 버튼을 누른다.
3. 난이도를 선택한다: Beginner, Intermediate, Advanced, Expert.
4. 백엔드가 AI 시나리오 후보를 생성하고 안전성/검증 가능성을 점수화한다.
5. 최종 선택된 시나리오가 사용자 namespace에 주입된다.
6. 사용자는 기존과 같은 터미널, 튜터, 검증 버튼으로 문제를 푼다.

즉 정적 미션을 대체하지 않고, 기본 미션 완료 후 계속 연습할 수 있는 무한 문제 생성 모드로 붙인다.

## 핵심 원칙

AI는 판단과 생성에 사용하고, 클러스터에 직접 명령을 실행하는 권한은 주지 않는다.

반드시 다음 분리 원칙을 지킨다.

- AI는 장애 시나리오, Chaos Mesh 스펙 후보, PromQL 검증 조건 후보, 튜터 응답 후보를 만든다.
- 백엔드는 JSON Schema, allowlist, 난이도 정책, namespace 격리, PromQL 정적 검사, Kubernetes 리소스 제한을 통과한 것만 실행한다.
- 사용자의 namespace 밖 리소스는 절대 생성/수정/삭제하지 않는다.
- 검증 조건은 AI가 만든 PromQL을 그대로 신뢰하지 않고, 백엔드의 `ValidationRuleGuard`를 통과해야 한다.
- 튜터는 정답을 바로 주지 않고, 힌트 레벨에 따라 관찰 질문에서 완전 해설까지 점진적으로 이동한다.

## 목표 아키텍처

```text
Frontend
  Static Mission UI
  AI More Problems UI
  Terminal
  Tutor Chat
  Scenario/Progress View
        |
        v
Backend FastAPI
  MissionOrchestrator
  ScenarioAgentService
  ChaosPlanCompiler
  ChaosExecutor
  ValidationRuleService
  RuntimeContextCollector
  TutorAgentService
        |
        +--> PostgreSQL
        |      missions / generated_scenarios / attempts
        |      validation_rules / command_logs / tutor_messages
        |
        +--> Kubernetes API / Chaos Mesh
        |
        +--> Prometheus HTTP API
        |
        +--> Loki HTTP API
        |
        +--> Qdrant RAG
        |
        +--> LLM Provider
```

## 에이전트 구성

### 1. Scenario Generator Agent

역할:

- 난이도, 학습 목표, 사용자 레벨, 최근 플레이 기록을 입력으로 받는다.
- 클라우드 장애 대응 훈련용 시나리오를 생성한다.
- Kubernetes/Prometheus/Loki에서 관찰 가능한 증상을 포함한다.
- 정답을 사용자가 바로 알 수 없도록 미션 설명과 내부 정답을 분리한다.

입력:

```json
{
  "difficulty": "beginner | intermediate | advanced | expert",
  "target_platform": "kubernetes",
  "namespace": "user-...",
  "allowed_fault_types": ["image_pull_error", "oom_killed", "service_selector_mismatch", "network_latency", "probe_failure"],
  "recent_completed_fault_types": ["image_pull_error"],
  "time_limit_seconds": 1200
}
```

출력은 반드시 구조화된 JSON으로 받는다.

```json
{
  "title": "Checkout API가 간헐적으로 실패합니다",
  "difficulty": "intermediate",
  "learning_objectives": [
    "Service selector와 Pod label의 관계를 설명할 수 있다",
    "Endpoints가 비어 있는 상태를 진단할 수 있다"
  ],
  "student_brief": "checkout 서비스가 배포되었지만 요청이 Pod까지 전달되지 않습니다. 원인을 찾아 정상화하세요.",
  "internal_summary": "Service selector app=checkout-api-broken 때문에 Endpoints가 생성되지 않는 장애",
  "fault": {
    "type": "service_selector_mismatch",
    "target": {
      "kind": "Service",
      "name": "checkout-svc",
      "namespace": "{{namespace}}"
    },
    "parameters": {
      "wrong_selector": {
        "app": "checkout-api-broken"
      },
      "expected_selector": {
        "app": "checkout-api"
      }
    }
  },
  "expected_solution": {
    "summary": "Service selector를 Pod label과 일치하도록 수정한다",
    "allowed_fix_patterns": [
      "kubectl patch service checkout-svc",
      "kubectl edit service checkout-svc",
      "kubectl apply -f"
    ]
  },
  "observability": {
    "symptoms": [
      "Service의 Endpoints가 비어 있음",
      "Pod는 Running 상태",
      "애플리케이션 요청은 503 또는 connection refused"
    ],
    "suggested_queries": [
      "kube_endpoint_address{namespace=\"{{namespace}}\", endpoint=\"checkout-svc\"}"
    ],
    "log_signals": [
      "no endpoints available for service"
    ]
  },
  "validation": {
    "success_promql": [
      "sum(kube_endpoint_address{namespace=\"{{namespace}}\", endpoint=\"checkout-svc\", ready=\"true\"}) > 0"
    ],
    "stability_seconds": 30
  },
  "scoring": {
    "base_score": 100,
    "hint_penalty": 7,
    "time_limit_seconds": 1500
  }
}
```

### AI 문제 생성/선택 알고리즘

`AI 문제 더 풀기`에서 사용자가 난이도를 고르면, AI가 바로 하나의 장애를 실행하는 것이 아니라 다음 순서로 동작한다.

```text
User selects difficulty
  |
  v
Backend builds generation context
  - user progress
  - completed static missions
  - recent AI scenario fault types
  - allowed fault types
  - available metrics
  - namespace policy
  |
  v
AI generates 3 scenario candidates
  |
  v
Backend validates and scores each candidate
  |
  v
Weighted random selection among accepted candidates
  |
  v
Compile to ChaosPlan + ValidationRules
  |
  v
Inject only after safety checks pass
```

AI가 후보를 만들 때 보는 기준:

- 선택한 난이도에 맞는가
- 사용자가 최근에 푼 장애와 중복되지 않는가
- 기본 4개 미션에서 배운 개념을 자연스럽게 확장하는가
- RAG 저장소의 실제 장애 로그와 유사한 학습 가치가 있는가
- Kubernetes/Prometheus/Loki에서 관찰 가능한 증상이 있는가
- Prometheus나 Kubernetes API로 완료 검증이 가능한가

백엔드가 최종 선택할 때 계산하는 점수:

```text
total_score =
  difficulty_fit_score
  + learning_value_score
  + novelty_score
  + observability_score
  + validation_score
  + rollback_score
  - risk_penalty
```

점수 항목:

- `difficulty_fit_score`: 요청 난이도와 실제 장애 복잡도가 맞으면 가산
- `learning_value_score`: 기본 미션 이후 학습 확장성이 높으면 가산
- `novelty_score`: 최근 사용자가 푼 fault type과 다르면 가산
- `observability_score`: Pod/Event/Metric/Log에서 단서가 명확하면 가산
- `validation_score`: PromQL/K8s rule로 안정적으로 검증 가능하면 가산
- `rollback_score`: 자동 복구 계획이 명확하면 가산
- `risk_penalty`: namespace 범위가 모호하거나 stress/latency가 과하면 감점 또는 거절

후보가 모두 거절되면 다음 순서로 fallback한다.

1. AI에게 safety violation reason을 포함해 1회 재생성 요청
2. 그래도 실패하면 난이도별 mock fixture scenario 사용
3. mock도 실패하면 사용자에게 “AI 문제 생성 실패”를 보여주고 기본 미션 화면으로 돌아간다

구현 위치:

- 새 파일: `backend/app/ai/scenario_agent.py`
- 새 파일: `backend/app/services/scenario_service.py`
- 기존 변경: `backend/app/services/mission_service.py`
- 기존 변경: `backend/app/models.py`

### 2. Chaos Plan Compiler

역할:

- AI가 만든 `fault`를 바로 실행하지 않고 내부 표준 `ChaosPlan`으로 컴파일한다.
- 허용된 장애 타입만 처리한다.
- 모든 리소스 이름, namespace, label, duration, stress 크기, latency 값을 정책으로 제한한다.

지원할 장애 타입 1차 범위:

- `image_pull_error`: Deployment image를 잘못된 태그로 변경
- `crash_loop`: container command/env를 잘못 설정해 CrashLoopBackOff 유도
- `oom_killed`: memory limit 축소 또는 StressChaos 적용
- `service_selector_mismatch`: Service selector를 잘못된 label로 변경
- `network_latency`: Chaos Mesh NetworkChaos delay 적용
- `probe_failure`: readiness/liveness probe 경로 또는 포트 오류 유도
- `configmap_misconfig`: ConfigMap 키 누락 또는 잘못된 값 적용

`ChaosPlan` 예시:

```json
{
  "id": "scenario-...",
  "namespace": "user-...",
  "steps": [
    {
      "kind": "k8s_patch",
      "resource": "deployment",
      "name": "checkout-api",
      "patch": {
        "spec": {
          "template": {
            "spec": {
              "containers": [
                {
                  "name": "app",
                  "image": "checkout-api:broken"
                }
              ]
            }
          }
        }
      }
    }
  ],
  "rollback": [
    {
      "kind": "k8s_patch",
      "resource": "deployment",
      "name": "checkout-api",
      "patch": {
        "spec": {
          "template": {
            "spec": {
              "containers": [
                {
                  "name": "app",
                  "image": "checkout-api:latest"
                }
              ]
            }
          }
        }
      }
    }
  ]
}
```

구현 위치:

- 새 파일: `backend/app/services/chaos_plan.py`
- 기존 변경: `backend/app/services/chaos_injector.py`

현재 `ChaosMeshInjector.inject(chaos_type, namespace)`는 문자열 타입만 받는다. 개편 후에는 다음 메서드를 추가한다.

```python
async def inject_plan(self, plan: ChaosPlan) -> ChaosResult:
    ...
```

기존 정적 미션과 호환하려면 `inject()`는 유지하고 내부에서 간단한 `ChaosPlan`으로 변환한다.

### 3. Validation Rule Generator Agent

역할:

- 시나리오의 성공 조건을 PromQL 후보로 만든다.
- 단일 순간 값만 보지 않고 안정화 기간을 포함한다.
- Kubernetes API 검증 조건도 함께 생성할 수 있다.

중요한 설계:

- Prometheus에 “AI가 직접 입력”하지 않는다.
- AI가 만든 검증 조건은 `validation_rules` 테이블에 저장한다.
- 검증 시에는 Prometheus HTTP API `/api/v1/query` 또는 `/api/v1/query_range`로 실행한다.
- recording/alert rule이 꼭 필요하면 백엔드가 `infra/monitoring/generated_rules.yml`을 생성하고 Prometheus `/-/reload`를 호출한다.

권장 1차 구현은 DB 저장 + Prometheus HTTP API query 방식이다. 이 방식은 Prometheus config reload가 필요 없고, 사용자별 동적 미션과 잘 맞는다.

추후 recording rule이 필요하면 다음을 추가한다.

- `infra/monitoring/generated_rules.yml`
- `prometheus.yml`의 `rule_files`에 `/etc/prometheus/generated_rules.yml` 추가
- `docker-compose.yml`에서 해당 파일을 read-write 또는 generated volume으로 mount
- Prometheus 실행 옵션에 `--web.enable-lifecycle` 추가
- 백엔드 `PrometheusRuleManager`가 파일을 원자적으로 갱신하고 `POST http://prometheus:9090/-/reload` 호출

검증 조건 스키마:

```json
{
  "rules": [
    {
      "name": "checkout_service_has_ready_endpoint",
      "type": "promql",
      "query": "sum(kube_endpoint_address{namespace=\"{{namespace}}\", endpoint=\"checkout-svc\", ready=\"true\"}) > 0",
      "operator": "truthy",
      "stability_seconds": 30,
      "explanation": "Service가 최소 하나 이상의 ready endpoint를 가져야 한다"
    }
  ],
  "all_required": true
}
```

PromQL Guard 규칙:

- `namespace="{{namespace}}"` 또는 백엔드가 주입한 사용자 namespace label이 반드시 있어야 한다.
- `namespace=~".*"` 같은 broad regex 금지
- `job`, `instance`, `pod`, `container`, `deployment`, `service`, `endpoint` 외 label matcher는 allowlist 기반으로 허용
- `sum`, `min`, `max`, `avg`, `count`, `rate`, `increase`, `histogram_quantile`, `clamp_min`, 비교 연산자만 1차 허용
- query 길이 제한
- `{namespace!=""}` 같은 전체 namespace 조회 금지
- `absent()`는 잘못 쓰면 정상 상태를 오판하기 쉬우므로 1차 구현에서는 금지

구현 위치:

- 새 파일: `backend/app/ai/validation_agent.py`
- 새 파일: `backend/app/services/validation_rule_service.py`
- 새 파일: `backend/app/services/promql_guard.py`
- 기존 변경: `backend/app/services/validation_service.py`

### 4. Runtime Context Collector

역할:

- AI 튜터가 현재 상태를 실제로 보고 대답할 수 있도록 Kubernetes, Prometheus, Loki, 명령 이력을 모은다.
- 튜터 프롬프트에는 raw 로그를 너무 많이 넣지 않고 최근 핵심 신호만 요약해서 넣는다.

수집 대상:

- Kubernetes:
  - `kubectl get pods`
  - Pod phase, ready condition, restart count
  - Deployment rollout status
  - Service selector, Endpoints
  - Events
- Prometheus:
  - 시나리오 검증 PromQL 결과
  - CPU/memory/restart/network/probe 관련 지표
- Loki:
  - 문제 namespace의 최근 애플리케이션 로그
  - 오류 키워드 주변 로그
- DB:
  - 사용자가 최근 실행한 명령어
  - 명령어 출력 요약
  - 이전 질문과 힌트 레벨

프롬프트에 넣을 컨텍스트 예시:

```json
{
  "namespace": "user-...",
  "mission": {
    "title": "Checkout API가 간헐적으로 실패합니다",
    "difficulty": "intermediate",
    "student_brief": "..."
  },
  "kubernetes_state": {
    "pods": [
      {
        "name": "checkout-api-...",
        "phase": "Running",
        "ready": true,
        "restart_count": 0,
        "labels": {
          "app": "checkout-api"
        }
      }
    ],
    "services": [
      {
        "name": "checkout-svc",
        "selector": {
          "app": "checkout-api-broken"
        },
        "ready_endpoints": 0
      }
    ],
    "recent_events": [
      "Service checkout-svc has no active endpoints"
    ]
  },
  "prometheus": {
    "validation_results": [
      {
        "rule": "checkout_service_has_ready_endpoint",
        "passed": false,
        "last_value": 0
      }
    ]
  },
  "recent_user_commands": [
    {
      "command": "kubectl get pods",
      "exit_code": 0,
      "output_summary": "1 checkout-api pod Running"
    },
    {
      "command": "kubectl describe svc checkout-svc",
      "exit_code": 0,
      "output_summary": "Selector app=checkout-api-broken, Endpoints none"
    }
  ]
}
```

구현 위치:

- 새 파일: `backend/app/services/runtime_context.py`
- 기존 변경: `backend/app/ai/tutor_service.py`
- 기존 변경: `ai-data/prompt_engine.py`

### 5. Socratic Tutor Agent

역할:

- 직접 로그, 이벤트, Prometheus 결과, 사용자 명령 이력을 보고 질문한다.
- 사용자가 이미 확인한 내용을 반복하지 않는다.
- 힌트 레벨이 낮을수록 질문 중심, 높을수록 명령/해결책 중심으로 응답한다.
- RAG에서 유사 장애 로그와 해결 패턴을 검색해 답변 근거로 삼는다.

힌트 정책:

- Level 0: 관찰 방향만 제시. 명령어 금지.
- Level 1: 확인할 리소스와 로그 영역을 지목. 정확한 명령어는 아직 금지.
- Level 2: 정확한 명령어 제공. 단, 바로 patch 명령을 주지 않고 관찰 명령부터 제시.
- Level 3: 원인과 해결 명령을 단계별 제공.

튜터가 지켜야 할 규칙:

- 사용자가 물어봐도 `internal_summary`, `expected_solution`을 Level 3 전에는 직접 노출하지 않는다.
- hallucination 방지를 위해 컨텍스트에 없는 리소스 이름을 새로 지어내지 않는다.
- 로그에 근거가 있으면 “현재 이벤트에서는 ...가 보입니다”처럼 관찰 근거를 밝힌다.
- 컨텍스트 수집 실패 시 실패 사실을 숨기지 않고, 사용자가 직접 확인할 관찰 질문으로 전환한다.

구현 위치:

- 기존 변경: `backend/app/ai/tutor_service.py`
- 기존 변경: `ai-data/prompt_engine.py`
- 기존 변경: `ai-data/prompts/socratic_tutor.md`
- 새 파일: `backend/app/models.py`에 `TutorMessage` 모델 추가

## RAG 저장소 개편

현재 `ai-data/knowledge-base`에는 Kubernetes troubleshooting 문서가 있다. 여기에 실제 클라우드 장애 로그와 사후 분석 자료를 넣기 위한 구조를 추가한다.

권장 디렉터리:

```text
ai-data/
  knowledge-base/
    troubleshooting/
    commands/
    incident-logs/
      eks/
      gke/
      aks/
      generic-k8s/
    postmortems/
    runbooks/
```

장애 로그 문서 포맷:

```markdown
---
title: EKS OOMKilled checkout-api incident
platform: eks
fault_type: oom_killed
difficulty: intermediate
signals:
  - OOMKilled
  - memory limit
  - restart_count
resolution:
  - memory limit increase
  - memory leak investigation
---

# 증상

...

# 원본 로그 일부

```text
Last State: Terminated
Reason: OOMKilled
Exit Code: 137
```

# 진단 흐름

...

# 해결

...

# 튜터링 질문 예시

- Pod가 재시작된 이유를 어디서 확인할 수 있을까요?
- limit와 실제 사용량 사이에 어떤 관계가 있나요?
```

RAG metadata에 반드시 넣을 값:

- `source`
- `platform`
- `fault_type`
- `difficulty`
- `signals`
- `resolution`
- `created_at`

`RAGService.search_knowledge()`는 다음 필터를 받을 수 있게 확장한다.

```python
def search_knowledge(
    self,
    query: str,
    top_k: int = 3,
    min_similarity: float | None = None,
    filters: dict | None = None,
) -> list[RetrievedDocument]:
    ...
```

튜터 검색 쿼리는 단순 사용자 질문만 쓰지 말고 런타임 신호를 섞는다.

```text
fault_type=service_selector_mismatch
symptoms=Service Endpoints empty, Pods Running, selector mismatch
question=왜 웹 요청이 Pod로 안 가나요?
```

## 데이터 모델 변경

현재 `Mission`은 정적 미션 테이블이다. 개편 후에는 정적 미션을 템플릿처럼 유지하거나 제거하고, 실제 실행 단위는 `GeneratedScenario`가 맡는다.

### GeneratedScenario

```python
class GeneratedScenario(Base):
    __tablename__ = "generated_scenarios"

    id: Mapped[uuid.UUID]
    user_id: Mapped[uuid.UUID]
    difficulty: Mapped[str]
    title: Mapped[str]
    student_brief: Mapped[str]
    internal_summary: Mapped[str]
    fault_type: Mapped[str]
    scenario_json: Mapped[dict]
    chaos_plan_json: Mapped[dict]
    validation_json: Mapped[dict]
    status: Mapped[str]  # generated | running | completed | failed | rejected
    safety_review: Mapped[dict | None]
    created_at: Mapped[datetime]
```

### MissionAttempt 변경

`MissionAttempt`에 다음 필드를 추가한다.

```python
attempt_type: Mapped[str]  # static_mission | ai_scenario
scenario_id: Mapped[uuid.UUID | None]
runtime_context_snapshot: Mapped[dict | None]
last_validation_result: Mapped[dict | None]
```

기존 4개 미션 attempt는 `attempt_type="static_mission"`과 `mission_id`를 사용한다. AI 문제 attempt는 `attempt_type="ai_scenario"`와 `scenario_id`를 사용한다.

무결성 규칙:

- `attempt_type="static_mission"`이면 `mission_id`는 필수, `scenario_id`는 null
- `attempt_type="ai_scenario"`이면 `scenario_id`는 필수, `mission_id`는 null 또는 참조용 값
- 한 사용자는 동시에 하나의 `in_progress` attempt만 가질 수 있다

### ValidationRule

```python
class ValidationRule(Base):
    __tablename__ = "validation_rules"

    id: Mapped[uuid.UUID]
    scenario_id: Mapped[uuid.UUID]
    name: Mapped[str]
    rule_type: Mapped[str]  # promql | k8s
    query: Mapped[str]
    stability_seconds: Mapped[int]
    is_required: Mapped[bool]
    guard_status: Mapped[str]  # accepted | rejected
    guard_reason: Mapped[str | None]
```

### TutorMessage

```python
class TutorMessage(Base):
    __tablename__ = "tutor_messages"

    id: Mapped[uuid.UUID]
    attempt_id: Mapped[uuid.UUID]
    role: Mapped[str]  # user | assistant | system
    message: Mapped[str]
    hint_level: Mapped[int]
    context_snapshot: Mapped[dict | None]
    sources: Mapped[dict | None]
    created_at: Mapped[datetime]
```

## API 변경

### 기존 기본 미션 API 유지

기존 API는 그대로 유지한다.

```http
GET /api/missions/
POST /api/missions/start
GET /api/missions/status
POST /api/missions/check
POST /api/missions/abandon
POST /api/missions/hint
```

이 API들은 현재 구현된 4개 고정 미션 전용으로 사용한다. 기존 프론트의 미션 카드, 잠금 해제, 점수 계산 흐름은 깨지지 않아야 한다.

### AI 시나리오 생성

```http
POST /api/scenarios/generate
```

Request:

```json
{
  "difficulty": "intermediate",
  "preferred_fault_types": ["service_selector_mismatch", "oom_killed"],
  "randomize": true
}
```

Response:

```json
{
  "scenario_id": "...",
  "title": "...",
  "difficulty": "intermediate",
  "student_brief": "...",
  "time_limit_seconds": 1500,
  "safety_status": "accepted"
}
```

### AI 시나리오 시작

```http
POST /api/scenarios/{scenario_id}/start
```

실행 흐름:

1. 진행 중인 attempt가 있는지 확인
2. 사용자 namespace 준비
3. `ChaosPlan` 실행
4. `MissionAttempt` 생성
5. 검증 rule 저장
6. 시작 상태 반환

### AI 랜덤 문제 바로 시작

```http
POST /api/scenarios/start-random
```

Request:

```json
{
  "difficulty": "beginner"
}
```

이 API는 생성과 시작을 한 번에 수행한다. 프론트에서는 `AI 문제 더 풀기`에서 난이도를 선택한 뒤 바로 시작하는 UX에 사용한다.

### 현재 AI 문제 검증

```http
POST /api/scenarios/current/check
```

기존 `/api/missions/check`는 기본 4개 미션 전용으로 유지한다. AI 문제는 `/api/scenarios/current/check`를 사용한다. 공통 내부 로직은 `MissionOrchestrator` 또는 `AttemptService`로 묶을 수 있지만, 외부 API 경로는 분리해서 프론트와 테스트의 의미를 명확히 한다.

### 튜터 채팅

```http
POST /api/chat/
```

기존 API는 유지하되 응답 필드를 확장한다.

```json
{
  "response": "...",
  "hint_level": 1,
  "mission_name": "...",
  "sources": [
    {
      "source": "incident-logs/eks/oomkilled.md",
      "similarity": 0.82
    }
  ],
  "observations_used": [
    "checkout-svc has 0 ready endpoints",
    "checkout-api pod is Running"
  ]
}
```

## 시나리오 시작 전체 플로우

```text
User clicks "AI 문제 더 풀기"
  |
  v
User selects difficulty
  |
  v
POST /api/scenarios/start-random
  |
  v
ScenarioAgentService.generate()
  |
  v
Structured JSON validation
  |
  v
ChaosPlanCompiler.compile()
  |
  v
ValidationRuleService.guard_and_store()
  |
  v
K8sSetupService.setup_user_namespace()
  |
  v
ChaosExecutor.inject_plan()
  |
  v
MissionAttempt created
  |
  v
Frontend shows student_brief + terminal + tutor
```

## 검증 플로우

```text
User clicks Check
  |
  v
ValidationRuleService.load_rules(attempt.scenario_id)
  |
  v
For each PromQL rule:
  - replace {{namespace}} with user namespace
  - run Prometheus query/query_range
  - require truthy result for stability_seconds
  |
  v
For each K8s rule:
  - inspect namespaced resource
  |
  v
All required rules pass?
  |
  +--> yes: mark completed, cleanup chaos, score
  |
  +--> no: return retry message with non-spoiling reason
```

검증 실패 메시지는 정답을 드러내면 안 된다.

좋은 예:

```text
아직 정상화 조건을 만족하지 못했습니다. 서비스가 실제 Pod endpoint를 가지고 있는지 다시 확인해 주세요.
```

나쁜 예:

```text
checkout-svc selector를 app=checkout-api로 바꾸면 됩니다.
```

## Prometheus 자동 입력 구현 옵션

### 옵션 A: DB 저장 후 Prometheus API query

추천하는 1차 구현이다.

장점:

- 사용자별 동적 시나리오에 적합
- Prometheus 설정 reload 불필요
- 실패 시 rollback이 쉽다
- read-only Prometheus 컨테이너 설정과 충돌하지 않는다

구현:

- `validation_rules` 테이블에 PromQL 저장
- `PrometheusValidationService`가 rule을 읽어 `/api/v1/query` 호출
- `stability_seconds`가 있으면 `/api/v1/query_range` 또는 여러 번 샘플링

### 옵션 B: generated_rules.yml 생성 후 reload

Prometheus UI에서 동적 rule을 직접 보고 싶다면 2차로 구현한다.

필요 변경:

```yaml
# infra/monitoring/prometheus.yml
rule_files:
  - /etc/prometheus/recording_rules.yml
  - /etc/prometheus/alert_rules.yml
  - /etc/prometheus/generated_rules.yml
```

```yaml
# docker-compose.yml
prometheus:
  command:
    - --config.file=/etc/prometheus/prometheus.yml
    - --storage.tsdb.path=/prometheus
    - --storage.tsdb.retention.time=7d
    - --web.enable-lifecycle
  volumes:
    - ./infra/monitoring/generated_rules.yml:/etc/prometheus/generated_rules.yml
```

백엔드가 파일을 갱신할 수 있으려면 별도 volume을 쓰거나, Prometheus rule manager sidecar를 둔다. 현재 compose는 monitoring 파일을 read-only로 mount하므로 그대로는 백엔드가 rule file을 쓸 수 없다.

## 난이도 정책

### Beginner

- 단일 리소스 장애
- 증상이 명확함
- 해결이 1~2개 명령으로 가능
- 예: ImagePullBackOff, Service selector mismatch

제한:

- latency 500ms 이하
- stress chaos 사용하지 않음
- multi-service 장애 금지

### Intermediate

- Pod는 정상처럼 보이지만 트래픽/리소스 연결이 깨짐
- 2~3개 관찰 명령 필요
- 예: OOMKilled, readiness probe 실패, endpoint 없음

제한:

- 사용자 namespace 내 2개 리소스까지 변경
- validation rule 2개까지

### Advanced

- 복합 장애 가능
- Prometheus/Loki 지표와 로그를 함께 봐야 함
- 예: network latency + readiness probe 부재, configmap misconfig + rollout 실패

제한:

- 사용자 namespace 내 4개 리소스까지 변경
- Chaos Mesh duration 최대 30분
- CPU/memory stress는 명시된 limit 이하

### Expert

- 실제 운영 장애 사후 분석에 가까운 시나리오
- 다중 증상, 거짓 단서 포함 가능
- 단, 해결 불가능하거나 과도하게 파괴적인 장애는 금지

제한:

- cluster-scoped resource 변경 금지
- node 장애, PVC 삭제, secret 삭제는 1차 구현에서 금지

## 안전장치

AI 생성 결과에 대해 반드시 다음 검사를 한다.

- JSON Schema 검증
- fault type allowlist 검증
- namespace placeholder 검증
- resource name 패턴 검증: `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`
- patch path allowlist 검증
- Chaos Mesh kind allowlist 검증
- duration 상한 검증
- memory/cpu stress 상한 검증
- PromQL guard 검증
- rollback plan 존재 여부 검증
- 시나리오 dry-run 검증

Kubernetes 적용 전 가능하면 server-side dry-run을 사용한다.

```text
kubectl apply --dry-run=server
```

Python Kubernetes client에서는 create/patch 호출 시 dry-run 옵션을 먼저 지원하는 별도 검증 함수를 둔다.

## LLM 사용 방식

OpenAI를 사용할 경우 구조화 출력이 필요하다. `Scenario Generator Agent`와 `Validation Rule Generator Agent`는 자유 텍스트가 아니라 JSON Schema 기반 응답을 사용한다.

환경 변수:

```env
AI_BACKEND=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
SCENARIO_MODEL=gpt-4o-mini
TUTOR_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
```

현재 `ai-data/rag_service.py`는 `text-embedding-ada-002`를 사용한다. 개편 시 `text-embedding-3-small` 또는 설정 기반 모델로 바꾸는 것이 좋다.

Mock 모드는 유지한다.

- 로컬 개발/테스트에서 LLM 없이 결정적 시나리오 생성
- 난이도별 fixture JSON 사용
- 테스트에서 snapshot 비교 가능

## 프론트엔드 변경

현재 미션 목록 화면은 유지하고, 기본 4개 미션 카드 아래에 `AI 문제 더 풀기` 영역을 추가한다.

필요 화면:

- 기존 4개 기본 미션 카드
- 기본 미션 진행/완료/잠금 상태
- `AI 문제 더 풀기` 버튼 또는 패널
- AI 문제 난이도 선택: Beginner, Intermediate, Advanced, Expert
- AI 랜덤 시나리오 시작 버튼
- 현재 AI 시나리오 요약
- 제한 시간/점수/힌트 수
- 터미널
- AI 튜터 채팅
- 검증 버튼
- 실패 시 “다시 관찰하기” 중심 피드백
- 완료 시 원인/해결/사용자 명령 흐름/추천 복습 문서 표시

화면 배치:

```text
Mission Page
  |
  +-- 기본 미션
  |     +-- Level 1 사라진 웹페이지
  |     +-- Level 2 터져버린 쇼핑몰
  |     +-- Level 3 끊어진 연결고리
  |     +-- Level 4 좀비 서버의 습격
  |
  +-- AI 문제 더 풀기
        +-- 난이도 선택
        +-- 시작 버튼
        +-- 최근 AI 문제 기록
```

주의:

- `internal_summary`, `expected_solution`, `validation_json`은 프론트로 보내지 않는다.
- 완료 전에는 `student_brief`, 난이도, 제한 시간, 학습 목표 정도만 노출한다.
- 기본 미션과 AI 문제는 같은 터미널/튜터 UI를 공유하되, API 경로와 attempt type은 분리한다.

## 구현 순서

### Phase 1: 기존 미션 보존 + AI 문제 뼈대

1. `GeneratedScenario`, `ValidationRule`, `TutorMessage` 모델 추가
2. migration 또는 개발용 metadata create 반영
3. `ScenarioAgentService` Mock 구현
4. `/api/scenarios/start-random` 추가
5. `MissionAttempt.attempt_type`으로 기본 미션과 AI 문제 구분
6. 기존 `/api/missions/*` API와 4개 미션은 그대로 유지
7. 프론트 미션 목록 아래에 `AI 문제 더 풀기` 영역 추가

완료 기준:

- OpenAI 없이 난이도별 mock scenario가 생성되고 시작된다.
- 기존 4개 기본 미션은 기존과 동일하게 동작한다.
- AI 문제는 별도 `/api/scenarios/*` API로 시작된다.

### Phase 2: ChaosPlan 도입

1. `ChaosPlan` dataclass/Pydantic 모델 추가
2. `ChaosPlanCompiler` 구현
3. `ChaosMeshInjector.inject_plan()` 추가
4. 기존 `inject(chaos_type, namespace)`는 `ChaosPlan`으로 변환
5. rollback/cleanup을 attempt별로 DB에 저장

완료 기준:

- service selector mismatch, image pull error, memory stress를 `ChaosPlan`으로 실행/rollback한다.

### Phase 3: Prometheus 동적 검증

1. `ValidationRuleService` 구현
2. `PromQLGuard` 구현
3. `PrometheusValidationService.check_rules()` 추가
4. scenario validation JSON을 DB rule로 저장
5. `/api/scenarios/current/check`가 동적 rule 기반으로 동작

완료 기준:

- 시나리오마다 다른 PromQL 성공 조건으로 완료 여부를 판단한다.
- namespace 없는 PromQL은 저장 단계에서 거절된다.

### Phase 4: Runtime Context 기반 튜터

1. `RuntimeContextCollector` 구현
2. Kubernetes state collector 구현
3. CommandLog 요약 추가
4. Prometheus validation 결과 요약 추가
5. Loki collector 추가
6. `TutorService.get_hint()`가 runtime context를 prompt에 포함
7. `TutorMessage` 저장

완료 기준:

- 튜터가 사용자가 방금 실행한 명령과 현재 Kubernetes 상태를 참고해서 질문한다.
- 같은 힌트를 반복하지 않는다.

### Phase 5: RAG 장애 로그 저장소

1. `incident-logs/` 디렉터리 구조 추가
2. markdown frontmatter parser 추가
3. `RAGService` metadata filter 확장
4. ingestion script가 fault_type/difficulty/platform metadata 저장
5. 튜터가 runtime signals 기반으로 검색

완료 기준:

- OOMKilled, ImagePullBackOff, Service endpoint 없음 같은 실제 로그 문서를 검색해 튜터 응답에 반영한다.

### Phase 6: OpenAI 기반 생성 활성화

1. `Scenario Generator Agent` OpenAI 구현
2. JSON Schema structured output 적용
3. `Validation Rule Generator Agent` OpenAI 구현
4. safety review 실패 시 자동 재생성 1회
5. 실패하면 mock/fallback scenario 사용

완료 기준:

- 난이도별 랜덤 시나리오가 LLM으로 생성된다.
- 잘못된 시나리오는 실행 전에 거절된다.

### Phase 7: 운영 품질

1. 생성/실행/검증/튜터 응답 metric 추가
2. LLM token usage 저장
3. 시나리오 재현용 seed 저장
4. 관리자용 scenario review 화면 추가
5. rate limit 및 비용 제한 추가

완료 기준:

- 장애 시나리오 생성 실패율, 검증 실패 사유, 튜터 사용량을 관찰할 수 있다.

## 테스트 전략

### Unit

- `PromQLGuard`가 위험한 query를 거절하는지
- `ChaosPlanCompiler`가 allowlist 밖 patch를 거절하는지
- 난이도 정책이 fault parameter를 제한하는지
- `ScenarioAgentService` mock fixture가 schema를 만족하는지
- `RuntimeContextCollector`가 로그를 길이 제한 내로 요약하는지

### Integration

- 기존 `/api/missions` 목록/시작/검증 흐름이 깨지지 않는지
- `start-random` 호출 후 attempt 생성
- mock chaos + mock validation 완료
- Prometheus validation rule query 성공/실패
- command log가 tutor context에 포함
- RAG 검색 결과가 tutor response metadata에 포함

### E2E

- 사용자가 기존 4개 기본 미션을 볼 수 있다.
- 사용자가 `AI 문제 더 풀기`를 누른다.
- 사용자가 난이도를 선택한다.
- 랜덤 장애가 생성된다.
- 터미널에서 `kubectl get/describe/logs`로 관찰한다.
- 튜터가 로그 기반 질문을 한다.
- 사용자가 수정한다.
- Prometheus 검증을 통과한다.
- 점수가 기록된다.

## 주요 파일별 변경 요약

```text
backend/app/models.py
  GeneratedScenario, ValidationRule, TutorMessage 추가
  MissionAttempt에 scenario_id/context/result 필드 추가

backend/app/schemas.py
  ScenarioGenerateRequest, ScenarioResponse, ScenarioStartResponse 추가
  ChatResponse에 sources/observations_used 추가

backend/app/api/scenarios.py
  난이도 기반 생성/시작/검증 API 추가

backend/app/api/chat.py
  RuntimeContextCollector와 TutorMessage 저장 연결

backend/app/services/mission_service.py
  정적 mission_id와 동적 scenario_id 모두 지원

backend/app/services/chaos_plan.py
  ChaosPlan, ChaosStep, RollbackStep 모델
  ChaosPlanCompiler 구현

backend/app/services/chaos_injector.py
  inject_plan 추가

backend/app/services/validation_rule_service.py
  AI validation JSON 저장, 실행, 안정화 검사

backend/app/services/promql_guard.py
  PromQL namespace/syntax/allowlist 검사

backend/app/services/runtime_context.py
  K8s/Prometheus/Loki/CommandLog context 수집

backend/app/ai/scenario_agent.py
  Mock + OpenAI scenario generator

backend/app/ai/validation_agent.py
  Mock + OpenAI validation rule generator

backend/app/ai/tutor_service.py
  실제 runtime context + RAG source 반영

ai-data/rag_service.py
  metadata filter, embedding model 설정화, frontmatter 처리

ai-data/prompt_engine.py
  runtime context와 scenario context 추가

ai-data/prompts/socratic_tutor.md
  로그 기반 소크라테스 튜터 규칙 강화

frontend/src/components/Mission/*
  기존 4개 미션 목록 아래에 AI 문제 더 풀기 영역 추가
```

## 첫 PR 추천 범위

첫 PR에서 모든 것을 한 번에 바꾸지 않는다. 다음 정도가 가장 안정적이다.

1. DB 모델과 schema 추가
2. mock `ScenarioAgentService`
3. `MissionAttempt.attempt_type` 추가
4. `/api/scenarios/start-random` 추가
5. 프론트 기존 미션 목록 아래 `AI 문제 더 풀기` UI 추가
6. 난이도 선택 후 mock AI scenario 시작
7. 기존 4개 미션 회귀 테스트 추가

이렇게 하면 기존 4개 미션을 안정적으로 보존하면서, AI 문제 생성/시작 흐름만 옆에 붙여 먼저 검증할 수 있다.

## 최종 목표 사용자 경험

사용자는 먼저 기존 4개의 기본 미션으로 Kubernetes 장애 대응의 핵심 패턴을 익힌다.

기본 미션 목록 아래의 `AI 문제 더 풀기`를 누르면 난이도를 선택할 수 있다.

시스템은 AI로 새 장애를 만든다.

사용자는 자기 namespace의 터미널에서 실제 Kubernetes 상태를 조사한다.

AI 튜터는 사용자의 명령 이력, 현재 Pod/Event/Log/Prometheus 상태, RAG의 실제 장애 로그를 보고 질문한다.

사용자가 수정을 완료하면 시스템은 AI가 만든 검증 조건을 백엔드가 안전하게 검증한 PromQL/K8s rule로 확인한다.

완료 후에는 “무엇을 관찰했고, 어떤 판단을 했고, 왜 해결됐는지”를 리뷰로 보여준다. 이 리뷰까지 RAG에 저장하면 이후 비슷한 장애의 튜터링 품질이 계속 좋아진다.
