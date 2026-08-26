# AfterFail

카오스 엔지니어링 + AI 튜터 + 게이미피케이션 기반 DevOps 장애 대응 훈련 플랫폼 (캡스톤 디자인)

> **이 파일이 프로젝트 규칙의 단일 원본이다.** 어떤 AI 도구를 쓰든 이 파일을 먼저 읽는다.
> 루트 `CLAUDE.md`는 이 파일을 가리키는 포인터이며, 규칙을 바꿀 때는 여기만 수정한다.

## 핵심 메커니즘
1. Attack - Chaos Mesh가 사용자 Pod 공격 (고정 4개 미션 + AI 동적 생성)
2. Defend - 사용자가 kubectl로 장애 해결 (AI 튜터가 소크라테스식 힌트 제공)
3. Score - K8s API/Prometheus가 정상화 감지 → 점수 부여

## 캡스톤 로드맵

### 캡스톤 1 - Kubernetes 완성 (진행 중)
기존 4개 고정 미션을 튜토리얼로 유지하고, AI가 동적으로 장애를 생성하는 "AI 문제 더 풀기" 모드를 추가한다. 자세한 설계는 [agent.md](agent.md) 참고.

- 기존 4개 미션 튜토리얼 유지
- AI 장애 생성 모드 Phase 1~6 완료 (Phase 5는 부분 완료 - incident-logs 미구성)
- Grafana 패널 cAdvisor 수정 완료 (Docker Desktop container="" 필터)
- 검증 K8s fallback 추가 완료
- 미션 4 재설계 완료 (network_latency → Readiness Probe 실패로 구현)

### 캡스톤 2 - 멀티 환경 고도화 (진행 중)
K8s 전용 훈련을 다중 환경으로 확장한다. 환경은 **Kubernetes(기존) / Docker / Linux** 3종.

> **실행 명세 우선.** 2학기 구현은 담당별 계획서의 작업 ID 단위로 진행한다.
> 백엔드 [docs/backend-capstone2-semester-plan.md](docs/backend-capstone2-semester-plan.md) (`BE-00`~`BE-28`),
> 프론트 [docs/frontend-capstone2-semester-plan.md](docs/frontend-capstone2-semester-plan.md) (`FE-*`),
> AI [docs/ai-capstone2-semester-plan.md](docs/ai-capstone2-semester-plan.md).
> 이 파일과 계획서가 어긋나면 계획서가 기준이며, 이 파일을 갱신한다.

**Application/DB는 목업 한정.** 백엔드 `SUPPORTED_ENVIRONMENTS`에 등록하지 않고 sandbox·injector·validator·명령 정책을 제공하지 않는다. UI에서도 "개발 예정"이 아니라 **후속 연구**로 표기한다. 8주차 범위 게이트(BE-15) 통과 + 실행 계약 확정 시에만 별도 이슈로 승격.

