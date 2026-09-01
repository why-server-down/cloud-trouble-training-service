import {
  DEFAULT_ENVIRONMENT,
  EnvironmentId,
  EnvironmentItem,
  EnvironmentListResponse,
  isEnvironmentId,
  MissionAttemptResponse,
  MissionCompleteResponse,
  MissionResponse,
  MissionStatusResponse,
  ScenarioResponse,
  ScenarioStatusResponse,
  SessionResponse,
} from '../types/training'

// 응답 타입의 단일 원본은 `types/training.ts` 다. 기존 호출부가 api 모듈에서
// 타입을 가져오고 있으므로 여기서 다시 내보내 import 경로를 깨지 않는다.
export type {
  AttemptType,
  EnvironmentId,
  EnvironmentItem,
  EnvironmentListResponse,
  EnvironmentStatus,
  MissionAttemptResponse,
  MissionCompleteResponse,
  MissionResponse,
  MissionStatusResponse,
  ScenarioResponse,
  ScenarioStatusResponse,
  SessionResponse,
} from '../types/training'

const normalizeApiBaseUrl = (configuredUrl?: string) => {
  if (!configuredUrl) return ''

  try {
    const url = new URL(configuredUrl)
    const isSameBrowserHost = url.hostname === window.location.hostname
    const isDockerServiceName = url.hostname === 'backend'

    if (isDockerServiceName || (isSameBrowserHost && url.port === '8000')) {
      return ''
    }
  } catch {
    return configuredUrl
  }

  return configuredUrl.replace(/\/$/, '')
}

const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL)
export const AUTH_EXPIRED_EVENT = 'auth-expired'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface LoginResponse {
  access_token: string
  token_type: string
}

interface RegisterResponse {
  id: string
  username: string
  created_at: string
}

export interface UserProfileResponse {
  id: string
  username: string
  created_at: string
  missions_completed: number
  total_score: number
}

/**
 * 튜터 답변의 근거 한 건. 백엔드 `TutorSource` 와 1:1 이다 (FE-11).
 * `path` 는 지식 베이스 내부 경로일 수 있어 무조건 링크로 만들지 않는다.
 */
export interface TutorSource {
  title: string
  source_id?: string | null
  path?: string | null
  environment?: string | null
  similarity?: number | null
}

/**
 * `POST /api/chat/` 응답. 백엔드 `ChatResponse` 와 1:1 이다 (FE-11).
 *
 * 주의: 백엔드 `TutorResult` 에는 environment 가 있지만 `ChatResponse` 는 내보내지
 * 않는다. 그래서 환경 배지는 응답이 아니라 활성 attempt 의 환경으로 그린다.
 */
export interface ChatResponse {
  response: string
  hint_level: number
  mission_name: string | null
  /** 답변에 쓰인 근거 문서. 없을 수 있다. */
  sources?: TutorSource[] | null
  /** 답변에 실제로 쓰인 관측값의 이름. 정답이 아니라 무엇을 봤는지를 알린다. */
  observations_used?: string[] | null
  token_usage?: Record<string, unknown> | null
  /** 프로바이더 실패로 대체 응답을 준 경우. 사용자에게 숨기지 않는다. */
  fallback_used?: boolean
}

/**
 * 응답의 environment 를 검증한다.
 *
 * - 값이 있고 계약에 없는 문자열이면 ApiError 로 올려 사용자에게 표시한다.
 *   (백엔드는 Literal 로 검증하므로 여기서 걸리면 계약이 어긋난 것이다)
 * - 필드가 아예 없으면 kubernetes 로 폴백한다. 백엔드는 기본값과 함께 항상
 *   내보내지만, environment 이전 버전 백엔드에 붙었을 때 화면 전체가 죽는 것을 막는다.
 */
const ensureEnvironment = (payload: { environment?: unknown }, context: string): EnvironmentId => {
  const raw = payload.environment

  if (raw === undefined || raw === null) return DEFAULT_ENVIRONMENT
  if (!isEnvironmentId(raw)) {
    throw new ApiError(`${context} 응답의 환경 값이 올바르지 않습니다: ${String(raw)}`, 502)
  }

  return raw
}

