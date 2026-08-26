# 캡스톤디자인 II AI 2학기 구현 계획

> 프로젝트: AfterFail - 멀티 레이어 클라우드 인프라 기반 지능형 장애 대응 훈련 플랫폼
> 작성 기준: 2026-08-26, `dev` 브랜치 `36b1415`
> 원문 기준: `서버가왜죽었조_캡스톤디자인II_계획서.pdf`
> 대상 기간: 2026학년도 2학기, 16주, 2주 단위 8개 스프린트
> 담당 역할: AI Engineer, Cloud Architect
> 주 작업 범위: `ai-data/`, `backend/app/ai/`, AI가 사용하는 runtime context·chat/scenario 연동

## 0. 이 문서의 사용법

이 문서는 AI 담당자 또는 AI 코딩 에이전트가 작업 ID 단위로 바로 구현할 수 있는 실행 명세다.

1. 한 번에 하나의 `AI-xx` 작업만 구현한다.
2. 검색·튜터·시나리오 생성·평가를 한 PR에 섞지 않는다.
3. 환경별 동작을 prompt 문구만으로 보장하지 않는다. metadata filter, schema validation, backend allowlist를 함께 사용한다.
4. LLM 결과만으로 장애 복구와 점수를 확정하지 않는다. 기계적 validator가 최종 기준이다.
5. 기존 Qdrant, OpenAI/Gemini client, LangChain splitter를 재사용한다. 새 vector DB, agent framework, orchestration framework를 추가하지 않는다.
6. 외부 API가 필요한 테스트와 offline test를 분리한다. 기본 test suite는 API key와 Qdrant server 없이 실행 가능해야 한다.
7. 정확도·힌트 준수율·환경 혼입률·응답 시간·token을 수치로 검증하지 않은 prompt 변경은 완료로 처리하지 않는다.
8. 사용자 질문, 명령 출력, 로그에서 secret과 개인정보를 제거한 뒤 외부 LLM에 보낸다.

AI 전달 프롬프트:

```text
docs/ai-capstone2-semester-plan.md를 읽고 [작업 ID]만 구현해라.
현재 production caller와 테스트를 먼저 확인하고, Kubernetes 기존 동작을 보존하면서 인수 조건을 만족시켜라.
environment metadata filter와 출력 schema 검증을 prompt 지시로 대체하지 마라.
변경 파일, 사용한 평가 데이터, 정확도/지연 결과, 남은 backend/frontend 의존성을 마지막에 보고해라.
```

---

## 1. AI 최종 책임 범위

PDF 계획서와 현재 팀 역할을 기준으로 AI 담당은 다음을 책임진다.

- Kubernetes 중심 지식베이스를 Docker와 Linux까지 확장한다.
- 문서에 environment, fault type, source, version metadata를 저장한다.
- 선택 environment와 현재 장애 상태를 이용한 metadata-filtered RAG를 구현한다.
- semantic retrieval과 간단한 keyword reranking을 결합한 hybrid retrieval을 구현한다.
- 환경별 소크라테스식 힌트 레벨 0~3을 일관되게 제공한다.
- 현재 sandbox 상태, 최근 명령, metrics/logs를 활용하되 정답을 직접 노출하지 않는다.
- environment와 난이도에 맞는 AI 장애 시나리오 후보를 생성한다.
- 생성 결과를 schema·allowlist·안전성·관찰 가능성으로 검증하고 최적 후보를 선택한다.
- AI 완료 판정은 mechanical validator의 보조 설명으로 제공한다.
- 검색 정확도, hint leakage, scenario validity, latency, token/cost를 평가·관측한다.

### 범위 기준

- 필수 environment: `kubernetes | docker | linux`.
- Application/DB knowledge와 scenario는 현재 공식 범위에서 제외한다.
- 8주차에 세 환경 RAG/시나리오 기반이 안정화되고 backend가 application sandbox 계약을 제공할 때만 확장한다.
- 멀티 에이전트 시스템은 만들지 않는다. 현재 Tutor, Scenario, Validation 세 역할이면 충분하다.

---

## 2. 현재 AI 기준선

### 2.1 이미 구현된 기반

- `AITutorEngine`: prompt + RAG + OpenAI-compatible chat completion.
- `RAGService`: Qdrant collection, chunking, embedding, vector search.
- OpenAI/Gemini backend 선택.
- fault type metadata와 matching/general filter.
- 217개 수준의 기존 Kubernetes knowledge chunk ingestion 경험.
- 소크라테스식 hint level 0~3.
- TutorMessage DB 저장과 이전 질문 5개 복원.
- Kubernetes RuntimeContext: Pod, Deployment, Service, Events, Prometheus, 최근 명령.
- ScenarioAgent: 난이도별 mock fixture, OpenAI/Gemini JSON 생성, 후보 점수.
- ChaosPlanCompiler와 validation guard로 AI 출력 제한.
- ValidationAgent: Kubernetes 상태 기반 LLM 판정.
- Qdrant가 비어 있을 때 startup auto ingestion.

### 2.2 현재 knowledge base

현재 문서는 사실상 Kubernetes 전용이다.

- Kubernetes debugging, pod states, kubectl commands.
- CrashLoopBackOff, ImagePullBackOff, OOMKilled, Pending Pod, Service misconfig.
- Chaos Mesh, Prometheus, resilience pattern, incident playbook.
- Docker/Linux 전용 troubleshooting 문서는 없다.
- 실제 운영 장애 로그를 담는 `incident-logs/`는 미구성이다.

### 2.3 핵심 결손

