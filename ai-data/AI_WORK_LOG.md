# AI 작업 진행 기록

## AI-00 환경·fault taxonomy 확정

- 상태: 완료
- 작업일: 2026-08-27
- 작업 브랜치: `feature/ai-runner`
- Wave: Wave 0
- 선행 조건: 별도 선행 작업 없음. 코드 구현 없이 backend의 현재 compiler/injector/validator 계약을 확인함.
- 변경 파일:
  - `ai-data/docs/fault-taxonomy-v1.md`: 환경별 taxonomy, 학습 목표, 관측 신호, 허용 복구, mechanical validator와 backend 담당 작업 정리
  - `ai-data/evals/metadata.json`: eval taxonomy version `v1` 기록
- 결정:
  - Kubernetes canonical fault 15종만 현재 AI scenario 생성 허용
  - 기존 `pod_failure`, `memory_stress`, `service_misconfig`, `network_latency`는 legacy alias로 분류
  - Docker 4종과 Linux 5종은 taxonomy 후보로 확정했지만 backend 구현 전까지 생성 비활성
  - Application/DB는 `v1` 범위에서 제외
- 검증:
  - canonical compiler mapping 15종 확인
  - canonical injector handler mapping 15종 확인
  - canonical mechanical validator mapping 15종 확인
  - `python3 -m json.tool ai-data/evals/metadata.json` 통과
  - `git diff --check` 통과
- 테스트 제한: 로컬에 `backend/venv`와 시스템 Python backend 의존성이 없어 backend pytest는 실행하지 못함. 코드 변경은 없음.
- 평가 데이터 및 품질 수치: AI-00은 taxonomy 문서 작업이므로 retrieval 정확도·지연 평가는 해당 없음
- 남은 의존성:
  - Docker 활성화: BE-13 DockerChaosInjector, BE-14 DockerValidationService
  - Linux 활성화: BE-17 LinuxChaosInjector, BE-18 LinuxValidationService
  - backend allowed list에서 legacy alias와 canonical 생성 목록을 분리하는 후속 계약 정리 필요

## AI-01 설정 경로 정리

- 상태: 완료
- 작업일: 2026-08-27
- 작업 브랜치: `feature/ai-baseline`
- Wave: Wave 1
- 선행 조건 및 게이트:
  - PR #33 backend CI `47 passed, 1 warning`
  - `backend/app/schemas.py` environment 계약 확인
  - `backend/alembic` 확인
  - dev required checks 3종 확인
- 변경 파일:
  - `ai-data/config.py`: 불변 `AISettings`, standalone/backend 명시적 factory, provider별 model/embedding 설정
  - `ai-data/ai_engine.py`: settings 객체로 model/timeout/token/temperature와 RAG 설정 주입
  - `ai-data/rag_service.py`: settings 객체 사용, mock in-memory Qdrant와 offline embedding 경로, 명시적 0 설정 보존
  - `ai-data/prompt_engine.py`: production module import 시 암묵적 `.env` 로드 제거
  - `ai-data/scripts/ingest_knowledge.py`: `.env` 로드를 standalone CLI 경계로 이동
  - `backend/app/ai/tutor_service.py`: 실행 중 `os.environ` mutation 제거, backend Settings를 `AISettings`로 변환해 전달
  - `ai-data/requirements.txt`: 미사용 chromadb 제거, qdrant-client 반영
  - `ai-data/tests/test_config_matrix.py`: mock/OpenAI/Gemini/default/import-order 설정 test 7개
  - `ai-data/docs/backend-settings-handoff-ai-01.md`: backend 소유 설정 키 후속 작업 기록
- 테스트 및 검증:
  - config matrix 7개 직접 실행 통과
  - 변경 Python 파일 `compileall` 통과
  - TutorService `os.environ[...]` mutation 0건
  - engine/RAG 초기화 오류에 provider exception·API key 값 미노출
  - `git diff --check` 통과
- 평가 데이터 및 품질 수치: 설정 작업이므로 retrieval 정확도·LLM latency 평가는 해당 없음
- 제한:
  - 로컬 Python에 backend/AI dependency와 pytest가 없어 전체 pytest는 실행하지 못함
  - Python 3.14 임시 가상환경 설치는 `grpcio-tools` wheel build 호환 문제로 실패함. 프로젝트 기준 Python 3.11 CI에서 재검증 필요
  - Docker daemon이 실행 중이 아니어서 Python 3.11 container 검증은 수행하지 못함
  - backend core Settings의 추가 timeout/RAG 키와 qdrant startup 명시 주입은 백엔드 담당 후속 작업

