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
