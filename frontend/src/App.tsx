import { useCallback, useEffect, useState } from 'react'
import Login from './components/Login/Login'
import MissionList from './components/Mission/MissionList'
import ProfileDetails from './components/Profile/ProfileDetails'
import Terminal from './components/Terminal/Terminal'
import {
  AUTH_EXPIRED_EVENT,
  createTerminalSession,
  getProfile,
  logoutUser,
  UserProfileResponse,
} from './services/api'
import './App.css'

type WorkspaceTab = 'missions' | 'terminal'

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [namespace, setNamespace] = useState<string | null>(null)
  const [profile, setProfile] = useState<UserProfileResponse | null>(null)
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('missions')
  const [isProfileOpen, setIsProfileOpen] = useState(false)
  const [isProfileLoading, setIsProfileLoading] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  const clearAuthState = useCallback(() => {
    setToken(null)
    setSessionId(null)
    setNamespace(null)
    setProfile(null)
    setActiveTab('missions')
    setIsProfileOpen(false)
    localStorage.removeItem('token')
    localStorage.removeItem('sessionId')
    localStorage.removeItem('namespace')
  }, [])

  useEffect(() => {
    const savedToken = localStorage.getItem('token')
    const savedNamespace = localStorage.getItem('namespace')

    const restoreSession = async () => {
      if (!savedToken) {
        setIsLoading(false)
        return
      }

      try {
        const session = await createTerminalSession(savedToken)
        setToken(savedToken)
        setSessionId(session.id)
        setNamespace(session.namespace || savedNamespace)
        localStorage.setItem('sessionId', session.id)
        localStorage.setItem('namespace', session.namespace)
      } catch (error) {
        console.error('터미널 세션 복원 실패:', error)
        clearAuthState()
      } finally {
        setIsLoading(false)
      }
    }

    void restoreSession()
  }, [clearAuthState])

  useEffect(() => {
    window.addEventListener(AUTH_EXPIRED_EVENT, clearAuthState)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, clearAuthState)
  }, [clearAuthState])

  const loadProfile = useCallback(async () => {
    if (!token) return

    setIsProfileLoading(true)
    try {
      setProfile(await getProfile(token))
    } catch (error) {
      console.error('프로필 조회 실패:', error)
    } finally {
      setIsProfileLoading(false)
    }
  }, [token])

  useEffect(() => {
    if (!token) return
    void loadProfile()
    const interval = window.setInterval(loadProfile, 15000)
    return () => window.clearInterval(interval)
  }, [loadProfile, token])

  useEffect(() => {
    const timeout = window.setTimeout(() => window.dispatchEvent(new Event('resize')), 0)
    return () => window.clearTimeout(timeout)
  }, [activeTab])

  const handleLoginSuccess = (newToken: string, newSessionId: string, newNamespace?: string) => {
    setToken(newToken)
    setSessionId(newSessionId)
    setNamespace(newNamespace || null)
    localStorage.setItem('token', newToken)
    localStorage.setItem('sessionId', newSessionId)
    if (newNamespace) localStorage.setItem('namespace', newNamespace)
  }

  const handleLogout = async () => {
    if (token) {
      try {
        await logoutUser(token)
      } catch (error) {
        console.error('로그아웃 요청 실패:', error)
      }
    }
    clearAuthState()
  }

  if (isLoading) return <div className="app-loading">불러오는 중...</div>
  if (!token || !sessionId) return <Login onLoginSuccess={handleLoginSuccess} />

  return (
    <div className="app">
      <header className="app-header">
        <h1>K8s Survival Camp</h1>
        <div className="header-info">
          {profile && (
            <button className="profile-summary" type="button" onClick={() => setIsProfileOpen(true)}>
              {profile.username} | 완료 {profile.missions_completed} | 총점 {profile.total_score}
            </button>
          )}
          {namespace && <span className="namespace-badge">Namespace: {namespace.startsWith('user-') ? namespace.slice(0, 20) + '...' : namespace}</span>}
          <button className="logout-button" type="button" onClick={handleLogout}>로그아웃</button>
        </div>
      </header>
      <main className="app-main">
        {isProfileOpen && profile ? (
          <ProfileDetails profile={profile} loading={isProfileLoading} onBack={() => setIsProfileOpen(false)} onRefresh={() => void loadProfile()} />
        ) : (
          <div className="workspace">
            <nav className="workspace-tabs" aria-label="작업 화면">
              <button className={activeTab === 'missions' ? 'active' : ''} type="button" onClick={() => setActiveTab('missions')}>미션</button>
              <button className={activeTab === 'terminal' ? 'active' : ''} type="button" onClick={() => setActiveTab('terminal')}>터미널</button>
            </nav>
            <div className="app-layout">
              <div className={`mission-section ${activeTab !== 'missions' ? 'mobile-hidden' : ''}`}><MissionList token={token} /></div>
              <div className={`terminal-section ${activeTab !== 'terminal' ? 'mobile-hidden' : ''}`}><Terminal sessionId={sessionId} token={token} namespace={namespace || undefined} /></div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
