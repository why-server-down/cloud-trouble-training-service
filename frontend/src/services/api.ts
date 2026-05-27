// API Base URL - 환경변수에서 가져오기
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// API 응답 타입 정의
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

// 로그인
export const login = async (
  username: string,
  password: string
): Promise<LoginResponse> => {
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
    if (response.status === 401) {
      throw new Error('아이디 또는 비밀번호가 잘못되었습니다')
    }
    throw new Error('로그인에 실패했습니다')
  }

  return response.json()
}

// 회원가입
export const register = async (
  username: string,
  password: string
): Promise<RegisterResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username, password }),
  })

  if (!response.ok) {
    if (response.status === 409) {
      throw new Error('이미 존재하는 사용자명입니다')
    }
    throw new Error('회원가입에 실패했습니다')
  }

  return response.json()
}

// 터미널 세션 생성
export const createTerminalSession = async (
  token: string
): Promise<SessionResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/terminal/sessions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('인증이 필요합니다')
    }
    throw new Error('세션 생성에 실패했습니다')
  }

  return response.json()
}

// 헬스 체크
export const healthCheck = async (): Promise<{ status: string }> => {
  const response = await fetch(`${API_BASE_URL}/health`)
  return response.json()
}

// Mission 관련 타입
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

interface MissionAttemptResponse {
  id: string
  user_id: string
  mission_id: string
  status: string
  start_time: string
  end_time: string | null
  final_score: number | null
  hints_used: number
}

interface MissionStatusResponse {
  attempt: MissionAttemptResponse
  elapsed_seconds: number
  remaining_seconds: number
  current_score: number
}

interface MissionCompleteResponse {
  attempt: MissionAttemptResponse
  message: string
}

// 미션 목록 조회
export const listMissions = async (token: string): Promise<MissionResponse[]> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error('미션 목록 조회 실패')
  }

  return response.json()
}

// 미션 시작
export const startMission = async (
  token: string,
  missionId: string
): Promise<MissionAttemptResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/start`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ mission_id: missionId }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '미션 시작 실패')
  }

  return response.json()
}

// 미션 상태 조회
export const getMissionStatus = async (
  token: string
): Promise<MissionStatusResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/status`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '미션 상태 조회 실패')
  }

  return response.json()
}

// 미션 완료 확인
export const checkMission = async (
  token: string
): Promise<MissionCompleteResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/check`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '미션 확인 실패')
  }

  return response.json()
}

// 미션 포기
export const abandonMission = async (
  token: string
): Promise<MissionAttemptResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/abandon`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '미션 포기 실패')
  }

  return response.json()
}

// 힌트 사용
export const useHint = async (
  token: string
): Promise<MissionAttemptResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/missions/hint`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '힌트 사용 실패')
  }

  return response.json()
}
