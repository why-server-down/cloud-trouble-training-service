/**
 * 훈련 환경(environment) 관련 API 계약 타입.
 *
 * 원본은 백엔드의 `app/core/environments.py` 와 `app/schemas.py` 다.
 * 이 파일은 그 계약의 미러이며, 프론트 어디에서도
 * `'kubernetes' | 'docker' | 'linux'` union 을 다시 선언하지 않는다.
 */

/** 백엔드 `SUPPORTED_ENVIRONMENTS` 와 1:1. 순서까지 동일하게 유지한다. */
export const ENVIRONMENT_IDS = ['kubernetes', 'docker', 'linux'] as const

export type EnvironmentId = (typeof ENVIRONMENT_IDS)[number]

/** 백엔드 `DEFAULT_ENVIRONMENT`. 응답에 environment 가 없을 때의 폴백이기도 하다. */
export const DEFAULT_ENVIRONMENT: EnvironmentId = 'kubernetes'

/**
 * API 응답의 environment 를 신뢰하기 전에 통과시키는 type guard.
 * 백엔드가 Literal 로 검증하므로 여기서 걸리면 계약이 어긋났다는 뜻이다.
 */
export const isEnvironmentId = (value: unknown): value is EnvironmentId =>
  typeof value === 'string' && (ENVIRONMENT_IDS as readonly string[]).includes(value)

/**
 * `GET /api/environments` 의 status.
 *
 * 백엔드가 **현재 실제로 내보내는 값은 available / preparing 두 개**뿐이다
 * (`core/environments.py` 의 AVAILABLE, PREPARING). degraded / disabled 는
 * FE-03 요구사항이 UI 처리를 명시한 상태이고 백엔드 필드 타입이 `str` 이므로,
 * 값이 추가되는 순간 바로 동작하도록 화면 처리만 먼저 갖춘다.
 * 목록에 없는 status 가 와도 탭 전체가 깨지지 않아야 한다 —
 * `EnvironmentItem.status` 를 string 으로 받는 이유다.
 */
export const ENVIRONMENT_STATUSES = ['available', 'degraded', 'preparing', 'disabled'] as const

export type EnvironmentStatus = (typeof ENVIRONMENT_STATUSES)[number]

export const isEnvironmentStatus = (value: unknown): value is EnvironmentStatus =>
  typeof value === 'string' && (ENVIRONMENT_STATUSES as readonly string[]).includes(value)

export interface EnvironmentItem {
  id: EnvironmentId
  /**
   * 알려진 값은 `EnvironmentStatus` 지만, 백엔드가 새 status 를 추가해도 파싱이
   * 죽지 않도록 string 으로 받는다. 소비하는 쪽에서 `isEnvironmentStatus()` 로 좁힌다.
   */
  status: string
  /** 백엔드 `_CAPABILITIES` 값. status 가 preparing 이면 빈 배열이다. */
  capabilities: string[]
}

export interface EnvironmentListResponse {
  items: EnvironmentItem[]
}

/** 시도 종류. 백엔드 `mission_attempts.attempt_type` check 제약과 동일하다. */
export const ATTEMPT_TYPES = ['static_mission', 'ai_scenario'] as const

export type AttemptType = (typeof ATTEMPT_TYPES)[number]

export const isAttemptType = (value: unknown): value is AttemptType =>
  typeof value === 'string' && (ATTEMPT_TYPES as readonly string[]).includes(value)

/**
 * 활성 시도 요약. MissionList 가 서버 status 로 만들어 App 에 올리고, App 은 이걸로
 * 환경 탭을 잠근다. 실행 환경의 원본은 항상 서버 응답이다(클라이언트 값 신뢰 금지).
 */
export interface ActiveAttemptSummary {
  attemptId: string
  attemptType: AttemptType
  environment: EnvironmentId
  status: string
}

// ── environment 를 포함하는 응답 타입 ────────────────────────────────

export interface SessionResponse {
  id: string
  namespace: string
  environment: EnvironmentId
  created_at: string
  is_active: boolean
}

export interface MissionResponse {
  id: string
  name: string
  level: number
  description: string
  chaos_type: string
  environment: EnvironmentId
  base_score: number
  time_limit: number
  hint_penalty: number
  is_unlocked: boolean
}

export interface MissionAttemptResponse {
  id: string
  user_id: string
  mission_id: string | null
  attempt_type: AttemptType
  scenario_id: string | null
  environment: EnvironmentId
  status: string
  start_time: string
  end_time: string | null
  final_score: number | null
  hints_used: number
}

export interface MissionStatusResponse {
  attempt: MissionAttemptResponse
  elapsed_seconds: number
  remaining_seconds: number
  current_score: number
}

export interface MissionCompleteResponse {
  attempt: MissionAttemptResponse
  message: string
}

export interface ScenarioResponse {
  scenario_id: string
  title: string
  difficulty: string
  environment: EnvironmentId
  student_brief: string
  time_limit_seconds: number
  base_score: number
  hint_penalty: number
  safety_status: string
}

export interface ScenarioStatusResponse {
  scenario_id: string
  attempt_id: string
  title: string
  difficulty: string
  environment: EnvironmentId
  student_brief: string
  elapsed_seconds: number
  remaining_seconds: number
  current_score: number
  hints_used: number
  status: string
}
