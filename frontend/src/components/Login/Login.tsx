import React, { useState } from 'react'
import { createTerminalSession, login, register } from '../../services/api'
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

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(null)
    setLoading(true)

    try {
      if (isRegisterMode) {
        if (password !== confirmPassword) {
          setError('비밀번호가 일치하지 않습니다.')
          return
        }

        if (password.length < 6) {
          setError('비밀번호는 최소 6자 이상이어야 합니다.')
          return
        }

        await register(username, password)
      }

      const loginResponse = await login(username, password)
      const session = await createTerminalSession(loginResponse.access_token)
      onLoginSuccess(loginResponse.access_token, session.id, session.namespace)
    } catch (err) {
      setError(err instanceof Error ? err.message : isRegisterMode ? '회원가입에 실패했습니다.' : '로그인에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const toggleMode = () => {
    setIsRegisterMode((current) => !current)
    setError(null)
    setPassword('')
    setConfirmPassword('')
  }

  return (
    <div className="login-container">
      <div className="login-box">
        <span className="login-eyebrow">OPS TRAINING / ACCESS GATE</span>
        <h1>K8s Survival Camp</h1>
        <p className="login-subtitle">
          {isRegisterMode ? '새 계정을 만들어주세요.' : '터미널에 접속하려면 로그인하세요.'}
        </p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">사용자명</label>
            <input id="username" type="text" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="student1" required disabled={loading} />
          </div>
          <div className="form-group">
            <label htmlFor="password">비밀번호</label>
            <input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="비밀번호 입력" required disabled={loading} />
          </div>
          {isRegisterMode && (
            <div className="form-group">
              <label htmlFor="confirmPassword">비밀번호 확인</label>
              <input id="confirmPassword" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="비밀번호 다시 입력" required disabled={loading} />
            </div>
          )}
          {error && <div className="error-message">{error}</div>}
          <button type="submit" className="login-button" disabled={loading}>
            {loading ? '처리 중...' : isRegisterMode ? '회원가입' : '로그인'}
          </button>
        </form>

        <div className="login-footer">
          <button className="toggle-mode-button" type="button" onClick={toggleMode} disabled={loading}>
            {isRegisterMode ? '이미 계정이 있으신가요? 로그인' : '계정이 없으신가요? 회원가입'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default Login
