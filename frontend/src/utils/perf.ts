/**
 * 성능 측정 (FE-20).
 *
 * 계획서 원칙: **프론트는 측정값을 숨기지 않는다.** AI 1.5초·자동 채점 300ms 는
 * 백엔드·LLM 을 포함한 목표라서 프론트가 "빠르게 보이게" 만들면 목표 달성 여부를
 * 판단할 수 없게 된다.
 *
 * `console.log` 대신 User Timing API(`performance.mark`/`measure`)를 쓴다:
 * - DevTools Performance 패널에 그대로 나타난다.
 * - 자동화 검증(Playwright)이 `performance.getEntriesByType('measure')` 로 읽는다.
 * - 프로덕션 빌드에서도 남지만 화면에는 아무 영향이 없다.
 */

export const PERF = {
  /** 질문 전송 → 답변 도착. AI 1.5초 목표의 실제 체감값. */
  TUTOR_RESPONSE: 'afterfail:tutor-response',
  /** 완료 확인 클릭 → check API 응답. */
  MISSION_CHECK_API: 'afterfail:mission-check-api',
  /** 완료 확인 클릭 → 화면 반영 완료. API 시간과 구분해 잰다. */
  MISSION_CHECK_COMMIT: 'afterfail:mission-check-commit',
  /** 환경 필터 클릭 → 로딩 상태 표시. 프론트 자체 목표 100ms. */
  DASHBOARD_FILTER_LOADING: 'afterfail:dashboard-filter-loading',
} as const

export type PerfName = (typeof PERF)[keyof typeof PERF]

const isSupported = () =>
  typeof performance !== 'undefined' &&
  typeof performance.mark === 'function' &&
  typeof performance.measure === 'function'

/** 측정 시작점을 찍는다. 같은 이름으로 다시 찍으면 이전 시작점을 덮는다. */
export const markStart = (name: PerfName) => {
  if (!isSupported()) return
  try {
    performance.clearMarks(`${name}:start`)
    performance.mark(`${name}:start`)
  } catch {
    // 측정 실패가 기능을 막아서는 안 된다.
  }
}

/**
 * 시작점부터 지금까지를 measure 로 남기고 경과 ms 를 돌려준다.
 * 시작점이 없으면 null 이다 (측정만 놓치고 동작은 그대로 간다).
 */
export const measureSince = (name: PerfName): number | null => {
  if (!isSupported()) return null

  try {
    const start = performance.getEntriesByName(`${name}:start`, 'mark')
    if (start.length === 0) return null

    performance.measure(name, `${name}:start`)
    const entries = performance.getEntriesByName(name, 'measure')
    const last = entries[entries.length - 1]
    performance.clearMarks(`${name}:start`)
    return last ? Math.round(last.duration) : null
  } catch {
    return null
  }
}

/** 다음 frame 까지 기다린다. "화면에 반영된 시점"을 재기 위한 것이다. */
export const nextFrame = (): Promise<void> =>
  new Promise((resolve) => {
    if (typeof requestAnimationFrame !== 'function') {
      resolve()
      return
    }
    requestAnimationFrame(() => resolve())
  })
