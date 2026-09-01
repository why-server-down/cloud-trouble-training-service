/**
 * 폴링 간격 (FE-16).
 *
 * 한 곳에 모아 두면 "어디가 1초마다 서버를 때리는지"를 코드 전체를 훑지 않고 알 수 있다.
 * 탭이 백그라운드일 때는 보이지 않는 화면을 같은 빈도로 갱신할 이유가 없어 늘린다.
 */

/** 미션·시나리오 진행 상태. 남은 시간 표시는 로컬 tick 이 담당한다. */
export const MISSION_POLL_INTERVAL_MS = 5000
export const MISSION_POLL_HIDDEN_MS = 15000

/** 프로필(점수·완료 수). 사용자가 직접 바꾸는 값이 아니라 더 느려도 된다. */
export const PROFILE_POLL_INTERVAL_MS = 15000
export const PROFILE_POLL_HIDDEN_MS = 60000

/** 학습 대시보드. 미션 완료 시 refreshKey 로 즉시 갱신되므로 주기는 느려도 된다. */
export const DASHBOARD_POLL_INTERVAL_MS = 15000
export const DASHBOARD_POLL_HIDDEN_MS = 60000

/**
 * Grafana 데이터 준비 확인. 준비되면 스스로 멈추는 짧은 폴링이라 촘촘해도 된다.
 * 다만 영원히 돌지 않도록 아래 시도 상한을 둔다.
 */
export const GRAFANA_PROBE_INTERVAL_MS = 1000
export const GRAFANA_PROBE_HIDDEN_MS = 5000
/** 이 횟수를 넘기면 준비 확인을 포기하고 degraded 로 표시한다. */
export const GRAFANA_PROBE_MAX_ATTEMPTS = 20

/** 연속 실패 시 backoff 상한. 죽은 서버를 같은 빈도로 두드리지 않는다. */
export const MAX_BACKOFF_MS = 30000