| 우선순위 | 현재 상태 | 영향 |
|---|---|---|
| P0 | RAG metadata에 environment가 없음 | Docker/Linux 질문에 K8s 문서 혼입 |
| P0 | ScenarioGenerationInput에 environment가 없음 | DB에는 docker로 저장해도 K8s scenario 생성 |
| P0 | ValidationAgent가 mechanical false를 true로 뒤집을 수 있음 | LLM 오판으로 점수 부여 가능 |
| P1 | `TutorService._call_engine()`이 message만 반환 | sources, token usage, observations 유실 |
| P1 | RuntimeContext와 prompt가 K8s 필드에 고정 | Docker/Linux 상태 사용 불가 |
| P1 | scenario prompt와 902줄 fixture가 K8s 전용 | 환경별 fault 생성 불가 |
| P1 | ingestion point ID가 매번 random UUID | 재적재 시 중복·stale chunk 발생 |
| P1 | embedding dimension 변경 시 collection을 자동 삭제 | 운영 지식 전체 유실 위험 |
| P1 | startup은 collection이 비어 있을 때만 ingestion | 문서 변경이 collection에 반영되지 않음 |
| P1 | retrieval 품질 평가 dataset/metric 없음 | top-k와 threshold 근거 없음 |
| P2 | `ai-data/config.py`와 backend settings가 중복·기본값 불일치 | 모델·embedding 설정 drift |
| P2 | `sys.path`와 `os.environ` mutation으로 backend 연결 | 테스트·초기화 순서 취약 |
| P2 | `ai-data/requirements.txt`에 legacy chromadb 존재 | 실제 Qdrant stack과 불일치 |
| P2 | tests 상당수가 실행형 demo이고 실제 API key를 요구 | CI 회귀 탐지 부족 |
| P2 | LLM 오류 문자열에 내부 exception이 포함될 수 있음 | 사용자에게 내부 정보 노출 |
| P2 | prompt injection/redaction test 없음 | retrieved doc/명령 출력 공격 가능 |

### 2.4 현재 호출 경로의 정보 유실

```text
POST /api/chat
  -> chat.py: mission/scenario에서 name, level, chaos_type만 조회
  -> TutorService.get_hint
  -> RuntimeContextCollector (VALIDATION_BACKEND=k8s일 때만)
  -> AITutorEngine.get_response
     -> RAGService.search_knowledge(fault_type)
     -> TutorResponse(message, sources, token_usage)
  -> TutorService가 response.message만 반환
  -> ChatResponse의 sources/observations_used는 비어 있음
```

2학기에는 environment와 근거가 이 경로 끝까지 보존되어야 한다.

### 2.5 현재 테스트 상태

- `ai-data/tests/test_qdrant_rag.py`는 pytest 형식이지만 RAGService 생성 시 실제 embedding API key가 필요해 완전 offline이 아니다.
- 여러 `test_*.py`가 assertion test보다 console demo 역할을 한다.
- 환경 필터, stable ingestion, hint leakage, scenario schema, prompt injection 평가가 없다.
- production에서 사용하지 않는 `llm_client.py`와 legacy demo가 유지되고 있다.

---

## 3. 2학기 AI 완료 정의

### 3.1 튜터 완료 흐름

1. backend가 active attempt의 environment, fault type, sandbox scope를 전달한다.
2. environment collector가 현재 상태와 최근 명령을 공통 observation schema로 만든다.
3. 질문과 fault type으로 Qdrant를 검색하되 environment/general 문서만 허용한다.
4. 상위 semantic 결과를 keyword·authority로 rerank한다.
5. hint level과 environment에 맞는 prompt를 생성한다.
6. LLM 응답을 생성하고 금지된 직접 정답·잘못된 환경 명령을 검사한다.
7. message, sources, observations_used, token usage, latency를 backend에 반환한다.
8. 실패 시 내부 exception 대신 안전한 fallback 응답을 제공한다.

### 3.2 시나리오 완료 흐름

1. environment, difficulty, 최근 fault, allowed fault type을 입력받는다.
2. 같은 environment 후보 3개를 생성하거나 같은 environment fixture로 fallback한다.
3. Pydantic/schema로 필수 필드와 environment를 검증한다.
4. backend allowlist로 컴파일 가능한 declarative fault만 허용한다.
5. 안전성, 관찰 가능성, 복구 가능성, 최근 중복, 난이도로 점수화한다.
6. reject 사유와 후보 점수를 기록하고 최적 후보를 반환한다.

### 3.3 품질 목표

| 지표 | 목표 |
|---|---:|
| Retrieval Recall@5 | 환경별 eval set 85% 이상 |
| Environment contamination | 1% 미만, ideally 0 |
| Hint level violation | level 0~2 direct solution leakage 5% 미만 |
| Scenario schema validity | 99% 이상 |
| Scenario environment match | 100% |
| Scenario backend compile success | 95% 이상 |
| Unsafe scenario acceptance | 0 |
| Tutor response time | 공식 목표 1.5초 측정, p50/p95 별도 보고 |
| AI error safe fallback | 100% |

외부 LLM latency 때문에 1.5초를 항상 보장할 수 없으면 결과를 숨기지 않고 model/provider별 p50/p95와 병목을 보고한다.

### 3.4 하지 않을 것

- environment를 질문 문자열에만 넣고 metadata filter를 생략하지 않는다.
- 검색 결과를 무제한 prompt에 넣지 않는다.
- 사용자 namespace, token, Secret, 전체 env를 그대로 외부 LLM에 보내지 않는다.
- LLM이 생성한 shell command를 직접 실행하지 않는다.
- 새로운 vector DB나 agent framework를 추가하지 않는다.
- K8s prompt를 단어 치환만 해 Docker/Linux용으로 재사용하지 않는다.
- 평가 dataset 없이 top-k, threshold, temperature를 감으로 바꾸지 않는다.

---

## 4. AI 내부 계약

### AI-C-01 Environment와 fault taxonomy

공통 environment:

```python
EnvironmentId = Literal["kubernetes", "docker", "linux"]
```

