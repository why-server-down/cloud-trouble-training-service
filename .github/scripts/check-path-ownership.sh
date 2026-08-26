#!/usr/bin/env bash
#
# 브랜치 이름으로 담당(be/fe/ai)을 판정하고, 그 담당의 소유 경로 밖 파일이
# 변경됐으면 실패시킨다. 3명이 각자 AI 자율 실행을 돌릴 때 같은 파일에 동시에
# 쓰는 것을 물리적으로 막는 것이 목적이다.
#
# 사용법: check-path-ownership.sh <브랜치이름> <base-sha>

set -euo pipefail

BRANCH="${1:?브랜치 이름이 필요하다}"
BASE_SHA="${2:?base SHA가 필요하다}"

# ── 계획서 PR 표에 이미 정해진 브랜치 이름 → 담당 매핑 ──────────────────
declare -A EXPLICIT=(
  # 백엔드 (AGENTS.md 캡스톤 2 로드맵 표)
  [feature/env-schema]=be
  [feature/injector-refactor]=be
  [feature/backend-baseline]=be
  [feature/env-sandbox]=be
  [feature/safe-terminal-exec]=be
  [feature/env-runtime]=be
  [feature/docker-env]=be
  [feature/linux-env]=be
  [feature/cross-layer-contracts]=be
  [feature/backend-hardening]=be
  [feature/aws-migration]=be
  [feature/backend-release]=be
  # AI (docs/ai-capstone2-semester-plan.md §9)
  [feature/multi-env-knowledge]=ai
  [feature/versioned-qdrant]=ai
  [feature/cross-layer-rag]=ai
  [feature/cross-layer-tutor]=ai
  [feature/multi-env-scenario]=ai
  [feature/runtime-ai-context]=ai
)

OWNER=""
if [[ -n "${EXPLICIT[$BRANCH]:-}" ]]; then
  OWNER="${EXPLICIT[$BRANCH]}"
elif [[ "$BRANCH" =~ ^(feature|fix)/(be|backend)- ]]; then
  OWNER=be
elif [[ "$BRANCH" =~ ^(feature|fix)/(fe|frontend)- ]]; then
  OWNER=fe
elif [[ "$BRANCH" =~ ^(feature|fix)/ai- ]]; then
  OWNER=ai
elif [[ "$BRANCH" =~ ^docs/ ]]; then
  OWNER=docs
else
  echo "::error::브랜치 이름 '$BRANCH'로 담당을 판정할 수 없다."
  echo "다음 중 하나를 쓴다: feature/be-*, feature/fe-*, feature/ai-*, docs/*"
  echo "또는 계획서 PR 표에 있는 이름을 그대로 쓴다 (이 스크립트의 EXPLICIT 목록)."
  exit 1
fi

echo "브랜치: $BRANCH  →  담당: $OWNER"

# ── 담당별 허용 경로 ────────────────────────────────────────────────
is_allowed() {
  local f="$1"

  # 문서(.md)는 담당과 무관하게 누구나 수정 가능 — 빌드를 깨뜨리지 않는다
  [[ "$f" == *.md ]] && return 0

  case "$OWNER" in
    be)
      # backend/app/ai/ 는 AI 담당 소유이므로 백엔드에서 제외
      [[ "$f" == backend/app/ai/* ]] && return 1
      [[ "$f" == backend/*        ]] && return 0
      [[ "$f" == infra/*          ]] && return 0
      [[ "$f" == .github/*        ]] && return 0
      [[ "$f" == docker-compose.yml || "$f" == .env.example ]] && return 0
      [[ "$f" == .gitattributes    || "$f" == .gitignore    ]] && return 0
      ;;
    fe)
      [[ "$f" == frontend/* ]] && return 0
      ;;
    ai)
      [[ "$f" == ai-data/*         ]] && return 0
      [[ "$f" == backend/app/ai/*  ]] && return 0
      ;;
    docs)
      # .md 는 위에서 이미 통과했다. 그 외는 전부 불허.
      return 1
      ;;
  esac
  return 1
}

CHANGED="$(git diff --name-only --diff-filter=d "$BASE_SHA" HEAD)"

if [[ -z "$CHANGED" ]]; then
  echo "변경된 파일이 없다."
  exit 0
fi

VIOLATIONS=()
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if ! is_allowed "$f"; then
    VIOLATIONS+=("$f")
  fi
done <<< "$CHANGED"

if [[ ${#VIOLATIONS[@]} -eq 0 ]]; then
  echo "소유 경로 검사 통과 ($(wc -l <<< "$CHANGED")개 파일)"
  exit 0
fi

echo "::error::'$OWNER' 담당의 소유 경로를 벗어난 변경이 ${#VIOLATIONS[@]}건 있다:"
for f in "${VIOLATIONS[@]}"; do
  echo "  - $f"
done
cat <<'MSG'

해결 방법 (둘 중 하나):
  1) 해당 파일을 소유한 담당의 브랜치에서 별도 PR로 올린다. (권장)
  2) 정말 이 PR에 포함해야 하면 PR에 'path-override' 라벨을 달고
     PR 본문에 이유를 적는다. 이 검사는 건너뛴다.

소유 경로:
  be : backend/** (backend/app/ai/ 제외), infra/**, .github/**,
       docker-compose.yml, .env.example, .gitignore, .gitattributes
  fe : frontend/**
  ai : ai-data/**, backend/app/ai/**
  공통: 모든 *.md
MSG
exit 1
