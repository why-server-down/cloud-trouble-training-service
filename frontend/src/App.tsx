import { useState } from 'react'
import Terminal from './components/Terminal/Terminal'
import Login from './components/Login/Login'
import './App.css'

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)

  const handleLoginSuccess = (newToken: string, newSessionId: string) => {
    setToken(newToken)
    setSessionId(newSessionId)
  }

  const handleLogout = () => {
    setToken(null)
    setSessionId(null)
  }

  // 로그인 전: 로그인 화면 표시
  if (!token || !sessionId) {
    return <Login onLoginSuccess={handleLoginSuccess} />
  }

  // 로그인 후: 터미널 화면 표시
  return (
    <div className="app">
      <header className="app-header">
        <h1>☁️ K8s Survival Camp - Terminal</h1>
        <div className="header-info">
          <span className="namespace-badge">Session: {sessionId.slice(0, 8)}...</span>
          <button className="logout-button" onClick={handleLogout}>
            로그아웃
          </button>
        </div>
      </header>
      <main className="app-main">
        <Terminal sessionId={sessionId} token={token} />
      </main>
    </div>
  )
}

export default App