초기 fault type:

| 환경 | fault type |
|---|---|
| Kubernetes | 기존 image_pull_error, crash_loop, oom_killed, service_selector_mismatch, probe_failure 등 |
| Docker | container_network_disconnect, volume_mount_error, container_oom, container_cpu_throttle |
| Linux | linux_oom, disk_io_stress, zombie_process, orphan_process, service_failure |

- taxonomy는 AI와 backend가 같은 파일을 직접 import하지 않아도 값이 일치해야 한다.
- source of truth는 backend allowlist/OpenAPI 문서다.
- AI eval dataset과 knowledge metadata도 이 값을 사용한다.

### AI-C-02 Knowledge document metadata

모든 원문 Document metadata:

```json
{
  "source_id": "docker-network-troubleshooting",
  "source": "07-docker/network-troubleshooting.md",
  "title": "Docker Network Troubleshooting",
  "environments": ["docker"],
  "fault_types": ["container_network_disconnect"],
  "content_type": "troubleshooting",
  "authority": 0.9,
  "version": "2026-08-26",
  "updated_at": "2026-08-26",
  "language": "ko"
}
```

chunk metadata 추가:

```json
{
  "chunk_index": 3,
  "content_hash": "sha256..."
}
```

- 여러 환경 공통 문서는 `environments: ["general"]`.
- mapping이 없는 문서를 general로 자동 간주하지 않는다. ingestion validation error로 보고한다.

### AI-C-03 Retrieval API

```python
search_knowledge(
    query: str,
    environment: str,
    fault_type: str | None,
    top_k: int = 5,
) -> list[RetrievedDocument]
```

Qdrant filter:

```text
environment in [requested_environment, general]
AND fault_type in [requested_fault_type, general]  # fault가 있을 때
```

반환 source에는 source_id, title, source, similarity, environment, fault_types를 포함한다.

### AI-C-04 공통 TrainingContext

```python
@dataclass
class TrainingContext:
    environment: str
    attempt_id: str
    mission_name: str
    difficulty_or_level: str
    fault_type: str
    scope_label: str
    recent_commands: list[dict]
    observations: dict
    metrics: dict
    logs: list[str]
```

- `scope_label`은 사용자에게 보여줄 수 있는 값만 포함한다.
- prompt model은 `pod_status/pod_logs/recent_events` 같은 K8s 전용 필드를 제거하고 observations로 일반화한다.

### AI-C-05 TutorResult

`backend/app/ai/tutor_service.py`가 반환할 값:

```python
@dataclass
class TutorResult:
    message: str
    hint_level: int
    environment: str
    sources: list[dict]
    observations_used: list[str]
    token_usage: dict
    latency_ms: float
    fallback_used: bool
```

`api/chat.py`는 이를 `ChatResponse`로 그대로 매핑한다.

### AI-C-06 ScenarioGenerationInput

```python
@dataclass
class ScenarioGenerationInput:
    environment: str
    difficulty: str
    scope_placeholder: str
    recent_fault_types: list[str]
    allowed_fault_types: list[str]
```

candidate 필수 필드:

```json
{
  "environment":"docker",
  "title":"...",
  "difficulty":"beginner",
  "student_brief":"...",
  "internal_summary":"...",
  "learning_objectives":[],
  "fault":{"type":"container_network_disconnect","parameters":{}},
  "observability":{"symptoms":[],"recommended_signals":[]},
  "validation":{"rules":[]},
  "scoring":{"base_score":100,"hint_penalty":5,"time_limit_seconds":1200}
}
```

- arbitrary command/script 필드를 허용하지 않는다.
- backend compiler가 known fault type과 parameters를 실제 action으로 변환한다.

### AI-C-07 Validation advisory

```python
ValidationJudgment(
    resolved: bool,
    reason: str,
    confidence: float,
    evidence: list[str],
)
```

- LLM judgment는 `last_validation_result` 설명용이다.
- mechanical rule이 false면 LLM resolved=true여도 attempt를 완료하지 않는다.

---

## 5. 목표 AI 구조

### 5.1 유지할 파일

| 파일 | 역할 |
|---|---|
| `ai-data/ingest.py` | 문서 로드·metadata validation |
| `ai-data/rag_service.py` | Qdrant ingestion/retrieval/rerank |
| `ai-data/prompt_engine.py` | 환경·hint level prompt |
| `ai-data/ai_engine.py` | retrieval + prompt + LLM orchestration |
| `backend/app/ai/tutor_service.py` | FastAPI/DB/runtime context adapter |
| `backend/app/ai/scenario_agent.py` | scenario generation/parse/score |
| `backend/app/ai/validation_agent.py` | advisory validation |

### 5.2 신규 최소 파일

| 파일 | 역할 |
|---|---|
| `ai-data/evals/retrieval_cases.jsonl` | 검색 정답 set |
| `ai-data/evals/tutor_cases.jsonl` | hint/environment 준수 set |
| `ai-data/evals/scenario_cases.jsonl` | scenario validity set |
| `ai-data/evals/run_evals.py` | stdlib + 현재 모듈 기반 eval runner |
| `ai-data/tests/fakes.py` | fake embeddings/LLM |
| `ai-data/knowledge-base/07-docker/*.md` | Docker 지식 |
| `ai-data/knowledge-base/08-linux/*.md` | Linux 지식 |

fixture를 code 902줄 안에 계속 추가하지 않는다. 환경별 fixture data가 커지면 `ai-data/fixtures/scenarios/{environment}.json`으로 이동한다.

### 5.3 정리할 legacy

