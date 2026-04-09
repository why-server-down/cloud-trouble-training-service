import { useEffect, useState } from 'react'
import Terminal from './components/Terminal/Terminal'
import Login from './components/Login/Login'
import MissionList from './components/Mission/MissionList'
import './App.css'

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [namespace, setNamespace] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // 컴포넌트 마운트 시 localStorage에서 토큰 복원
  useEffect(() => {
    const savedToken = localStorage.getItem('token')
    const savedSessionId = localStorage.getItem('sessionId')
    const savedNamespace = localStorage.getItem('namespace')

    if (savedToken && savedSessionId) {
      setToken(savedToken)
      setSessionId(savedSessionId)
      setNamespace(savedNamespace)
    }
    setIsLoading(false)
  }, [])

  const handleLoginSuccess = (newToken: string, newSessionId: string, newNamespace?: string) => {
    setToken(newToken)
    setSessionId(newSessionId)
    setNamespace(newNamespace || null)

    // localStorage에 저장
    localStorage.setItem('token', newToken)
    localStorage.setItem('sessionId', newSessionId)
    if (newNamespace) {
      localStorage.setItem('namespace', newNamespace)
    }
  }

  const handleLogout = () => {
    setToken(null)
    setSessionId(null)
    setNamespace(null)

    // localStorage에서 제거
    localStorage.removeItem('token')
    localStorage.removeItem('sessionId')
    localStorage.removeItem('namespace')
  }

  // 로딩 중
  if (isLoading) {
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh',
        background: '#1e1e1e',
        color: '#61dafb'
      }}>
        로딩 중...
      </div>
    )
  }

  // 로그인 전: 로그인 화면 표시
  if (!token || !sessionId) {
    return <Login onLoginSuccess={handleLoginSuccess} />
  }

  // 로그인 후: 미션 + 터미널 화면 표시
  return (
    <div className="app">
      <header className="app-header">
        <h1>☁️ K8s Survival Camp</h1>
        <div className="header-info">
          {namespace && (
            <span className="namespace-badge">
              Namespace: {namespace.startsWith('user-') ? namespace.slice(0, 20) + '...' : namespace}
            </span>
          )}
          <button className="logout-button" onClick={handleLogout}>
            로그아웃
          </button>
        </div>
      </header>
      <main className="app-main">
        <div className="app-layout">
          <div className="mission-section">
            <MissionList token={token} />
          </div>
          <div className="terminal-section">
            <Terminal sessionId={sessionId} token={token} namespace={namespace || undefined} />
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