## AI-02 오프라인 테스트와 평가 실행기

- 상태: 완료 — PR #39, merge commit `e99e831`
- 작업일: 2026-08-28
- 작업 브랜치: `feature/ai-offline-evals`
- Wave: Wave 1
- 변경:
  - deterministic fake embedding과 OpenAI 호환 fake chat client 추가
  - 기본 pytest를 API key, network, 외부 Qdrant 없이 실행 가능하게 구성
  - 외부 연동 smoke test를 `integration` marker로 분리
  - JSON parse, retrieval, environment filter 오프라인 평가 실행기 추가
- 검증:
  - AI pytest `33 passed, 3 deselected`
  - offline eval `3/3 passed`
- 후속: AI-03 metadata schema와 loader

## AI-03 knowledge metadata schema와 loader

- 상태: 완료 — PR #48, merge commit `5ce907c`
- 작업일: 2026-08-29
- 작업 브랜치: `feature/multi-env-knowledge`
- Wave: Wave 2
- 변경:
  - `knowledge-base/manifest.json`을 문서 metadata 단일 원본으로 추가
  - source ID, environment, fault type, authority, version 검증
  - 미등록·빈·과대 문서 거부와 chunk index/content hash 추적 추가
- 품질 수치:
  - Kubernetes 문서 17개, chunk 217개 manifest coverage 확인
- 검증:
  - AI pytest `41 passed, 3 deselected`
  - backend pytest `202 passed`
  - offline eval `4/4 passed`
- 후속: AI-04 Docker knowledge base

## AI-04 Docker knowledge base

- 상태: 완료 — PR #49, merge commit `b203385`
- 작업일: 2026-08-29
- 작업 브랜치: `feature/ai-docker-knowledge`
- Wave: Wave 2
- 변경:
  - lifecycle, 명령, network, storage, resource, 안전 복구 문서 6종 추가
  - backend Docker argv allowlist와 sandbox 경계에 맞춘 명령 예시 검증
  - Docker fault 4종 retrieval 질문 20개 추가
- 품질 수치: Docker Recall@5 `20/20 (100%)`
- 검증:
  - AI pytest `48 passed, 3 deselected`
  - backend pytest `202 passed`
  - offline eval `5/5 passed`
- 후속: AI-05 Linux knowledge base

## AI-05 Linux knowledge base

- 상태: 완료 — PR #50, merge commit `946869d`
- 작업일: 2026-08-29
- 작업 브랜치: `feature/ai-linux-knowledge`
- Wave: Wave 2
- 변경:
  - process, cgroup OOM, disk I/O, resource, service/log, socket, 안전 복구 문서 7종 추가
  - Linux fault 5종 metadata와 retrieval 질문 21개 추가
  - capability 기반 명령 안내와 host sandbox 안전 경계 검증
- 검증:
  - AI pytest `55 passed, 3 deselected`
  - backend pytest `202 passed`
  - offline eval `6/6 passed`
- 후속: BE-16 capability와 문서 명령 재검증 — 이후 BE-16~18이 dev에 머지됨

## AI-06 versioned idempotent Qdrant ingestion

- 상태: 완료 — PR #51, merge commit `015cc92`
- 작업일: 2026-08-29
- 작업 브랜치: `feature/versioned-qdrant`
- Wave: Wave 2
- 변경:
  - `uuid5(source_id + chunk_index + content_hash)` stable point ID 적용
  - source별 stale chunk 교체와 added/updated/deleted/unchanged report 추가
  - 기본 collection `afterfail_knowledge_v2`, dimension 불일치 시 기존 collection 보존
  - 검증된 collection의 원자적 alias 전환과 관리용 sync command 추가
- 검증:
  - AI pytest `61 passed, 3 deselected`
  - backend pytest `202 passed`
  - offline eval `6/6 passed`
- 남은 의존성: backend startup이 `needs_sync()`를 호출하도록 `qdrant_init.py` 후속 연동

## AI-07 environment + fault RAG filter