- production에서 사용하지 않는 `llm_client.py`는 demo가 모두 새 client 경로로 이동한 뒤 삭제하거나 examples로 격리한다.
- `ai-data/requirements.txt`의 chromadb를 제거하고 Qdrant requirements와 통합한다.
- console demo는 pytest 수집 대상과 분리해 `examples/`로 이동한다.
- 디렉터리명 `ai-data` 대규모 rename은 이번 학기 필수 작업이 아니다. 핵심 기능 안정화 뒤 결정한다.

---

## 6. 스프린트별 구현 계획

## Sprint 0 - 1~2주차: taxonomy, 설정, offline 품질 기준

### AI-00 환경·fault taxonomy 확정

협의 대상: backend 담당.

구현/문서:

- Kubernetes/Docker/Linux allowed fault type 표를 확정한다.
- 각 fault의 learning objective, observable signals, allowed recovery action, mechanical validator를 연결한다.
- Application/DB 제외 여부를 명시한다.
- taxonomy version `v1`을 eval metadata에 기록한다.

완료 조건:

- AI scenario가 생성할 수 있는 fault마다 backend compiler/injector/validator 담당 이슈가 있다.
- backend가 구현하지 않은 fault는 allowed list에 없다.

### AI-01 설정 경로 정리

수정 파일:

- `ai-data/config.py`
- `backend/app/core/config.py`
- `backend/app/ai/tutor_service.py`
- requirements 파일

구현 지시:

- backend adapter가 `os.environ`을 실행 중 mutation하지 않고 명시적 settings 객체를 AI engine에 전달한다.
- model, embedding model, timeout, top_k, threshold default를 한 경로에서 주입한다.
- `ai-data/config.py` standalone default와 backend settings의 값이 다르지 않게 한다.
- legacy chromadb dependency를 제거한다.
- API key가 없는 mock/offline mode에서 RAGService가 fake/no-op 경로로 테스트 가능해야 한다.
- production error에 API key 존재 여부 이상의 값을 출력하지 않는다.

인수 조건:

- OpenAI/Gemini/mock 설정 matrix unit test.
- backend import 순서에 따라 model 값이 바뀌지 않는다.
- `pip install -r` 대상이 실제 production stack과 일치한다.

### AI-02 offline test와 eval runner

신규/수정 파일:

- `ai-data/tests/fakes.py`
- pytest config
- `ai-data/evals/run_evals.py`
- 기존 tests/examples 정리

구현 지시:

- deterministic fake embedding을 제공한다.
- fake chat completion은 입력별 고정 JSON/텍스트를 반환한다.
- 기본 pytest는 API key, network, Qdrant server 없이 실행한다.
- 실제 OpenAI/Gemini/Qdrant test는 `integration` marker로 분리한다.
- console 출력 demo는 pytest assertion test로 오인되지 않게 examples로 이동한다.

인수 조건:

- `python -m pytest -q` offline green.
- retrieval/filter/parse test가 실제 돈을 사용하지 않는다.
- eval runner는 JSON summary와 process exit code를 반환한다.

---

## Sprint 1 - 3~4주차: 멀티 환경 knowledge base와 안전한 ingestion

### AI-03 metadata schema와 loader

수정 파일:

- `ai-data/ingest.py`
- `ai-data/scripts/ingest_knowledge.py`
- tests

구현 지시:

- path substring 기반 FAULT_TYPE_TAGS를 유지하되 environment metadata를 명시한다.
- 각 문서 front matter 또는 중앙 manifest 중 하나를 source of truth로 사용한다. 최소 변경은 중앙 manifest다.
- source_id, title, environments, fault_types, authority, version 필수를 검증한다.
- mapping 없는 파일을 silent general로 넣지 않는다.
- chunk마다 chunk_index/content_hash를 붙인다.
- content가 비어 있거나 지나치게 큰 문서는 reject/경고한다.

인수 조건:

- 기존 K8s 문서 전부 valid metadata.
- 잘못된 environment/fault/source_id duplicate test 실패.
- loader 결과 수와 source별 chunk 수가 보고된다.

### AI-04 Docker knowledge base

신규 문서 최소 범위:

1. container lifecycle와 exit code.
2. `docker ps/inspect/logs/stats` 조사법.
3. bridge network, disconnect, DNS/port 문제.
4. volume/bind mount 오류와 권한.
5. container OOM/CPU throttle/resource limit.
6. 안전한 복구 playbook.

각 문서 요구:

- symptoms -> observations -> hypotheses -> safe commands -> recovery validation 구조.
- 정답 command만 나열하지 않고 hint level에서 사용할 개념 설명 포함.
- source와 작성/갱신 날짜 명시.
- environment=docker와 fault_types 태그.
- host Docker socket/privileged 권장 금지 문구.

완료 조건:

- Docker eval 질문 최소 20개.
- 각 필수 Docker fault마다 관련 문서 1개 이상.

### AI-05 Linux knowledge base

신규 문서 최소 범위:

1. process state, zombie/orphan.
2. cgroup/container OOM과 OOM-Killer 관찰.
3. disk usage와 disk I/O saturation.
4. memory/CPU/load 조사.
5. service/log 조사.
6. network socket 조사.
7. 안전한 복구 playbook.

주의:

- host kernel 전체에 영향을 주는 명령을 해결책으로 제시하지 않는다.
- sandbox에서 실제 제공하지 않는 systemd/dmesg 기능을 단정하지 않는다.
- backend Linux image capability와 문서 command를 대조한다.

완료 조건:

- Linux eval 질문 최소 20개.
- 각 필수 Linux fault마다 관련 문서 1개 이상.

### AI-06 versioned idempotent ingestion

수정 파일:

- `ai-data/rag_service.py`
- `backend/app/services/qdrant_init.py`
- tests

구현 지시:

