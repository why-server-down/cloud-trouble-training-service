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
