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