- point ID를 `uuid5(source_id + chunk_index + content_hash)`로 안정화한다.
- collection 이름을 versioned 예: `afterfail_knowledge_v2`로 둔다.
- dimension mismatch 시 운영 collection을 즉시 삭제하지 않는다. 새 collection 생성 -> ingestion -> 검증 -> alias 전환 순서로 처리한다.
- source version 변경 시 stale point를 제거한다.
- collection 비어 있음뿐 아니라 manifest/content hash 변경을 감지한다.
- startup 전체 ingestion이 API startup을 장시간 막지 않게 background/admin command 정책을 정한다.
- ingestion report에 added/updated/deleted/unchanged를 기록한다.

인수 조건:

- 같은 문서 두 번 ingestion 후 point 수가 증가하지 않는다.
- 한 문서 수정 후 해당 source chunk만 교체된다.
- 실패한 새 collection 때문에 기존 alias가 사라지지 않는다.

---

## Sprint 2 - 5~6주차: environment-filtered hybrid RAG

### AI-07 environment + fault filter

수정 파일:

- `ai-data/rag_service.py`
- `ai-data/ai_engine.py`
- tests

구현 지시:

- `search_knowledge(query, environment, fault_type, top_k)`로 변경한다.
- Qdrant must filter로 environment/general과 fault/general을 동시에 적용한다.
- environment가 없거나 invalid하면 검색하지 않고 명시적 오류를 반환한다.
- retrieved source metadata를 보존한다.
- top_k와 threshold에서 `or` default를 사용하지 않아 0 같은 명시 값이 무시되지 않게 한다.

인수 조건:

- Docker query 결과에 Kubernetes-only 문서 0개.
- general 문서는 세 환경에서 검색 가능.
- fault type filter와 environment filter가 AND로 적용된다.

### AI-08 dependency 없는 hybrid reranking

수정 파일: `rag_service.py`, tests.

구현 지시:

- vector top 20을 가져온다.
- 한국어/영문/명령 token을 간단히 정규화한다.
- query와 title/content keyword overlap을 계산한다.
- authority metadata를 작은 가중치로 반영한다.
- 초기 공식:

```text
final_score = 0.75 * semantic_score
            + 0.15 * keyword_overlap
            + 0.10 * authority
```

- 최종 top_k를 반환하고 semantic/final score를 eval log에 남긴다.
- BM25/FastEmbed 같은 새 dependency는 eval에서 현재 방식이 부족하다고 증명될 때만 추가한다.

인수 조건:

- exact command/fault keyword 문서가 무관한 일반 문서보다 위에 온다.
- 동일 입력 순서가 deterministic하다.
- reranking off/on Recall@5를 비교한다.

### AI-09 retrieval eval

신규 `ai-data/evals/retrieval_cases.jsonl`.

case 구조:

```json
{"id":"docker-net-01","environment":"docker","fault_type":"container_network_disconnect","query":"컨테이너는 떠 있는데 통신이 안 됩니다","expected_source_ids":["docker-network-troubleshooting"]}
```

dataset:

- 환경별 최소 20개, 총 60개 이상.
- 한국어 70%, 영문/명령형 30%.
- 일반 질문, 애매한 질문, 잘못된 환경 용어 포함.

보고 지표:

- Recall@1/3/5.
- MRR.
- environment contamination.
- empty retrieval rate.
- latency p50/p95.

인수 조건:

- Recall@5 85% 이상.
- contamination 1% 미만.
- threshold/top_k 값을 report 근거로 고정.

---

## Sprint 3 - 7~8주차: 환경 인지형 소크라테스 튜터

### AI-10 공통 TrainingContext와 prompt 일반화

수정 파일:

- `ai-data/prompt_engine.py`
- `ai-data/ai_engine.py`
- `backend/app/ai/tutor_service.py`
- `backend/app/services/runtime_context.py` 연동

구현 지시:

- MissionContext/SystemContext/UserContext의 K8s 고정 필드를 TrainingContext로 교체하거나 호환 adapter를 둔다.
- prompt에 environment, mission, observations, recent commands, retrieved docs를 명시적 구역으로 분리한다.
- retrieved docs와 runtime logs를 untrusted data로 표시한다.
- environment별 command vocabulary를 넣는다.
- hint level 규칙:
  - 0: 관찰 질문, command/root cause 금지.
  - 1: 조사 영역 지목, exact recovery 금지.
  - 2: 진단 command 허용, 복구 command 금지.
  - 3: root cause와 복구 step/command 허용.
- 현재 prompt 문서와 code의 level 설명 불일치를 하나로 통일한다.

인수 조건:

- Docker level 2 응답에 kubectl recovery command가 없다.
- Linux level 0에 root cause가 직접 노출되지 않는다.
- level 3은 backend command policy 안의 복구법만 제안한다.

### AI-11 TutorResult 정보 보존

수정 파일:

- `ai-data/ai_engine.py`
- `backend/app/ai/tutor_service.py`
- `backend/app/api/chat.py`
- `backend/app/schemas.py`

구현 지시:

- AITutorEngine 응답의 sources/token_usage를 adapter가 버리지 않게 한다.
- 실제 prompt에 포함한 observation key를 observations_used로 반환한다.
- source는 title/source_id/path/environment/similarity만 노출하고 local absolute filepath는 노출하지 않는다.
- 내부 exception text를 사용자 message로 반환하지 않는다.
- TutorMessage에는 최종 message를 저장하고 metadata 저장 필요성은 DB migration을 backend 담당과 협의한다.

인수 조건:

- ChatResponse에 sources/observations_used가 실제 값으로 온다.
- local disk path, API key, raw stack trace 노출 0건.
- RAG 실패 시 message는 안전한 fallback이고 sources는 빈 배열.

### AI-12 prompt injection과 redaction

수정 파일:

- prompt/engine/tutor adapter
- tests/eval cases

구현 지시:

