# 3인 병렬 AI 실행 순서

> 대상: 백엔드 / 프론트엔드 / AI 담당이 **각자 AI 자율 실행을 돌려** 2학기 계획서를 구현하는 상황.
> 이 문서는 "무엇을 만드는가"가 아니라 **"언제 시작해도 되는가"**만 정한다.
> 작업 내용은 각 계획서(`docs/*-capstone2-semester-plan.md`)가 기준이다.

---

## 0. 왜 순서가 필요한가

세 계획서는 서로의 결과물을 기다리도록 쓰여 있다.

- 프론트 계획서 §7: `FE-05 → backend env-sandbox → FE-06/07/08`
- AI 계획서 §8: "백엔드 담당자에게 **요구할 것** — safe sandbox TrainingContext,
  mechanical validation result, scenario compiler reject reason …"

순서를 무시하고 동시에 출발하면 프론트·AI는 **아직 존재하지 않는 API에 대고 구현한다.**
결과물은 머지 충돌이 아니라 *틀린 코드*이고, 충돌보다 훨씬 비싸다(전부 다시 써야 한다).

또한 P0 보안 결손(host `shell=True` 실행, WebSocket 세션 소유권 미검증)은 BE-05/06에서
해소된다. 그 전에 Docker(DinD)·Linux 환경을 얹으면 위험이 더해지는 게 아니라 곱해진다.
**순서는 안전 설계의 일부다.**

---

## 1. 웨이브 구조

각 웨이브는 **게이트를 통과해야 다음 웨이브가 시작**된다.
같은 웨이브 안의 항목은 동시에 돌려도 된다 (소유 경로가 겹치지 않으므로 CI가 막아준다).

### Wave 0 — 계약 확정 (다른 둘은 대기)

| 담당 | 작업 | 비고 |
|---|---|---|
| 백엔드 | **BE-01 ~ BE-03** | 테스트 녹색화 → Alembic 도입 → API에 `environment` 필드 |
| AI | AI-00 (taxonomy 확정) | 문서 작업. 백엔드와 fault type 표를 합의만 한다 |
| 프론트 | FE-00 (API 계약 확정) | 문서/협의 작업. 코드 없음 |

**게이트 (전부 충족해야 Wave 1 시작):**

- [ ] `pytest -q`가 **녹색** (현재 기준선은 `1 failed, 31 passed` — BE-01이 이걸 고친다)
- [ ] `backend/app/schemas.py`의 environment 필드가 dev에 머지됨
- [ ] Kubernetes/Docker/Linux allowed fault type 표가 문서로 확정됨
- [ ] PR Checks 3개 job이 dev에서 required status check로 지정됨

> **이 웨이브 동안 프론트·AI는 코드 실행을 시작하지 않는다.**
> 계약이 흔들리는 상태에서 만든 타입·프롬프트는 전부 폐기 대상이 된다.

### Wave 1 — 실행 기반 (3인 병렬)

| 담당 | 작업 | 브랜치 |
|---|---|---|
| 백엔드 | BE-04, BE-07 (SandboxService, 세션 API) | `feature/env-sandbox` |
| 백엔드 | BE-05, BE-06 (Pod exec 전환, WS 소유권 검증) | `feature/safe-terminal-exec` |
| AI | AI-01 ~ AI-02 (설정 경로 정리, offline 품질 기준) | `feature/ai-baseline` |
| 프론트 | FE-01 ~ FE-05 (타입, 환경 탭, 세션, attempt 잠금) | `feature/frontend-env-*` |

**게이트:** BE-05/06 머지 완료 (host shell 실행 제거). 이게 안 끝나면 Wave 2로 못 간다.

### Wave 2 — 환경 확장 (3인 병렬)

| 담당 | 작업 |
|---|---|
| 백엔드 | BE-08~10 (environment factory) → BE-11~15 (Docker) → BE-16~18 (Linux) |
| AI | AI-03~06 (멀티 환경 knowledge base, versioned Qdrant) |
| 프론트 | FE-06~09 (Docker/Linux 훈련 UI) |