- 상태: 완료 — PR #63, merge commit `674996d`
- 작업일: 2026-08-31
- 작업 브랜치: `feature/cross-layer-rag`
- Wave: Wave 3
- 선행 조건:
  - BE-14/15 범위 게이트와 BE-16~21 dev 머지 확인
  - `RuntimeContextCollector.collect(environment, sandbox)` 계약 확인
- 변경:
  - environment/general과 fault/general을 Qdrant `must` 조건으로 AND 적용
  - 누락·잘못된 environment 명시적 거부, retrieval metadata 보존
  - TutorRequest에 environment 추가하되 기존 호출은 Kubernetes 기본값 유지
  - tutor service가 DB attempt environment와 서버 복원 sandbox를 collector/RAG에 전달
- 검증:
  - AI pytest `69 passed, 3 deselected`
  - backend pytest `363 passed`
  - offline eval `6/6 passed`
- 남은 의존성:
  - backend가 Docker/Linux environment capability에 `tutor` 노출
  - AI-10에서 공통 TrainingContext prompt로 observations 직접 반영

## AI-08 dependency 없는 hybrid RAG reranking

- 상태: 완료 — PR #64, merge commit `c4f8992`
- 작업일: 2026-08-31
- 작업 브랜치: `feature/ai-hybrid-reranking`
- Wave: Wave 3
- 변경:
  - environment/fault filter 이후 vector 후보 20개 조회
  - 한국어·영문·명령 token 정규화와 title/content keyword overlap 계산
  - `0.75 semantic + 0.15 keyword + 0.10 authority` 점수 적용
  - semantic/keyword/final score metadata와 deterministic tie-break 추가
  - `rerank=False` vector baseline 비교 경로 추가
- 품질 수치:
  - Docker 20문항 vector-only Recall@5 `1.000`
  - Docker 20문항 hybrid Recall@5 `1.000`
- 검증:
  - AI pytest `72 passed, 3 deselected`
  - backend pytest `363 passed`
  - offline eval `6/6 passed`
- 후속: AI-09 3개 환경 retrieval 정식 평가와 latency 보고

## AI-09 retrieval eval

- 상태: 완료 — PR #65
- 작업일: 2026-08-31
- 작업 브랜치: `feature/ai-retrieval-eval`
- Wave: Wave 3
- 변경:
  - `evals/retrieval_cases.jsonl`에 Kubernetes/Docker/Linux 각 20문항, 총 60문항 추가
  - 한국어 70%, 영문/명령형 30%와 일반·애매·타 환경 용어 질문 포함
  - Recall@1/3/5, MRR, environment contamination, empty retrieval, latency p50/p95 평가기 추가
  - 환경별 Recall@5 85%와 contamination 1% 미만을 자동 gate로 적용
  - mock ingestion의 불필요한 Gemini rate-limit 대기를 제거해 offline 평가 시간을 단축
- 품질 수치:
  - 전체 Recall@1/3/5: `0.6000 / 0.8333 / 0.9167`, MRR `0.7156`
  - Kubernetes Recall@5 `0.85`, Docker `0.90`, Linux `1.00`
  - environment contamination `0`, empty retrieval rate `0`
  - 전체 latency p50 `5.32ms`, p95 `10.55ms` (offline deterministic embedding)
  - 평가 근거로 `top_k=5`, candidate `20`, min similarity `0` 고정
- 검증:
  - AI pytest `76 passed, 3 deselected`
  - backend pytest `363 passed`
  - 기존 offline eval `6/6 passed`
- 후속: AI-10 공통 TrainingContext와 prompt 일반화

## AI-10 공통 TrainingContext와 prompt 일반화

- 상태: 완료
- 작업일: 2026-08-31
- 작업 브랜치: `feature/cross-layer-tutor`
- Wave: Wave 3
- 선행 조건:
  - AI-09 PR #65 dev 머지 확인
  - AI-07에서 확인한 BE-15 범위 결정과 BE-16~21 RuntimeContext 계약 유지 확인