const withEnvironment = <T extends { environment?: unknown }>(payload: T, context: string) => ({
  ...payload,
  environment: ensureEnvironment(payload, context),
})

const withAttemptEnvironment = <T extends { attempt: MissionAttemptResponse }>(
  payload: T,
  context: string,
) => ({
  ...payload,
  attempt: withEnvironment(payload.attempt, context),
})

const notifyIfUnauthorized = (response: Response) => {
  if (response.status === 401) {
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
  }
}

const getErrorDetail = async (response: Response, fallback: string) => {
  notifyIfUnauthorized(response)

  try {
    const error = await response.json()
    return error.detail || fallback
  } catch {
    return fallback
  }
}

export const login = async (username: string, password: string): Promise<LoginResponse> => {
  const formData = new URLSearchParams()
  formData.append('username', username)
  formData.append('password', password)

  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: formData,
  })

  if (!response.ok) {
    throw new Error(response.status === 401 ? '아이디 또는 비밀번호가 올바르지 않습니다' : '로그인에 실패했습니다')
  }

  return response.json()
}

export interface TierInfo {
  name: string
  min_score: number
  max_score: number | null
  color: string
  progress: number
  next_tier: string | null
}

/**
 * 한 환경의 집계 (FE-13).
 *
 * `competency` 가 null 이면 **아직 시도가 없다**는 뜻이다. 0 과 구분해야 한다 —
 * 0 은 "해봤는데 못했다"이고 null 은 "아직 안 했다"다
 * (`analytics_service._environment_stats`).
 */
export interface EnvironmentStatEntry {
  completed: number
  average_score: number
  average_mttr: number
  hints_used: number
  competency: number | null
}

export interface DashboardStatsResponse {
  username: string
  total_score: number
  missions_completed: number
  total_time_spent: number
  hints_used: number
  current_tier: TierInfo
  skill_scores: Record<'troubleshooting' | 'resource' | 'network' | 'ops', number>
  /** 이 응답이 어느 환경으로 필터된 것인가. null 이면 전체 합계다. */
  environment?: string | null
  /**
   * 환경별 분해. 백엔드는 **전체 조회(`environment=all`)일 때만** 채운다.
   * 필터를 건 조회에서는 빈 객체다 — 없는 값을 0 으로 읽지 않도록 주의한다.
   */
  environment_stats?: Record<string, EnvironmentStatEntry>
}

export interface LearningCurveEntry {
  attempt_id: string
  mission_id: string
  mission_name: string
  /** 이 시도가 어느 환경이었는지. 전체 보기에서 곡선을 구분하는 데 쓴다. */
  environment?: string
  attempt_number: number
  completion_time: number
  score: number
  hints_used: number
  completed_at: string
}

export interface LeaderboardEntry {
  rank: number
  user_id: string
  username: string
  total_score: number
  missions_completed: number
  is_current_user: boolean
}

export interface AchievementItem {
  id: string
  name: string
  description: string
  points_bonus: number
  is_hidden: boolean
  unlocked: boolean
}

export interface AchievementsResponse {
  unlocked: number
  total: number
  progress: number
  items: AchievementItem[]
}

export const register = async (username: string, password: string): Promise<RegisterResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username, password }),
  })

  if (!response.ok) {
    throw new Error(response.status === 409 ? '이미 존재하는 사용자명입니다' : '회원가입에 실패했습니다')
  }

  return response.json()
}

/**
 * 훈련 환경별 터미널 세션을 만든다.
 *
 * 백엔드는 같은 (user, environment) 조합에 대해 활성 세션을 재사용하므로
 * 이 호출 자체는 멱등이다. 그래도 중복 호출은 샌드박스 readiness 대기를
 * 그만큼 반복하게 하므로, 호출부(`useEnvironmentSessions`)에서 막는다.
 */
export const createTerminalSession = async (
  token: string,
  environment: EnvironmentId,
): Promise<SessionResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/terminal/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ environment }),
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '터미널 세션 생성에 실패했습니다'))
  }

  return withEnvironment(await response.json() as SessionResponse, '터미널 세션')
}

/**
 * 터미널 세션을 종료한다. 로그아웃 정리용이라 실패해도 화면 흐름을 막지 않는다 —
 * 호출부가 결과를 무시할 수 있도록 예외 대신 성공 여부를 돌려준다.
 */