**게이트:** BE-15 = **8주차 범위 게이트**. 여기서 Docker/Linux 실구현 여부를 판정한다.
통과 못 하면 Wave 3의 범위를 줄인다.

### Wave 3 — 크로스 레이어 (3인 병렬)

| 담당 | 작업 |
|---|---|
| 백엔드 | BE-19~21 (RuntimeContext, AI 실행 계약, MTTR) |
| AI | AI-07~17 (hybrid RAG, 환경 인지 튜터, 멀티 환경 시나리오 생성) |
| 프론트 | FE-11~15 (튜터 UX, 환경별 대시보드) |

**게이트:** AI 실행 계약(`TutorResult`, `ValidationJudgment`)이 `schemas.py`에 반영됨.
→ 이건 **백엔드 브랜치에서** 머지되어야 한다 (아래 §3 참고).

### Wave 4 — 마감 (3인 병렬)

BE-22~28 / AI-18~28 / FE-16~21 (안정화, 테스트 확대, E2E, 문서, 제출)

---

## 2. 매 웨이브 공통 규칙

- 한 웨이브를 **PR 하나로 몰지 않는다.** 스프린트/작업 묶음 단위로 쪼개서 올린다.
  한 실행 = PR 1개면 문제가 생겼을 때 `git revert -m 1`이 "전부 되돌리기"밖에 안 된다.
- PR은 올린 뒤 **바로 머지**한다 (리뷰 대기 없음). 단 PR Checks가 녹색일 때만 머지된다.
- 머지 직후 나머지 두 명은 `git switch dev && git pull origin dev`로 동기화한다.
- 웨이브 게이트를 통과했는지는 **사람이 판단한다.** 이건 자동화하지 않는다.

---

## 3. 경계 작업 (실제로 충돌하는 지점)

CI 소유 경로 검사로 대부분의 충돌은 막히지만, **계획서상 경계를 넘는 작업이 3건 확인**됐다.
이건 규칙으로 못 막으니 아래대로 처리한다.

| 작업 | 문제 | 처리 |
|---|---|---|
| **AI-01 설정 경로 정리** | AI 계획서가 `backend/app/core/config.py`와 `requirements.txt` 수정을 지시하는데, 둘 다 백엔드 소유 | 백엔드 쪽 변경은 **백엔드가 BE 브랜치에서** 처리한다. AI는 필요한 설정 키 목록만 넘긴다 |
| **AI 튜터 계약** (`TutorResult`) | `backend/app/api/chat.py`, `schemas.py`가 백엔드 소유인데 AI 작업이 반드시 건드린다 | `schemas.py` 변경은 백엔드가 **먼저 작은 PR로** 머지 → AI는 그 위에서 `backend/app/ai/`만 수정 |
| **AI 라이브러리 추가** | `requirements.txt`는 백엔드 소유 | AI가 패키지명·버전을 요청 → 백엔드가 반영 |

`backend/app/api/chat.py`와 `backend/app/services/scenario_service.py`는
`app/ai/`를 import 하는 **경계 파일**이다. 이 두 파일을 바꾸는 PR은 작게 만들고 먼저 머지한다.

정말 한 PR에 섞어야 하면 PR에 `path-override` 라벨을 달면 CI 검사를 건너뛴다.
**남용하면 이 문서 전체가 무의미해진다.** 사유를 PR 본문에 반드시 남긴다.

---

## 4. 시작 전 체크리스트

3인이 각자 실행을 시작하기 전에 이것만 확인한다.

- [ ] `dev` 브랜치에 **Required status checks**로 `소유 경로 검사` / `백엔드 테스트` / `프론트엔드 빌드/린트` 지정
- [ ] **Required approvals는 0** (사람 승인 대기를 두지 않기로 한 결정)
- [ ] 저장소 설정에서 **squash merge / rebase merge 비활성화** (merge commit만 허용)
- [ ] 각자 `git config user.name` / `user.email`이 본인 GitHub 계정인지 확인
- [ ] Wave 0 게이트가 전부 체크됐는지 확인