- user question, command output, logs, retrieved docs를 데이터 경계 delimiter 안에 넣는다.
- "이전 지시 무시", prompt 탈취, secret 출력 요청을 따르지 않게 system instruction을 강화한다.
- Bearer token, common secret/password patterns, Kubernetes Secret data, environment variables를 redact한다.
- 최대 question/log/doc length와 total context token budget을 둔다.
- prompt 전체를 production log에 남기지 않는다.

인수 조건:

- adversarial case 20개에서 secret/prompt leakage 0.
- 너무 긴 로그가 truncate되어도 핵심 observation summary는 유지.

### AI-13 8주차 튜터 품질 게이트

평가 dataset `tutor_cases.jsonl` 최소 60개.

자동/수동 평가:

- environment command correctness.
- hint level leakage.
- retrieved source relevance.
- observation grounding.
- unsupported claim.
- Korean clarity.

gate:

- environment mismatch 0.
- level 0~2 direct solution leakage 5% 미만.
- unsupported dangerous command 0.
- P0/P1이면 Application/DB 확장 금지.

---

## Sprint 4 - 9~10주차: 멀티 환경 AI 시나리오 생성

### AI-14 environment-aware input과 fixtures

수정 파일:

- `backend/app/ai/scenario_agent.py`
- `backend/app/services/scenario_service.py`
- 필요 시 `ai-data/fixtures/scenarios/*.json`
- tests

구현 지시:

- ScenarioGenerationInput에 environment를 추가한다.
- ScenarioService가 request environment를 agent에 전달한다.
- fixture를 Kubernetes/Docker/Linux로 분리한다.
- generation failure는 같은 environment fixture로만 fallback한다.
- 최근 fault 중복 회피도 environment 안에서 계산한다.

인수 조건:

- Docker 요청 candidate 100% environment=docker.
- Docker API 실패 fallback도 Docker fixture.
- allowed list가 빈 경우 다른 환경 fixture를 사용하지 않고 명시적 오류.

### AI-15 환경별 scenario prompt와 schema

수정 파일:

- `ai-data/prompts/scenario_gen.md`
- scenario agent parser/schema

구현 지시:

- 공통 schema와 환경별 섹션을 둔다.
- namespace/pod command 대신 declarative fault parameters만 생성한다.
- environment별 allowed fault/observation/validation rule type을 prompt에 넣는다.
- exact JSON schema 또는 Pydantic model로 parse한다.
- unknown field를 무조건 버리지 말고 reject reason에 기록한다.
- min/max time_limit, score, hint penalty를 검증한다.
- student_brief에 정답/내부 요약/주입 방법이 포함되지 않게 검사한다.

인수 조건:

- invalid JSON, wrong environment, unknown fault, missing validation, answer leakage가 reject.
- valid fixture 100% parse/compile.

### AI-16 후보 scoring과 다양성

초기 score:

```text
base 40
+20 recent fault와 다름
+15 difficulty 일치
+10 observable signals 2개 이상
+10 backend compile 가능
+5 source-backed learning objective
-30 unsafe parameter
-20 recent 3회 안에 같은 fault
-20 student brief answer leakage
```

- 후보 3개 전체 reject reason을 기록한다.
- 단순 `max(score)` 전에 safety/schema rejected를 제외한다.
- randomize=true여도 같은 seed/eval mode에서는 deterministic 선택을 지원한다.
- LLM 호출 실패를 mock fallback 성공으로 숨기지 말고 fallback_used metric을 남긴다.

인수 조건:

- 최근 중복보다 새 fault가 우선한다.
- unsafe candidate가 높은 다른 점수를 가져도 선택되지 않는다.
- 같은 eval seed 결과가 재현된다.

### AI-17 scenario eval

`scenario_cases.jsonl` 환경별·난이도별 최소 5개, 총 60개 이상.

지표:

- JSON/schema validity.
- environment match.
- allowed fault match.
- backend compiler success.
- observation availability.
- validation rule executability.
- student brief answer leakage.
- generation latency/token.

목표:

- schema validity 99%.
- environment match 100%.
- compiler success 95%.
- unsafe accepted 0.

---

## Sprint 5 - 11~12주차: 상황 인지와 안전한 AI 평가

### AI-18 환경별 runtime observation 사용

협업 파일:

- `backend/app/services/runtime_context.py`
- `backend/app/ai/tutor_service.py`
- prompt formatting/tests

환경별 observation 최소값:

| 환경 | observation |
|---|---|
| Kubernetes | pod/deployment/service/event/readiness |
| Docker | container state/exit/resource/network/volume/log summary |
| Linux | process/memory/disk/load/socket/service/log summary |

구현 지시:

- collector는 backend 담당이 안전한 sandbox target에서 수집한다.
- AI는 common observation schema만 사용한다.
- collection timeout/partial failure를 prompt에 명확히 표시한다.
- 질문과 무관한 raw 상태 전체를 보내지 않고 필요한 summary를 선택한다.
- observations_used는 실제 포함한 key만 반환한다.

인수 조건:

- environment별 grounding test.
- observation unavailable 상황에서 없는 값을 지어내지 않는다.
- command output 속 secret redaction.

### AI-19 ValidationAgent advisory 전환

수정 파일:

- `backend/app/ai/validation_agent.py`
- `backend/app/services/scenario_service.py` 협업
- tests/evals

구현 지시:

- K8s 전용 `_collect_k8s_state` 중복을 RuntimeContext collector로 대체한다.
- environment별 observation을 받는다.
- output에 evidence list를 추가한다.
- LLM resolved=true가 mechanical false를 override하지 못하게 한다.
- confidence parsing을 0~1 범위로 clamp하고 invalid JSON은 safe false/advisory error.
- mock validator도 unrelated healthy resource 하나만 보고 true를 반환하지 않게 fault-specific evidence를 사용한다.

인수 조건:

