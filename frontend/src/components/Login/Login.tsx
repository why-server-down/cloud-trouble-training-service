import React, { useState } from 'react'
import { login, register, createTerminalSession } from '../../services/api'
import './Login.css'

interface LoginProps {
  onLoginSuccess: (token: string, sessionId: string, namespace?: string) => void
}

const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
  const [isRegisterMode, setIsRegisterMode] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      if (isRegisterMode) {
        // 회원가입 모드
        if (password !== confirmPassword) {
          setError('비밀번호가 일치하지 않습니다')
          setLoading(false)
          return
        }

        if (password.length < 6) {
          setError('비밀번호는 최소 6자 이상이어야 합니다')
          setLoading(false)
          return
        }

        // 1. 회원가입
        await register(username, password)
        
        // 2. 자동 로그인
        const loginResponse = await login(username, password)
        const token = loginResponse.access_token

        // 3. 터미널 세션 생성
        const sessionResponse = await createTerminalSession(token)
        const sessionId = sessionResponse.id
        const namespace = sessionResponse.namespace

        // 4. 성공 콜백
        onLoginSuccess(token, sessionId, namespace)
      } else {
        // 로그인 모드
        // 1. 로그인
        const loginResponse = await login(username, password)
        const token = loginResponse.access_token

        // 2. 터미널 세션 생성
        const sessionResponse = await createTerminalSession(token)
        const sessionId = sessionResponse.id
        const namespace = sessionResponse.namespace

        // 3. 성공 콜백
        onLoginSuccess(token, sessionId, namespace)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : isRegisterMode ? '회원가입에 실패했습니다' : '로그인에 실패했습니다')
    } finally {
      setLoading(false)
    }
  }

  const toggleMode = () => {
    setIsRegisterMode(!isRegisterMode)
    setError(null)
    setPassword('')
    setConfirmPassword('')
  }

  return (
    <div className="login-container">
      <div className="login-box">
        <h1>☁️ K8s Survival Camp</h1>
        <p className="login-subtitle">
          {isRegisterMode ? '새 계정을 만들어주세요' : '터미널에 접속하려면 로그인하세요'}
        </p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">사용자명</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="student1"
              required
              disabled={loading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">비밀번호</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              disabled={loading}
            />
          </div>

          {isRegisterMode && (
            <div className="form-group">
              <label htmlFor="confirmPassword">비밀번호 확인</label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                required
                disabled={loading}
              />
            </div>
          )}

          {error && <div className="error-message">{error}</div>}

          <button type="submit" className="login-button" disabled={loading}>
            {loading ? (isRegisterMode ? '가입 중...' : '로그인 중...') : (isRegisterMode ? '회원가입' : '로그인')}
          </button>
        </form>

        <div className="login-footer">
          <button className="toggle-mode-button" onClick={toggleMode} disabled={loading}>
            {isRegisterMode ? '이미 계정이 있으신가요? 로그인' : '계정이 없으신가요? 회원가입'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default Login