관련 규칙은 [../AGENTS.md](../AGENTS.md) "팀 협업 & Git 규칙" 참고.

---

## 5. 게이트 확인 방법 (AI 에이전트용)

작업을 시작하기 전에 **사람에게 묻지 말고 아래 명령으로 직접 판정한다.**
결과가 조건과 다르면 [../AGENTS.md](../AGENTS.md) §7-1의 보고 양식으로 사람에게 알린다.

### 5-1. 내 작업이 어느 웨이브인가

| 작업 ID | 웨이브 |
|---|---|
| BE-01 ~ BE-03 / AI-00 / FE-00 | Wave 0 |
| BE-04 ~ BE-07 / AI-01 ~ AI-02 / FE-01 ~ FE-05 | Wave 1 |
| BE-08 ~ BE-18 / AI-03 ~ AI-06 / FE-06 ~ FE-09 | Wave 2 |
| BE-19 ~ BE-21 / AI-07 ~ AI-17 / FE-11 ~ FE-15 | Wave 3 |
| BE-22 ~ BE-28 / AI-18 ~ AI-28 / FE-16 ~ FE-21 | Wave 4 |

### 5-2. 공통 사전 확인

```bash
# dev 최신 상태로 맞춘다 (이걸 안 하면 아래 판정이 전부 틀린다)
git fetch origin && git log origin/dev --oneline -15
```

### 5-3. Wave 0 게이트 — Wave 1 이상을 시작하려면 전부 충족

```bash
# (1) 백엔드 테스트가 녹색인가?  → "failed"가 0이어야 한다
cd backend && python -m pytest -q; cd ..

# (2) API 계약에 environment 필드가 반영됐는가?  → 결과가 나와야 한다
git grep -n "environment" origin/dev -- backend/app/schemas.py

# (3) Alembic이 도입됐는가?  → 디렉터리가 있어야 한다
git ls-tree origin/dev --name-only backend/alembic

# (4) PR Checks가 dev에 required로 걸려 있는가?  → 404가 아니어야 한다
gh api repos/why-server-down/cloud-trouble-training-service/branches/dev/protection \
  --jq '.required_status_checks.contexts'
```

> (1)의 현재 기준선은 `1 failed, 31 passed`다. **BE-01이 이걸 고치기 전까지
> Wave 1 이상은 시작하지 않는다.** 실패 테스트를 삭제하거나 `xfail`로 숨겨서
> 녹색을 만드는 것은 게이트 통과가 아니다.

### 5-4. Wave 1 게이트 — Wave 2를 시작하려면

```bash
# host shell 실행이 제거됐는가?  → 결과가 없어야 한다 (P0 보안 결손)
git grep -n "shell=True" origin/dev -- backend/app

# 샌드박스 서비스가 들어왔는가?  → 파일이 있어야 한다
git ls-tree origin/dev --name-only backend/app/services | grep -i sandbox
```

### 5-5. Wave 2 게이트 — Wave 3을 시작하려면

BE-15(8주차 범위 게이트) 판정 결과가 필요하다. **이건 명령으로 확인할 수 없다.**
Docker/Linux 실구현을 계속할지 범위를 줄일지는 사람이 결정하므로, 사람에게 물어본다.

### 5-6. Wave 3 게이트 — Wave 4를 시작하려면

```bash
# AI 실행 계약이 schemas.py에 반영됐는가?
git grep -nE "TutorResult|ValidationJudgment" origin/dev -- backend/app/schemas.py
```

### 5-7. 프론트·AI 담당이 특히 주의할 것

프론트와 AI 작업은 **거의 전부 백엔드 머지에 의존한다.**
"백엔드가 아직 안 만들었으니 mock으로 만들어두자"는 선택을 하지 않는다.
확정되지 않은 계약 위에 만든 코드는 계약이 바뀌는 순간 전부 폐기된다 —
그 판단은 사람이 내리도록 보고하고 대기한다.