| 단계 | 브랜치 | 작업 ID | 주차 | 상태 |
|---|---|---|---|---|
| 기반 | `feature/env-schema` | — | — | [x] environment 데이터 계층 관통 (PR #30) |
| 기반 | `feature/injector-refactor` | — | — | [x] 레지스트리 디스패치 전환 (PR #31) |
| 1 | `feature/backend-baseline` | BE-01~03 | 1–2 | [ ] 테스트 녹색화, Alembic 도입, API environment 필드 |
| 2 | `feature/env-sandbox` | BE-04, BE-07 | 3–4 | [ ] SandboxService, Quota/NetworkPolicy/RBAC, 세션 API |
| 3 | `feature/safe-terminal-exec` | BE-05, BE-06 | 3–4 | [ ] host shell 제거 → Pod exec, WS 소유권 검증 |
| 4 | `feature/env-runtime` | BE-08~10 | 5–6 | [ ] environment 기반 factory, 미션 잠금·seed, K8s 회귀 |
| 5 | `feature/docker-env` | BE-11~15 | 7–8 | [ ] DinD sandbox·injector·validator, 8주차 범위 게이트 |
| 6 | `feature/linux-env` | BE-16~18 | 9–10 | [ ] Linux sandbox·injector·validator |
| 7 | `feature/cross-layer-contracts` | BE-19~21 | 11–12 | [ ] RuntimeContext, AI 실행 계약, MTTR·analytics |
| 8 | `feature/backend-hardening` | BE-22~24 | 13–14 | [ ] 동시성·reconciliation, CORS·메트릭, 테스트 확대 |
| 9 | `feature/aws-migration` | BE-25 | 15–16 | [ ] EKS 보안 배포 (별도 트랙) |
| 10 | `feature/backend-release` | BE-26~28 | 15–16 | [ ] E2E·성능·문서 |

**실행/격리 설계:** K8s를 실행 기반으로 삼아 환경을 사용자 네임스페이스 안 샌드박스 Pod(kubernetes=toolbox+target, docker=DinD, linux=범용 Pod)로 제공하고, 터미널 명령을 호스트 subprocess가 아닌 **argv allowlist + Pod 내부 exec**로 실행한다. 실행 대상은 서버가 DB 세션에서 결정하며 클라이언트 값을 신뢰하지 않는다. 상세는 [agent.md](agent.md) "실행/격리 아키텍처" 참고.

**우선 해소 대상 (P0):** ① host `shell=True` 실행 ② WebSocket 세션 소유권 미검증 ③ environment가 세션·명령 실행까지 미연결 ④ active chaos ID가 프로세스 메모리에만 존재(재시작 시 정리 불가).

브랜치는 dev에서 기능별로 분기 → dev PR. 위 표의 순서를 따르되 5·6(Docker/Linux)은 4 머지 후 병렬 가능.

## 기술 스택
- Frontend: React (xterm.js 터미널, 채팅 UI, 환경 탭 UI)
- Backend: FastAPI, SQLAlchemy async, PostgreSQL
- AI: LangChain + OpenAI gpt-4o-mini / Google Gemini (소크라테스식 튜터, 시나리오 생성), Qdrant (RAG)
- Infra: Kubernetes, Chaos Mesh
- Monitoring: Prometheus, Grafana, Loki, Promtail, AlertManager

## 구현 현황 (2026-06-05 기준)

### 완료
- [x] 회원가입 / 로그인 (JWT)
- [x] 로그아웃 / 프로필 조회 API
- [x] 웹 터미널 (xterm.js + WebSocket, kubectl 전용)
- [x] 미션 시스템 (목록/시작/상태/완료/포기/힌트, 4개 레벨)
- [x] 점수 계산 (시간 감점 + 힌트 감점)
- [x] AI 튜터 채팅 API (Mock + OpenAI/Gemini 연동, K8s Pod 상태 실시간 반영)
- [x] RAG AI 엔진 (ai-data/ - LangChain + Qdrant + GPT/Gemini)
- [x] Chaos Mesh 연동 (로그인 시 사용자 네임스페이스 + nginx Pod 자동 생성)
- [x] K8s API 기반 실제 검증 (K8sValidationService)
- [x] Prometheus 기반 검증 (PrometheusValidationService)
- [x] 대시보드 / 리더보드 / 업적 시스템
- [x] 티어 시스템 (Bronze → Silver → Gold → Platinum → DevOps Master)
- [x] 모니터링 스택 (Prometheus + Grafana + Loki + Promtail + AlertManager)
- [x] Grafana cAdvisor 패널 수정 (container="" 필터, Docker Desktop 호환)
- [x] AI 튜터 Pod 상태 조회 datetime 정렬 버그 수정
- [x] 환경 탭 UI (Kubernetes / Docker / Linux / Application, 미개발 탭 WIP 화면)
  - 캡스톤2에서 `GET /api/environments` 가용성 기반으로 전환 예정. Application 탭은 목업/후속 연구 표기로 변경.
- [x] **AI 장애 생성 모드 Phase 1~3** (agent.md 기준)
  - GeneratedScenario / ValidationRule 모델 및 DB 마이그레이션
  - ScenarioAgent: Mock fixture (난이도별 4종) + OpenAI/Gemini 실제 생성
  - ChaosPlan / ChaosPlanCompiler (allowlist 안전장치)
  - ScenarioService (생성 → 주입 → 검증 → 포기 → 힌트 전체 오케스트레이션)
  - ValidationRuleService: PromQLGuard + k8s 타입 룰 + K8s 직접 검증 fallback
  - /api/scenarios/* 전체 엔드포인트 (start-random, status, current/check, current/abandon, current/hint, unlock-status)
  - ai-data/prompts/scenario_gen.md 시나리오 생성 시스템 프롬프트
  - 프론트엔드 AI Challenge Mode UI (잠금 해제 조건, 난이도 선택, 진행 상황 표시)
- [x] missions.py AI 시나리오 attempt 혼용 크래시 수정 (NoneType 방지)
- [x] scenario_agent.py mock fixture validation k8s 룰로 통일
- [x] 미션 4 재설계 (chaos_type=network_latency → Readiness Probe 실패 주입으로 구현)
- [x] **AI 장애 생성 모드 Phase 4** (agent.md 기준)
  - RuntimeContextCollector 구현 및 튜터 연결 완료 (K8s state + 이벤트 + Prometheus + 명령 이력)
  - TutorMessage DB 모델 및 저장 로직 구현 완료
- [x] **AI 장애 생성 모드 Phase 5 (부분 완료)**
  - RAG knowledge-base 구축 (troubleshooting/ 전용 문서 + 6개 권위 출처 문서)
  - fault_type 기반 RAG 필터링 구현 (ingest_knowledge.py + rag_service.py + ai_engine.py)
  - Qdrant 217개 청크 ingestion 완료, 채팅 API 연동 검증 완료
  - ai-data/ingest.py 공용 모듈 분리 (load_all_documents + FAULT_TYPE_TAGS)
  - 미완료: incident-logs/ 실제 운영 장애 로그 문서 미구성
- [x] **AI 장애 생성 모드 Phase 6** — validation_agent.py 구현 완료 (Mock + OpenAI/Gemini LLM 판정)
- [x] **Qdrant knowledge-base 자동 ingestion** — 서버 시작 시 컬렉션 비어있으면 자동 적재
  - AI_BACKEND=mock이거나 이미 문서 있으면 skip
  - backend/app/services/qdrant_init.py (auto_ingest_if_empty)
  - main.py lifespan에 통합

### 진행 중 (캡스톤 1)
- [ ] AI 장애 생성 모드 Phase 7 (운영 메트릭, 비용 제한, 시드 저장)
- [ ] Phase 5 미완료: incident-logs/ 실제 클라우드 장애 로그 문서 추가

### 진행 중 (캡스톤 2)
단계별 진행 상태는 위 "캡스톤 2" 로드맵 표를 기준으로 한다. 현재 기반 2건(env-schema, injector-refactor) 완료, 다음은 `feature/backend-baseline`(BE-01~03).

**백엔드 테스트 기준선 (2026-08-26 실측, `backend/` venv):**
```
python -m pytest -q  →  1 failed, 31 passed
```
- 실패 1건: `tests/test_command_validator.py::TestBlockedCommands::test_invalid_subcommand`
  (`kubectl create secret`이 허용됨 → 허용 여부를 미션 요구와 맞추고 resource/flag까지 제한)
- `pytest-asyncio==0.23.3`은 requirements·venv 모두에 설치되어 async 테스트가 실행된다.
  단 `pytest.ini`가 없어 `asyncio_mode`가 미명시 → BE-01에서 추가한다.
- 계획서 §2.2의 "28 passed / 4 failed / pytest-asyncio 미설치"는 다른 환경 기준 수치다.

## 팀 협업 & Git 규칙

3인(백엔드 / 프론트엔드 / AI)이 각자 계획서를 기준으로 **AI 자율 실행을 병렬로** 돌린다.
아래 규칙은 저장소 전체에 적용되며, 개인 전역 규칙(`~/.claude/CLAUDE.md`)과 충돌하면
**이 문서가 우선**한다. (예: 전역 "squash merge 기본"은 이 저장소에서 적용하지 않는다.)

> **실행을 시작하기 전에 [docs/parallel-execution-order.md](docs/parallel-execution-order.md)를 먼저 읽는다.**
> 세 계획서는 서로의 머지를 기다리도록 쓰여 있어서, 동시에 출발하면 프론트·AI가
> 존재하지 않는 API에 대고 구현하게 된다. 웨이브 게이트를 통과했는지 확인하고 시작한다.

### 1. 담당 분야와 소유 경로

| 담당 | 계획서 | 작업 ID | 소유 경로 (단독 수정 가능) |
|---|---|---|---|
| 백엔드 | [docs/backend-capstone2-semester-plan.md](docs/backend-capstone2-semester-plan.md) | `BE-xx` | `backend/app/api/`, `backend/app/services/`, `backend/app/core/`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/main.py`, `backend/tests/`, `backend/alembic/`, `infra/` |
| 프론트엔드 | [docs/frontend-capstone2-semester-plan.md](docs/frontend-capstone2-semester-plan.md) | `FE-xx` | `frontend/` 전체 |
| AI | [docs/ai-capstone2-semester-plan.md](docs/ai-capstone2-semester-plan.md) | `AI-xx` | `ai-data/` 전체, `backend/app/ai/` |

- **소유 경로 밖의 파일은 기본적으로 건드리지 않는다.** 자기 작업에 필요한 최소 범위만 수정한다.
- 남의 경로를 수정했다면 PR 본문에 이유와 영향 범위를 적는다 (승인을 기다리지는 않는다).

### 2. 공유 파일 (변경하면 반드시 알리기)

아래 파일은 3인 모두에게 영향을 주므로 **가능한 한 단독 PR로 분리**하고, 머지 직후 팀에 알린다.
승인을 기다릴 필요는 없지만, 알리지 않으면 다른 사람이 낡은 계약 위에서 작업하게 된다.

| 파일 | 주 소유 | 주의점 |
|---|---|---|
| `backend/app/schemas.py` | 백엔드 | API 계약. 변경 시 FE·AI가 즉시 dev 재동기화 필요 |
| `backend/app/models.py` + Alembic 리비전 | 백엔드 | DB 스키마. 동시에 두 개의 마이그레이션을 만들지 않는다 |
| `docker-compose.yml`, `.env.example`, `infra/` | 백엔드 | 로컬 실행 환경 전체에 영향 |
| `backend/requirements.txt` | 백엔드(공용) | AI 라이브러리 추가는 AI 담당이 요청 → 백엔드가 반영 |
| `AGENTS.md`, `CLAUDE.md`, `backend/CLAUDE.md`, `agent.md`, `docs/*` | 공용 | 문서만 바꾸는 변경은 `dev`에 직접 커밋해도 된다. 코드와 함께 바뀌면 그 PR에 포함 |

충돌 예방 원칙:

- API 계약 변경은 **작은 PR로 만들어 먼저 머지**하고, FE·AI는 머지 직후 dev를 브랜치에 반영한다.
- Alembic 리비전을 만들기 전 항상 dev를 먼저 반영한다. 리비전 체인(`down_revision`)이 갈라지면
  나중에 만든 쪽이 자신의 리비전을 재생성한다.
- `package-lock.json`, `requirements.txt` 충돌은 수동 병합하지 말고 **dev 기준으로 되돌린 뒤 재생성**한다.
- 파일 이동·이름 변경 같은 대규모 리팩터는 단독 PR로 분리하고, 머지하는 즉시 팀에 공유한다.

### 3. 브랜치

- `main` - 배포 브랜치. 직접 푸시 금지.
- `dev` - 통합 브랜치. 코드 변경은 **PR로만** 반영한다 (문서만 바꾸는 커밋은 직접 푸시 가능).
- `feature/*` - 작업 브랜치. 항상 최신 `dev`에서 분기한다.

브랜치 이름은 **각 계획서의 "PR 권장안" 표에 적힌 이름을 그대로 사용**한다
(백엔드는 위 캡스톤 2 로드맵 표). 표에 없는 작업만 아래 규칙으로 새로 만든다.

```
feature/be-<주제>    # 백엔드
feature/fe-<주제>    # 프론트엔드
feature/ai-<주제>    # AI
fix/<be|fe|ai>-<주제>
docs/<주제>
```

- 한 브랜치 = 한 PR = 계획서의 PR 묶음 하나. 여러 담당 분야를 한 브랜치에 섞지 않는다.
- 브랜치는 오래 두지 않는다. **길어도 3~4일 안에 PR을 올린다** (오래될수록 충돌이 커진다).
- **브랜치 이름으로 소유 경로가 판정된다.** CI가 이름을 보고 담당(be/fe/ai)을 정한 뒤,
  그 담당의 경로 밖 파일이 바뀌었으면 PR을 실패시킨다
  (판정 규칙: `.github/scripts/check-path-ownership.sh`). 위 명명 규칙을 벗어나면
  담당을 판정할 수 없어 그대로 실패하므로, 새 브랜치는 반드시 접두어를 지킨다.

### 4. 작업 절차

```bash
# 1) dev 최신화 후 분기
git switch dev && git pull origin dev
git switch -c feature/be-env-sandbox

# 2) 작업 → 작업 ID 단위로 커밋
git add <내 소유 경로의 파일만>
git commit -m "feat: SandboxService 추가 (BE-04)"

# 3) 작업 중 dev가 앞서갔으면 반영
git fetch origin
git rebase origin/dev          # 아직 push 안 한 커밋만 있을 때
# git merge origin/dev         # 이미 push했거나 남이 브랜치를 볼 때

# 4) push → PR → 바로 머지 (리뷰 대기 없음)
git push -u origin feature/be-env-sandbox
gh pr create --base dev --title "[BE-04] SandboxService 추가" --body "..."
gh pr merge --merge --delete-branch
git switch dev && git pull origin dev
```

- `--force` 금지. 불가피하면 **본인 전용 브랜치에서만** `--force-with-lease`.
- `dev`/`main`에는 어떤 경우에도 force push 하지 않는다.
- 커밋 메시지는 한국어, `<type>: <요약> (<작업 ID>)` 형식.
  type: `feat` `fix` `docs` `refactor` `test` `chore`

### 5. PR과 머지

- base 브랜치는 항상 `dev`. 제목에 작업 ID를 넣는다: `[BE-04] ...`
- PR 본문에 다음을 적는다:
  - 변경 요약 (작업 ID별)
  - 실행한 테스트와 결과 (예: `pytest -q → 32 passed`)
  - **공유 파일(§2)을 건드렸는지 여부** — 건드렸다면 다른 담당자에게 알림
  - 다른 담당자가 후속으로 해야 할 일
- **리뷰 대기 없이 본인이 바로 머지한다.** 다른 사람의 승인이나 리뷰 코멘트를 기다리지 않는다.
  여기서 PR은 검토 절차가 아니라 **변경 기록과 머지 커밋을 남기기 위한 장치**다.
- 사람 리뷰가 없으므로 **PR Checks(`.github/workflows/pr-checks.yml`)가 유일한 안전장치**다.
  3개 job(소유 경로 검사 / 백엔드 테스트 / 프론트엔드 빌드·린트)이 녹색이어야 머지된다.
  검사가 빨간데 억지로 머지하거나, 실패하는 테스트를 삭제·`xfail` 처리해서 통과시키지 않는다.
- **머지는 "Create a merge commit"(= `--no-ff`)만 사용한다.**
  커밋 내역이 그대로 남아야 하므로 **Squash merge·Rebase merge 금지**.
  ```bash
  gh pr merge --merge --delete-branch          # PR 올린 직후 바로 실행
  gh pr merge --merge --auto --delete-branch   # CI가 붙어 있으면 통과 즉시 자동 머지
  ```
  GitHub 저장소 설정도 Settings → General → Pull Requests에서 "Allow merge commits"만 켜고
  squash/rebase는 끈다. Branch protection의 **Required approvals는 설정하지 않는다**
  (설정하면 본인 머지가 막힌다).
- 머지 후 각자 `git switch dev && git pull origin dev`로 즉시 동기화한다.

### 6. AI 도구 사용 흔적을 저장소에 남기지 않기

각자 AI 도구(Claude Code 등)로 개발하지만, **저장소 기록에는 AI 흔적이 남지 않아야 한다.**

- 커밋 메시지·PR 제목·PR 본문에 `Co-Authored-By: Claude`, `Generated with ...`,
  `🤖`, `Anthropic`, `Claude Code` 등 **AI 생성 표시를 넣지 않는다.**
- `git config user.name` / `user.email`은 **본인 GitHub 계정**으로 설정한다.
  `noreply@anthropic.com` 같은 값이 커밋 author/committer에 들어가지 않게 한다.
  ```bash
  git config user.name "<본인 이름>"
  git config user.email "<본인 GitHub 이메일>"
  ```
- AI 도구 설정·세션 로그·작업 메모를 커밋하지 않는다
  (`.claude/`, `.kiro/`, `.antigravitycli/`, 세션 요약 파일, 임시 스크립트).
  → `.gitignore`에 등록되어 있는지 확인하고, 없으면 추가한다.
- 코드 주석·문서에 "AI가 생성함", "Claude가 작성" 같은 표기를 넣지 않는다.
  단, **제품 기능으로서의 AI**(AI 튜터, AI 시나리오 생성 등)를 설명하는 문구는 당연히 정상이다.
- 커밋 전 자체 점검:
  ```bash
  git log origin/dev..HEAD --format='%an <%ae> | %cn <%ce>%n%B' | grep -iE 'claude|anthropic|co-authored|generated with'
  # 아무것도 안 나와야 정상
  ```

### 7. AI 에이전트(Claude Code 등)에게 적용되는 규칙

- 브랜치 생성 → 커밋 → push → PR 생성 → 머지까지 **중간에 승인을 묻지 말고 끝까지 진행한다.**
  단계마다 "진행할까요?"를 확인하지 않는다.
- `git add -A` / `git add .` 대신 **변경한 파일을 명시적으로 지정**해 스테이징한다.
  (의도치 않은 파일이 딸려 들어가는 것을 막기 위한 것이지, 승인 절차가 아니다.)
- 6항의 AI 표시 금지 규칙을 커밋·PR 작성 시 항상 적용한다.
- 다음 두 가지만 **하지 않는다**:
  - `dev` / `main`에 force push
  - 커밋되지 않은 남의 작업을 날리는 `git reset --hard`, `git clean -fd`

## 로컬 실행
```bash
# 인프라만 (권장 - Method B)
docker compose up postgres qdrant -d

# 백엔드 (AI_BACKEND=openai|gemini 시 서버 시작 시 Qdrant 자동 ingestion)
cd backend
source venv/bin/activate
uvicorn app.main:app --port 8000

# 프론트엔드
cd frontend
npm run dev

# Swagger
open http://localhost:8000/docs
```

## 환경변수 (.env)
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival

# AI 백엔드 선택
AI_BACKEND=mock              # mock | openai | gemini

# OpenAI 모드
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
SCENARIO_MODEL=gpt-4o-mini
TUTOR_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

# Gemini 모드 (OpenAI 호환 API 사용)
GEMINI_API_KEY=
GEMINI_MODEL=models/gemini-2.0-flash-lite
GEMINI_EMBEDDING_MODEL=models/text-embedding-004

# 인프라
CHAOS_BACKEND=mock           # mock | chaos_mesh
VALIDATION_BACKEND=mock      # mock | k8s | prometheus
MOCK_VALIDATION_AUTO_PASS=false
PROMETHEUS_URL=http://localhost:9090

# RAG (Qdrant 벡터 DB)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=              # Qdrant Cloud 사용 시

# 프론트엔드 (Vite 빌드 시)
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
VITE_GRAFANA_BASE_URL=http://localhost:3001
```

## 모니터링 스택 실행
```bash
docker compose --profile monitoring up -d

# Grafana: http://localhost:3001 (admin/admin)
# Prometheus: http://localhost:9090
```

> **주의 (로컬 환경)**: `infra/monitoring/prometheus.yml`의 노드명(`desktop-control-plane`)은 **Docker Desktop 4.x 이상** 기준.
> 구버전 Docker Desktop은 노드명이 `docker-desktop`이므로 Grafana CPU/Memory가 No Data로 표시됨.
> ```bash
> kubectl get nodes          # 노드명 확인
> docker --version           # Docker Desktop 버전 확인
> # 구버전이면 Docker Desktop 업데이트 권장 (Settings → Check for Updates)
> # 업데이트 후 Settings → Kubernetes → Reset Kubernetes Cluster
> ```
> 캡스톤 2 (EKS 배포) 때 Kubernetes 서비스 디스커버리(`kubernetes_sd_configs`)로 자동화 예정.

## 주요 설계 문서
- [docs/parallel-execution-order.md](docs/parallel-execution-order.md) - **3인 병렬 AI 실행 순서와 웨이브 게이트 (실행 전 필독)**
- [agent.md](agent.md) - AI 장애 생성 모드 전체 설계 및 구현 현황 (Phase 1~7)
- [backend/CLAUDE.md](backend/CLAUDE.md) - 백엔드 API 및 서비스 상세
- [README.md](README.md) - 프로젝트 공개 소개

## 규칙
- 항상 한국어로 응답
- 커밋 메시지는 한국어로 작성
