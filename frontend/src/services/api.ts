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
  // OAuth2PasswordRequestForm 형식으로 전송
  const formData = new URLSearchParams()
  formData.append('username', username)
  formData.append('password', password)

  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: formData.toString(),
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
