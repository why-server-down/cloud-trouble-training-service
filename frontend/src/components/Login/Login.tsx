import React, { useState } from 'react'
import { login, createTerminalSession } from '../../services/api'
import './Login.css'

interface LoginProps {
  onLoginSuccess: (token: string, sessionId: string, namespace?: string) => void
}

const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      // 1. 로그인
      const loginResponse = await login(username, password)
      const token = loginResponse.access_token

      // 2. 터미널 세션 생성
      const sessionResponse = await createTerminalSession(token)
      const sessionId = sessionResponse.id
      const namespace = sessionResponse.namespace

      // 3. 성공 콜백
      onLoginSuccess(token, sessionId, namespace)
    } catch (err) {
      setError(err instanceof Error ? err.message : '로그인에 실패했습니다')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-box">
        <h1>☁️ K8s Survival Camp</h1>
        <p className="login-subtitle">터미널에 접속하려면 로그인하세요</p>

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

          {error && <div className="error-message">{error}</div>}

          <button type="submit" className="login-button" disabled={loading}>
            {loading ? '로그인 중...' : '로그인'}
          </button>
        </form>

        <div className="login-footer">
          <p>테스트 계정: student1 / pass123</p>
        </div>
      </div>
    </div>
  )
}

export default Login