- unrelated healthy deployment로 장애 완료 판정하지 않는다.
- LLM false positive가 score를 부여하지 않는다.
- reason에 내부 정답을 학생 응답으로 노출하지 않는다.

### AI-20 대화 memory와 보존

수정 파일:

- `TutorService`
- TutorMessage 관련 migration은 backend 담당과 협업

구현 지시:

- attempt별 최근 5개 user/assistant pair를 시간순으로 읽는다.
- 현재는 user 질문만 읽는 동작을 개선하되 context token budget을 지킨다.
- 완료/포기 후 새 attempt에 이전 대화를 섞지 않는다.
- 30일 retention cleanup을 backend job으로 연결한다.
- analytics에는 원문 대신 count/token/latency만 사용한다.

인수 조건:

- 같은 attempt에서 반복 질문을 인지한다.
- 다른 attempt/user 대화 혼입 0.
- retention test와 cleanup 문서.

---

## Sprint 6 - 13~14주차: 성능·비용·관측·회귀 평가

### AI-21 latency 최적화

수정 파일:

- TutorService/AITutorEngine/RAGService
- metrics

구현 지시:

- runtime collection과 RAG retrieval을 가능한 범위에서 병렬 실행한다.
- sync embedding/LLM call은 `asyncio.to_thread` 또는 executor로 event loop를 막지 않는다.
- context collection, RAG, LLM에 독립 timeout을 둔다.
- RAG 실패 시 RAG 없는 tutor fallback, runtime 실패 시 관측 없음 fallback을 구분한다.
- 동일 attempt/fault의 general retrieval은 짧은 TTL cache를 검토하되 측정 후 필요할 때만 적용한다.
- prompt에 넣는 chunk 수/글자/token 상한을 둔다.

측정:

- context_ms, retrieval_ms, rerank_ms, llm_ms, total_ms.
- provider/model/environment/hint level별 p50/p95.

인수 조건:

- event loop blocking test.
- timeout 후 late response가 저장되지 않는다.
- 공식 1.5초 목표에 대한 실제 수치 보고.

### AI-22 token·cost 제한

설정:

- max question chars.
- max command/log chars.
- max retrieved chunks.
- max context tokens.
- max completion tokens.
- per-user/attempt chat rate limit은 backend 담당과 협업.

구현 지시:

- token_usage와 estimated cost를 내부 metric/log에 저장한다.
- 사용자 ID를 metrics label로 사용하지 않는다.
- LLM retry는 rate limit/connection에만 제한적으로 적용한다.
- scenario generation 3후보를 위해 불필요한 다중 API call을 하지 않는다.
- provider 장애 시 같은 request를 무제한 fallback 호출하지 않는다.

인수 조건:

- 긴 입력에서 token budget 초과 없음.
- retry 상한 test.
- 월/시연 예상 비용 report.

### AI-23 관측 메트릭

추가 metric:

- tutor requests/result/fallback by provider/environment.
- retrieval latency/result count/empty rate.
- retrieval contamination count.
- prompt/response token.
- scenario generation validity/reject/fallback.
- validation advisory agreement with mechanical result.
- Qdrant ingestion added/updated/deleted/error.

금지 label:

- user ID, namespace, raw question, source full path, scenario title.

### AI-24 자동 평가 회귀 기준

CI/offline 필수:

1. metadata validation.
2. stable ingestion ID.
3. environment/fault filter.
4. hybrid rerank deterministic.
5. hint prompt rules.
6. redaction/prompt injection.
7. TutorResult source preservation.
8. scenario schema/environment/fallback.
9. validation advisory non-override.
10. token/timeout/retry.

nightly/manual integration:

- Qdrant server.
- OpenAI small sample.
- Gemini small sample.
- real runtime observations.

merge gate:

- retrieval/tutor/scenario eval이 기준보다 3%p 이상 하락하면 실패.
- environment contamination 또는 unsafe acceptance 1건이라도 있으면 실패.

---

## Sprint 7 - 15~16주차: 실제 통합·멘토 검증·제출

### AI-25 세 환경 end-to-end

환경별 다음 흐름을 최소 5회 실행한다.

```text
scenario 생성
-> backend compiler/injector
-> runtime observation
-> tutor 0~3단계
-> mechanical validation
-> advisory explanation
-> source/latency/token 기록
```

검수:

- environment 혼입.
- 실제 없는 command 제안.
- level별 정답 leakage.
- source relevance.
- scenario 실행/복구 가능성.
- latency/token.

### AI-26 AWS 멘토 시나리오 검토

AWS 멘토에게 환경별 최소 3개 시나리오를 검토받는다.

평가 항목:

- 실무 빈도/현실성.
- 관찰 signal의 적절성.
- 초보자 난이도.
- 안전한 복구 가능성.
- 잘못된 학습 유도 여부.

피드백은 taxonomy, knowledge, fixture, eval expected에 반영한다. 단일 prompt 예시만 수정하고 eval을 생략하지 않는다.

### AI-27 최종 성능·품질 보고

보고 표:

- 환경별 Recall@1/3/5, MRR.
- contamination.
- hint violation.
- scenario validity/compiler success.
- advisory/mechanical agreement.
- tutor p50/p95 latency.
- prompt/completion token 평균.
- provider별 fallback/error.
- 예상 비용.

### AI-28 문서와 시연

갱신 파일:

- `ai-data/README.md`
- `ai-data/knowledge-base/README.md`
- `backend/CLAUDE.md` AI 절
- `.env.example`
- eval report

필수 문서:

- environment/fault taxonomy.
- knowledge metadata schema와 새 문서 추가법.
- versioned ingestion/alias rollback.
- retrieval filter/rerank 공식.
- prompt hint level 규칙.
- scenario schema와 reject 사유.
- offline/integration eval 실행법.
- provider/model/embedding migration.
- privacy/redaction/retention.
- Application/DB 후속 범위.