- 변경:
  - Kubernetes/Docker/Linux 공통 `TrainingContext`를 추가하고 기존 context 호출 호환 adapter 유지
  - mission, observations/runtime logs, recent commands, retrieved docs, learner history를 명시적 구역으로 분리
  - 사용자 입력·관측값·로그·검색 문서를 untrusted data 경계로 표시
  - 환경별 command vocabulary와 hint level 0~3 규칙을 코드·시스템 prompt에서 통일
  - `TutorService`가 RuntimeContext의 공통 observations/metrics/logs를 K8s 전용 문자열로 축약하지 않고 전달
  - RAG 문서를 문자열 치환하지 않고 `TrainingContext.retrieved_docs`로 전달
- 인수 조건 검증:
  - Docker level 2 prompt에 Docker 진단 vocabulary만 포함하고 recovery command 금지
  - Linux level 0에서 root cause와 command 노출 금지
  - level 3 명령을 현재 환경 vocabulary와 backend command policy에 제한
- 검증:
  - AI pytest `80 passed, 3 deselected`
  - backend pytest `363 passed`
- 후속: AI-11 TutorResult 정보 보존

## AI-11 TutorResult 정보 보존

- 상태: 완료
- 작업일: 2026-08-31
- 작업 브랜치: `feature/cross-layer-tutor`
- Wave: Wave 3
- 선행 계약:
  - 백엔드 계약 PR #67을 먼저 머지해 `TutorSource`와 `ChatResponse` 메타데이터 필드 확장
- 변경:
  - `AITutorEngine`의 sources, observations_used, token_usage, latency, fallback 상태를 응답 끝까지 보존
  - source를 title/source_id/상대 path/environment/similarity만 포함하는 안전한 형태로 변환
  - prompt에 실제 포함된 observation/metric/log/recent command 키를 observations_used로 기록
  - RAG 또는 provider 실패 시 내부 exception을 숨기고 안전한 fallback과 빈 sources 반환
  - `TutorService`가 최종 message만 저장하되 API에는 전체 `TutorResult`를 반환
- 인수 조건 검증:
  - ChatResponse가 sources/observations_used/token_usage를 반환하도록 백엔드 계약 연결
  - 절대 로컬 경로와 raw exception/API key 문자열 노출 방지 테스트 추가
  - RAG 실패 시 `fallback_used=true`, `sources=[]` 확인
- 검증:
  - AI pytest `82 passed, 3 deselected`
  - backend pytest `364 passed`
- DB 결정:
  - TutorMessage에는 기존대로 최종 message만 저장하며 AI-11에서는 migration을 추가하지 않음
- 후속: AI-12 prompt injection과 redaction

## AI-12 prompt injection과 redaction

- 상태: 완료
- 작업일: 2026-08-31
- 작업 브랜치: `feature/cross-layer-tutor`
- Wave: Wave 3
- 선행 조건:
  - AI-11 PR #68 dev 머지와 TutorResult fallback 계약 확인
- 변경:
  - user question, observations, runtime logs, recent commands, retrieved docs를 각각 untrusted data 경계로 분리
  - raw 사용자 질문을 OpenAI user message로 중복 전송하던 경로 제거
  - Bearer/provider token, password/secret/API key, Kubernetes Secret data, 환경변수 재귀 redaction 추가
  - 모델 응답에도 동일 redaction을 적용해 출력 단계의 secret 반복 노출 차단
  - question 2,000자, observations 8,000자, logs 4,000자, commands 3,000자, docs 8,000자 제한
  - 전체 prompt를 약 9,000 token 상당의 36,000자 이내로 제한하고 observations를 문서·로그보다 우선 보존
  - prompt 전체를 production log에 기록하는 코드가 없음을 확인
- 보안 평가:
  - `evals/prompt_injection_cases.jsonl`에 한국어/영문 prompt 탈취, role 변경, secret 출력 요청 등 20개 추가
  - 20개 adversarial case에서 입력 secret 노출 0건
  - 모델 출력 secret 재노출 방지와 raw question 중복 전송 방지 검증
  - 장문 로그·문서가 truncate되어도 핵심 observation summary 유지 검증
- 검증:
  - AI pytest `105 passed, 3 deselected`
  - backend pytest `364 passed`
- 후속: AI-13 8주차 튜터 품질 게이트

## AI-13 8주차 튜터 품질 게이트

- 상태: 완료
- 작업일: 2026-08-31
- 작업 브랜치: `feature/cross-layer-tutor`
- Wave: Wave 3
- 선행 조건:
  - AI-10~12 공통 context, TutorResult, prompt injection 방어 dev 머지 확인
