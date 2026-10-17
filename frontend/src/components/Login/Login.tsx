import React, { useEffect, useRef, useState } from 'react'
import { login, register } from '../../services/api'
import './Login.css'

interface LoginProps {
  /**
   * 터미널 세션은 여기서 만들지 않는다 (FE-04). 환경이 정해지고 터미널이
   * 필요해진 뒤에 만들므로, 로그인은 토큰만 넘긴다.
   */
  onLoginSuccess: (token: string) => void
}

const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
  const [isRegisterMode, setIsRegisterMode] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const errorRef = useRef<HTMLDivElement | null>(null)

  /*
   * 모바일에서 키보드가 열려 있으면 화면이 짧아 오류가 접힌 아래에 생길 수 있다.
   * 스크린리더는 alert 로 읽지만, 눈으로 보는 사용자를 위해 오류를 화면 안으로 당긴다 (FE-28).
   */
  useEffect(() => {
    if (error) errorRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [error])

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
      onLoginSuccess(loginResponse.access_token)
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
      <div className="login-column">
        <header className="login-brand">
          <h1>AfterFail</h1>
          <p>실제 장애를 직접 복구하며 배우는 DevOps 훈련</p>
        </header>

        <div className="login-box">
          <h2 className="login-title">{isRegisterMode ? '새 계정 만들기' : '로그인'}</h2>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="username">사용자명</label>
              {/* 모바일 키보드가 첫 글자를 대문자로 바꾸거나 자동 수정하지 않게 한다. */}
              <input
                id="username"
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="student1"
                required
                disabled={loading}
                autoComplete="username"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                enterKeyHint="next"
              />
            </div>
            <div className="form-group">
              <label htmlFor="password">비밀번호</label>
              {/* 회원가입에서는 확인 칸이 남아 있어 '다음', 로그인에서는 바로 제출하는 '이동'이다. */}
              <input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={isRegisterMode ? '6자 이상' : '비밀번호 입력'}
                required
                disabled={loading}
                autoComplete={isRegisterMode ? 'new-password' : 'current-password'}
                enterKeyHint={isRegisterMode ? 'next' : 'go'}
              />
            </div>
            {isRegisterMode && (
              <div className="form-group">
                <label htmlFor="confirmPassword">비밀번호 확인</label>
                <input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="비밀번호 다시 입력"
                  required
                  disabled={loading}
                  autoComplete="new-password"
                  enterKeyHint="go"
                />
              </div>
            )}
            {/* 로그인 오류는 스크린리더가 바로 읽도록 alert 로 둔다 (설계 문서 8). */}
            {error && (
              <div className="error-message" role="alert" ref={errorRef}>
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <circle cx="8" cy="8" r="6.25" />
                  <path d="M8 4.75v3.75M8 11.1v.15" />
                </svg>
                <span>{error}</span>
              </div>
            )}
            <button type="submit" className="ui-button primary login-button" disabled={loading}>
              {loading ? '처리 중...' : isRegisterMode ? '회원가입' : '로그인'}
            </button>
          </form>
        </div>

        <button className="ui-button plain toggle-mode-button" type="button" onClick={toggleMode} disabled={loading}>
          {isRegisterMode ? '이미 계정이 있으신가요?' : '계정이 없으신가요?'}{' '}
          <span>{isRegisterMode ? '로그인' : '회원가입'}</span>
        </button>
      </div>
    </div>
  )
}

export default Login