최종 완료 조건:

- 세 환경 end-to-end 성공.
- Recall@5 85% 이상.
- environment mismatch/unsafe acceptance 0.
- hint leakage 목표 충족.
- source/observation이 API 끝까지 전달.
- mechanical validator만 점수 확정.
- offline CI green, provider integration sample 통과.
- 품질/성능/비용 report 제출.

---

## 7. 작업 의존성

```text
AI-00 taxonomy
  -> AI-01 config
  -> AI-02 offline test
      -> AI-03 metadata
      -> AI-04 Docker KB
      -> AI-05 Linux KB
      -> AI-06 versioned ingestion
          -> AI-07 filter
          -> AI-08 rerank
          -> AI-09 retrieval eval
              -> AI-10 prompt/context
              -> AI-11 TutorResult
              -> AI-12 security
              -> AI-13 quality gate
                  -> AI-14~17 scenario
                  -> AI-18~20 context/validation/memory
                      -> AI-21~24 hardening
                          -> AI-25~28 release
```

---

## 8. 팀 간 인계점

### 백엔드 담당자에게 요구할 것

- environment별 allowed fault types.
- safe sandbox TrainingContext.
- mechanical validation result/evidence.
- scenario compiler reject reason.
- chat rate limit과 TutorMessage retention job.
- AI metrics endpoint/registry.

### 백엔드 담당자에게 제공할 것

- environment-aware ScenarioCandidate.
- TutorResult(message/sources/observations/token/latency).
- ValidationJudgment advisory.
- taxonomy/eval version.
- provider fallback과 오류 code.

### 프론트엔드 담당자에게 제공할 것

- sources 항목의 안전한 표시 필드.
- observations_used 문자열 목록.
- fallback/error 상태.
- environment와 hint level.
- 느린 응답/취소 시 동작 계약.

---

## 9. PR 권장안

| PR | 브랜치 예시 | 작업 |
|---|---|---|
| 1 | `feature/ai-baseline` | AI-00~02 |
| 2 | `feature/multi-env-knowledge` | AI-03~05 |
| 3 | `feature/versioned-qdrant` | AI-06 |
| 4 | `feature/cross-layer-rag` | AI-07~09 |
| 5 | `feature/cross-layer-tutor` | AI-10~13 |
| 6 | `feature/multi-env-scenario` | AI-14~17 |
| 7 | `feature/runtime-ai-context` | AI-18~20 |
| 8 | `feature/ai-hardening` | AI-21~24 |
| 9 | `feature/ai-release` | AI-25~28 |

---

## 10. Definition of Done

각 AI 변경:

- [ ] environment를 입력·metadata·출력에서 검증한다.
- [ ] offline test가 있다.
- [ ] eval dataset으로 변경 전후를 비교했다.
- [ ] retrieved source와 observation이 추적 가능하다.
- [ ] hint level 금지사항을 검사했다.
- [ ] secret/PII redaction을 확인했다.
- [ ] timeout/retry/fallback 상한이 있다.
- [ ] token/latency를 측정한다.
- [ ] 내부 exception을 사용자에게 노출하지 않는다.
- [ ] mechanical validator를 override하지 않는다.

환경 완료:

- [ ] knowledge 문서와 metadata.
- [ ] retrieval eval 20개 이상.
- [ ] environment contamination 0 또는 목표 이하.
- [ ] environment prompt/command test.
- [ ] scenario fixture와 generated candidate.
- [ ] backend compile success.
- [ ] runtime observation grounding.
- [ ] TutorResult source 전달.

---

## 11. 위험과 대응

| 위험 | 대응 |
|---|---|
| Docker/Linux 문서 부족 | 환경별 최소 fault 문서부터 작성하고 일반 클라우드 문서로 억지 fallback하지 않음 |
| 잘못된 문서 혼입 | environment + fault must filter와 contamination eval |
| embedding 변경으로 collection 손실 | versioned collection + alias cutover, 자동 delete 금지 |
| ingestion 중복 | stable UUID5와 content hash |
| prompt 정답 누설 | level별 eval과 answer leakage detector |
| LLM이 위험 command 생성 | declarative scenario schema + backend allowlist, prompt만 신뢰하지 않음 |
| LLM false-positive 채점 | advisory only, mechanical validator 최종 승인 |
| 1.5초 목표 미달 | 단계별 latency 측정, parallel retrieval/context, model별 수치 공개 |
| token 비용 증가 | context/chunk/completion budget과 metrics |
| provider 장애 | 제한된 retry와 safe mock/template fallback, fallback metric |
| 설정 drift | explicit settings 주입, os.environ mutation 제거 |
| demo가 test로 오인 | examples와 offline pytest 분리 |

---

## 12. 최종 산출물

- Kubernetes/Docker/Linux knowledge base와 metadata manifest.
- versioned/idempotent Qdrant ingestion과 rollback 가능한 alias.
- environment + fault filtered hybrid RAG.
- retrieval/tutor/scenario eval dataset과 runner.
- environment-aware 소크라테스식 prompt.
- sources/observations/token/latency를 보존하는 TutorResult.
- Docker/Linux AI scenario fixture·prompt·schema·scoring.
- 안전한 RuntimeContext 사용과 redaction.
- mechanical validation을 보조하는 ValidationAgent.
- provider별 품질·지연·비용 보고서.
- 실행·ingestion·평가·문서 추가 가이드.

AI 파트의 핵심 성공 기준은 답변을 그럴듯하게 만드는 것이 아니라, 선택한 환경과 실제 관측 상태에 근거한 문서를 검색하고, 힌트 수준을 지키며, 실행 가능하고 안전한 시나리오만 생성하는 것을 평가 수치로 증명하는 것이다.