- 변경:
  - `evals/tutor_cases.jsonl`에 Kubernetes/Docker/Linux 각 20개, 총 60개 기준 응답 추가
  - 각 환경에서 hint level 0~3, 진단·복구 질문, 관측 신호와 기대 source를 포함
  - environment command correctness, hint leakage, source relevance, observation grounding, unsupported claim, dangerous command, Korean clarity 자동 평가기 추가
  - prompt의 environment/hint level 계약도 케이스마다 함께 검증
  - 실패 시 non-zero exit와 JSON report를 제공해 CI 품질 게이트로 사용 가능
- 평가 방식:
  - 외부 API 없이 재현 가능한 수동 검토 기준 응답(golden response)을 자동 채점
  - 실제 OpenAI/Gemini 응답은 릴리스 평가에서 동일 데이터셋의 response를 교체해 별도 측정
- 품질 수치:
  - environment mismatch `0`
  - level 0~2 direct solution leakage `0%`
  - unsupported dangerous command `0`
  - source relevance `100%`, observation grounding `100%`
  - unsupported claim `0%`, Korean clarity `100%`
  - Kubernetes/Docker/Linux 환경별 20/20 통과
- 범위 판정:
  - 튜터 품질 게이트는 통과했으나 backend 실행 계약이 없어 Application/DB는 후속 연구로 유지
- 검증:
  - AI pytest `109 passed, 3 deselected`
  - backend pytest `364 passed`
  - tutor offline eval `60/60 passed`
- 후속: AI-14 environment-aware scenario input과 fixtures

## AI-14 environment-aware scenario input과 fixtures

- 상태: 완료 — AI PR #75 + backend 경계 PR
- 작업일: 2026-09-01
- 작업 브랜치: `feature/multi-env-scenario`, `feature/be-scenario-environment-contract`
- Wave: Wave 3
- 선행 조건:
  - AI-13 PR #70 dev 머지와 Kubernetes/Docker/Linux 실행 fault allowlist 확인
- 변경:
  - `ScenarioGenerationInput.environment` 추가
  - Kubernetes/Docker/Linux fixture를 환경별·난이도별로 분리
  - LLM 요청에 environment를 전달하고 wrong-environment 응답을 거절
  - provider/parse 실패 시 요청과 같은 environment fixture로만 fallback
  - 빈 allowlist 또는 일치 fixture 부재 시 명시적 오류 반환
  - ScenarioService가 요청 environment와 해당 환경 allowlist를 agent에 전달
  - 최근 fault 중복 이력을 GeneratedScenario.environment 안에서만 조회
  - Docker/Linux fault type이 Kubernetes `pod_failure`로 fallback되지 않고 해당 injector에 그대로 전달
- 인수 조건 검증:
  - Docker 요청 candidate environment `100% docker`
  - Docker provider 실패 fallback environment `100% docker`
  - 세 환경의 빈 allowlist가 모두 명시적 오류
- 검증:
  - AI pytest `118 passed, 3 deselected`
  - backend pytest `511 passed, 4 deselected`
- 후속: AI-15 환경별 scenario prompt와 schema

## 백엔드 관측 handoff — AI-23 부분 구현

- 상태: 완료 (AI-23 전체 완료 아님)
- 작업일: 2026-09-01
- 작업 브랜치: `feature/ai-hardening`
- 요청 배경:
  - 백엔드 담당이 추가한 `AI_CALLS`, `AI_CALL_DURATION`, `AI_TOKENS` 연결
  - AI 소유 경로 `backend/app/ai/`에 남은 print 7건 제거
- 변경:
  - Tutor/Scenario/Validation LLM 호출을 provider와 purpose 저카디널리티 label로 계측
  - success/fallback 호출 수, 호출 시간, prompt/completion/total token 기록
  - user ID, namespace, prompt, response 본문은 metric label/value에 포함하지 않음
  - print 7건을 표준 logging의 warning/exception으로 전환
  - provider 실패 fallback도 result=fallback으로 기록
- 검증:
  - AI pytest `122 passed, 3 deselected`
  - backend pytest `511 passed, 4 deselected`
  - `backend/app/ai/` print 호출 `0건`
- 남은 AI-23 범위:
  - retrieval latency/result count/empty rate와 environment별 tutor result metric