export const deleteTerminalSession = async (token: string, sessionId: string): Promise<boolean> => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/terminal/sessions/${sessionId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.ok
  } catch {
    return false
  }
}

export const getProfile = async (token: string): Promise<UserProfileResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '프로필을 불러오지 못했습니다'))
  }

  return response.json()
}

export const logoutUser = async (token: string): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '로그아웃에 실패했습니다'))
  }
}

/**
 * 환경별 미션 목록. 백엔드는 `environment` 기본값을 두지만 프론트는 항상 명시한다
 * (`backend/app/api/missions.py`) — 기본값에 기대면 탭을 바꿔도 같은 목록이 온다.
 *
 * `signal` 은 환경을 빠르게 전환했을 때 이전 요청을 끊기 위한 것이다. 끊지 않으면
 * 늦게 도착한 이전 환경 응답이 현재 화면을 덮는다.
 */
export const listMissions = async (
  token: string,
  environment: EnvironmentId,
  signal?: AbortSignal,
): Promise<MissionResponse[]> => {
  const query = new URLSearchParams({ environment })
  const response = await fetch(`${API_BASE_URL}/api/missions/?${query}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    signal,
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '미션 목록 조회에 실패했습니다'))
  }

  const missions = (await response.json() as MissionResponse[]).map((mission) =>
    withEnvironment(mission, '미션 목록'),
  )

  // 다른 환경 미션이 섞여 오면 조용히 걸러내지 않는다. 걸러내면 목록이 비어 보이는
  // 이유가 "준비 중"인지 "계약이 깨졌는지" 구분되지 않는다.
  const mismatched = missions.find((mission) => mission.environment !== environment)
  if (mismatched) {
    throw new ApiError(
      `미션 목록 응답에 요청한 환경(${environment})이 아닌 ${mismatched.environment} 미션이 섞여 있습니다`,
      502,
    )
  }

  return missions
}

export const startMission = async (token: string, missionId: string): Promise<MissionAttemptResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/start`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ mission_id: missionId }),
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '미션 시작에 실패했습니다'))
  }

  return withEnvironment(await response.json() as MissionAttemptResponse, '미션 시작')
}

export const getMissionStatus = async (token: string): Promise<MissionStatusResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/status`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new ApiError(await getErrorDetail(response, '미션 상태 조회에 실패했습니다'), response.status)
  }

  return withAttemptEnvironment(await response.json() as MissionStatusResponse, '미션 상태')
}

export const checkMission = async (token: string): Promise<MissionCompleteResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/check`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '미션 확인에 실패했습니다'))
  }

  return withAttemptEnvironment(await response.json() as MissionCompleteResponse, '미션 확인')
}

export const abandonMission = async (token: string): Promise<MissionAttemptResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/abandon`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '미션 포기에 실패했습니다'))
  }

  return withEnvironment(await response.json() as MissionAttemptResponse, '미션 포기')
}

export const requestHint = async (token: string): Promise<MissionAttemptResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/hint`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '힌트 사용에 실패했습니다'))
  }

  return withEnvironment(await response.json() as MissionAttemptResponse, '힌트 사용')
}

/**
 * AI 튜터 질문. `signal` 로 취소할 수 있다 (FE-12).
 * 취소된 요청은 AbortError 로 올라가므로 호출자가 메시지 목록에 넣지 않는다.
 */
export const askTutor = async (
  token: string,
  message: string,
  hintLevel: number = 0,
  signal?: AbortSignal,
): Promise<ChatResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/chat/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, hint_level: hintLevel }),
    signal,
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, 'AI 튜터 응답을 받지 못했습니다'))
  }

  return response.json()
}

const getAuthorizedJson = async <T>(
  token: string,
  path: string,
  fallback: string,
  signal?: AbortSignal,
): Promise<T> => {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    signal,
  })

  if (!response.ok) {
    throw new ApiError(await getErrorDetail(response, fallback), response.status)
  }

  return response.json()
}

/**
 * 대시보드 환경 필터 (FE-13). 백엔드 `EnvironmentFilter` 와 같은 값이다.
 * 'all' 은 전체 합계 + 환경별 분해를 뜻한다.
 */
