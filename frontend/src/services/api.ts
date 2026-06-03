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

interface LoginResponse {
  access_token: string
  token_type: string
}

interface SessionResponse {
  id: string
  namespace: string
  created_at: string
  is_active: boolean
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

interface MissionResponse {
  id: string
  name: string
  level: number
  description: string
  chaos_type: string
  base_score: number
  time_limit: number
  hint_penalty: number
  is_unlocked: boolean
}

export interface MissionAttemptResponse {
  id: string
  user_id: string
  mission_id: string
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

interface MissionCompleteResponse {
  attempt: MissionAttemptResponse
  message: string
}

interface ChatResponse {
  response: string
  hint_level: number
  mission_name: string | null
}

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

export interface DashboardStatsResponse {
  username: string
  total_score: number
  missions_completed: number
  total_time_spent: number
  hints_used: number
  current_tier: TierInfo
  skill_scores: Record<'troubleshooting' | 'resource' | 'network' | 'ops', number>
}

export interface LearningCurveEntry {
  attempt_id: string
  mission_id: string
  mission_name: string
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

export const createTerminalSession = async (token: string): Promise<SessionResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/terminal/sessions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '터미널 세션 생성에 실패했습니다'))
  }

  return response.json()
}

export const healthCheck = async (): Promise<{ status: string }> => {
  const response = await fetch(`${API_BASE_URL}/health`)
  return response.json()
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

export const listMissions = async (token: string): Promise<MissionResponse[]> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '미션 목록 조회에 실패했습니다'))
  }

  return response.json()
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

  return response.json()
}

export const getMissionStatus = async (token: string): Promise<MissionStatusResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/status`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '미션 상태 조회에 실패했습니다'))
  }

  return response.json()
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

  return response.json()
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

  return response.json()
}

export const useHint = async (token: string): Promise<MissionAttemptResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/hint`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, '힌트 사용에 실패했습니다'))
  }

  return response.json()
}

export const askTutor = async (token: string, message: string, hintLevel: number = 0): Promise<ChatResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/chat/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, hint_level: hintLevel }),
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, 'AI 튜터 응답을 받지 못했습니다'))
  }

  return response.json()
}

const getAuthorizedJson = async <T>(token: string, path: string, fallback: string): Promise<T> => {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorDetail(response, fallback))
  }

  return response.json()
}

export const getDashboardStats = (token: string) =>
  getAuthorizedJson<DashboardStatsResponse>(token, '/api/dashboard/stats', 'Failed to load dashboard stats.')

export const getLearningCurve = (token: string) =>
  getAuthorizedJson<LearningCurveEntry[]>(token, '/api/dashboard/learning-curve', 'Failed to load learning curve.')

export const getLeaderboard = (token: string) =>
  getAuthorizedJson<LeaderboardEntry[]>(token, '/api/leaderboard?limit=10', 'Failed to load leaderboard.')

export const getAchievements = (token: string) =>
  getAuthorizedJson<AchievementsResponse>(token, '/api/achievements', 'Failed to load achievements.')

// AI Scenario

export interface ScenarioResponse {
  scenario_id: string
  title: string
  difficulty: string
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
  student_brief: string
  elapsed_seconds: number
  remaining_seconds: number
  current_score: number
  hints_used: number
  status: string
}

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

export const getScenarioStatus = (token: string) =>
  getAuthorizedJson<ScenarioStatusResponse>(token, '/api/scenarios/status', 'AI 시나리오 상태를 불러오지 못했습니다')

export const startRandomScenario = async (token: string, difficulty: string): Promise<ScenarioResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/start-random`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ difficulty, randomize: true }),
  })
  if (!response.ok) throw new Error(await getErrorDetail(response, 'AI 시나리오 시작에 실패했습니다'))
  return response.json()
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

export const useScenarioHint = async (token: string): Promise<MissionAttemptResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/current/hint`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(await getErrorDetail(response, '힌트 사용에 실패했습니다'))
  return response.json()
}

export const debugResolveScenario = async (token: string): Promise<{ message: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/debug/resolve`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(await getErrorDetail(response, '디버그 해결에 실패했습니다'))
  return response.json()
}