export type DashboardEnvironmentFilter = EnvironmentId | 'all'

export const getDashboardStats = (
  token: string,
  environment: DashboardEnvironmentFilter = 'all',
  signal?: AbortSignal,
) =>
  getAuthorizedJson<DashboardStatsResponse>(
    token,
    `/api/dashboard/stats?environment=${environment}`,
    '통계를 불러오지 못했습니다',
    signal,
  )

export const getLearningCurve = (
  token: string,
  environment: DashboardEnvironmentFilter = 'all',
  signal?: AbortSignal,
) =>
  getAuthorizedJson<LearningCurveEntry[]>(
    token,
    `/api/dashboard/learning-curve?environment=${environment}`,
    '학습 곡선을 불러오지 못했습니다',
    signal,
  )

export const getLeaderboard = (token: string) =>
  getAuthorizedJson<LeaderboardEntry[]>(token, '/api/leaderboard?limit=10', 'Failed to load leaderboard.')

export const getAchievements = (token: string) =>
  getAuthorizedJson<AchievementsResponse>(token, '/api/achievements', 'Failed to load achievements.')

// Environments

/**
 * 훈련 환경 가용 상태 목록.
 *
 * 계약에 없는 id 는 응답 전체를 실패시키지 않고 건너뛴다 — 백엔드가 환경을 먼저
 * 추가해도 이미 열려 있는 환경의 훈련이 멈추면 안 된다. 반대로 미션·attempt·세션의
 * environment 는 사용자의 실제 훈련 대상이라 잘못된 값이면 오류로 올린다
 * (`withEnvironment`). 같은 필드가 아니라 역할이 다르다.
 */
export const getEnvironments = async (token: string): Promise<EnvironmentItem[]> => {
  const payload = await getAuthorizedJson<EnvironmentListResponse>(
    token,
    '/api/environments',
    '환경 목록을 불러오지 못했습니다',
  )

  if (!Array.isArray(payload?.items)) {
    throw new ApiError('환경 목록 응답 형식이 올바르지 않습니다', 502)
  }

  const known = payload.items.filter((item) => isEnvironmentId(item.id))
  if (known.length !== payload.items.length) {
    console.warn(`프론트가 모르는 환경 ${payload.items.length - known.length}건을 건너뛰었습니다.`)
  }

  return known
}

// AI Scenario

export interface ScenarioCheckResponse {
  resolved: boolean
  message: string
  score: number | null
}

export interface UnlockStatusResponse {
  unlocked: boolean
  completed_static: number
  total_static: number
}

export const getUnlockStatus = (token: string) =>
  getAuthorizedJson<UnlockStatusResponse>(token, '/api/scenarios/unlock-status', 'AI 잠금 상태를 불러오지 못했습니다')

export const getScenarioStatus = async (token: string) => {
  const status = await getAuthorizedJson<ScenarioStatusResponse>(
    token,
    '/api/scenarios/status',
    'AI 시나리오 상태를 불러오지 못했습니다',
  )
  return withEnvironment(status, 'AI 시나리오 상태')
}

export const startRandomScenario = async (
  token: string,
  difficulty: string,
  environment: EnvironmentId,
  demoUnlock: boolean = false,
): Promise<ScenarioResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/start-random`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ difficulty, environment, randomize: true, demo_unlock: demoUnlock }),
  })
  if (!response.ok) throw new Error(await getErrorDetail(response, 'AI 시나리오 시작에 실패했습니다'))
  return withEnvironment(await response.json() as ScenarioResponse, 'AI 시나리오 시작')
}

export const checkScenario = async (token: string): Promise<ScenarioCheckResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/current/check`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(await getErrorDetail(response, 'AI 시나리오 확인에 실패했습니다'))
  return response.json()
}

export const abandonScenario = async (token: string): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/current/abandon`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(await getErrorDetail(response, 'AI 시나리오 포기에 실패했습니다'))
}

export const requestScenarioHint = async (token: string): Promise<MissionAttemptResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/current/hint`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(await getErrorDetail(response, '힌트 사용에 실패했습니다'))
  return withEnvironment(await response.json() as MissionAttemptResponse, 'AI 시나리오 힌트')
}

