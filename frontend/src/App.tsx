import { useCallback, useEffect, useState } from 'react'
import Login from './components/Login/Login'
import MissionList from './components/Mission/MissionList'
import DashboardOverview from './components/Profile/DashboardOverview'
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
type EnvTab = 'kubernetes' | 'docker' | 'linux' | 'application'

const ENV_TABS: { id: EnvTab; label: string; subtitle: string; wip: boolean }[] = [
  { id: 'kubernetes', label: 'Kubernetes', subtitle: '쿠버네티스 장애 대응', wip: false },
  { id: 'docker', label: 'Docker', subtitle: '컨테이너 운영', wip: true },
  { id: 'linux', label: 'Linux', subtitle: '시스템 관리', wip: true },
  { id: 'application', label: 'Application', subtitle: '앱 트러블슈팅', wip: true },
]

const GRAFANA_BASE_URL = import.meta.env.VITE_GRAFANA_BASE_URL || 'http://localhost:3001'
const DASHBOARD_UID = 'k8s-survival-overview'
const GRAFANA_DATA_WARMUP_MS = 5500

const getGrafanaUrl = (namespace: string | null) =>
  `${GRAFANA_BASE_URL}/d/${DASHBOARD_UID}/${DASHBOARD_UID}?orgId=1&kiosk&refresh=5s&var-namespace=${encodeURIComponent(namespace || '.*')}`

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [namespace, setNamespace] = useState<string | null>(null)
  const [profile, setProfile] = useState<UserProfileResponse | null>(null)
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('missions')
  const [activeEnvTab, setActiveEnvTab] = useState<EnvTab>('kubernetes')
  const [isProfileOpen, setIsProfileOpen] = useState(false)
  const [isProfileLoading, setIsProfileLoading] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [hasActiveMission, setHasActiveMission] = useState(false)
  const [isGrafanaFrameReady, setIsGrafanaFrameReady] = useState(false)
  const [isGrafanaDataReady, setIsGrafanaDataReady] = useState(false)
  const grafanaUrl = getGrafanaUrl(namespace)
  const isGrafanaLoading = hasActiveMission && (!isGrafanaFrameReady || !isGrafanaDataReady)

  const clearAuthState = useCallback(() => {
    setToken(null)
    setSessionId(null)
    setNamespace(null)
    setProfile(null)
    setHasActiveMission(false)
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

  useEffect(() => {
    setIsGrafanaFrameReady(false)
    setIsGrafanaDataReady(false)
  }, [grafanaUrl, hasActiveMission])

  useEffect(() => {
    if (!hasActiveMission || !isGrafanaFrameReady) return

    const timeout = window.setTimeout(() => setIsGrafanaDataReady(true), GRAFANA_DATA_WARMUP_MS)
    return () => window.clearTimeout(timeout)
  }, [grafanaUrl, hasActiveMission, isGrafanaFrameReady])

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
        <div className="brand-lockup">
          <span className="brand-index">OPS / 01</span>
          <h1>AfterFail</h1>
          <span className="brand-subtitle">Incident drill console</span>
        </div>
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
          <ProfileDetails token={token} profile={profile} loading={isProfileLoading} onBack={() => setIsProfileOpen(false)} onRefresh={() => void loadProfile()} />
        ) : (
          <div className="workspace">
            <nav className="env-tabs" aria-label="환경 선택">
              {ENV_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={`env-tab${activeEnvTab === tab.id ? ' active' : ''}${tab.wip ? ' wip' : ''}`}
                  onClick={() => setActiveEnvTab(tab.id)}
                >
                  <span className="env-tab-label">{tab.label}</span>
                  <span className="env-tab-sub">{tab.wip ? '개발 예정' : tab.subtitle}</span>
                </button>
              ))}
            </nav>

            {activeEnvTab !== 'kubernetes' ? (
              <div className="wip-screen">
                <div className="wip-content">
                  <span className="wip-eyebrow">COMING SOON / CAPSTONE 2</span>
                  <h2>{ENV_TABS.find((t) => t.id === activeEnvTab)?.label} 환경</h2>
                  <p>
                    {ENV_TABS.find((t) => t.id === activeEnvTab)?.subtitle} 훈련 환경은 현재 개발 중입니다.
                    <br />
                    캡스톤 2에서 만나볼 수 있습니다.
                  </p>
                  <div className="wip-roadmap">
                    <span>ROADMAP</span>
                    <ul>
                      {activeEnvTab === 'docker' && (
                        <>
                          <li>Docker Compose 서비스 장애 시뮬레이션</li>
                          <li>컨테이너 리소스 제한 실습</li>
                          <li>네트워크 격리 및 볼륨 마운트 문제 해결</li>
                        </>
                      )}
                      {activeEnvTab === 'linux' && (
                        <>
                          <li>프로세스 및 서비스 장애 대응</li>
                          <li>디스크 / 메모리 / CPU 포화 상태 복구</li>
                          <li>시스템 로그 분석 및 트러블슈팅</li>
                        </>
                      )}
                      {activeEnvTab === 'application' && (
                        <>
                          <li>애플리케이션 성능 저하 원인 분석</li>
                          <li>API 에러 패턴 및 데드락 해결</li>
                          <li>분산 추적 기반 병목 지점 탐지</li>
                        </>
                      )}
                    </ul>
                  </div>
                </div>
              </div>
            ) : (
              <>
                <nav className="workspace-tabs" aria-label="작업 화면">
                  <button className={activeTab === 'missions' ? 'active' : ''} type="button" onClick={() => setActiveTab('missions')}>미션</button>
                  <button className={activeTab === 'terminal' ? 'active' : ''} type="button" onClick={() => setActiveTab('terminal')}>터미널</button>
                </nav>
                <div className="app-layout">
                  <div className={`mission-section ${activeTab !== 'missions' ? 'mobile-hidden' : ''}`}><MissionList token={token} onActiveMissionChange={setHasActiveMission} /></div>
                  <div className={`terminal-section ${activeTab !== 'terminal' ? 'mobile-hidden' : ''}`}>
                    <div className="terminal-workspace">
                      {hasActiveMission ? (
                        <Terminal sessionId={sessionId} token={token} namespace={namespace || undefined} />
                      ) : (
                        <section className="tutorial-panel">
                          <div className="tutorial-panel-header">
                            <span className="terminal-label">GETTING STARTED / FIELD GUIDE</span>
                          </div>
                          <div className="tutorial-content">
                            <span className="tutorial-kicker">AfterFail</span>
                            <h2>장애를 직접 관찰하고 복구해 보세요.</h2>
                            <p>왼쪽 목록에서 미션을 시작하면 이 영역에 터미널이 열립니다. 오른쪽 대시보드와 Kubernetes 명령을 함께 사용해 원인을 찾아보세요.</p>
                            <div className="tutorial-steps">
                              <article>
                                <strong>01 / 미션 선택</strong>
                                <span>왼쪽에서 잠금 해제된 미션을 고르고 시작합니다.</span>
                              </article>
                              <article>
                                <strong>02 / 상태 조사</strong>
                                <span>Pod, Deployment, Service 상태와 이벤트를 차례로 확인합니다.</span>
                              </article>
                              <article>
                                <strong>03 / 복구 및 검증</strong>
                                <span>원인을 수정한 뒤 미션 패널에서 완료 확인을 실행합니다.</span>
                              </article>
                            </div>
                            <div className="tutorial-commands">
                              <span>INVESTIGATION STARTERS</span>
                              <code>kubectl get pods</code>
                              <code>kubectl get deployments</code>
                              <code>kubectl get services</code>
                              <code>kubectl get events --sort-by=.metadata.creationTimestamp</code>
                            </div>
                          </div>
                        </section>
                      )}
                      <section className="grafana-panel">
                        <div className="grafana-panel-header">
                          <span className="terminal-label">{hasActiveMission ? 'OBSERVABILITY / GRAFANA' : 'PROFILE / LEARNING DASHBOARD'}</span>
                          {hasActiveMission && <a href={grafanaUrl} target="_blank" rel="noreferrer">새 창</a>}
                        </div>
                        {hasActiveMission ? (
                          <div className="grafana-frame-wrap">
                            <iframe
                              className="grafana-frame"
                              src={grafanaUrl}
                              title="Grafana dashboard"
                              onLoad={() => setIsGrafanaFrameReady(true)}
                            />
                            {isGrafanaLoading && (
                              <div className="grafana-loading-overlay" role="status" aria-live="polite">
                                <strong>데이터 로딩중입니다..</strong>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="workspace-dashboard">
                            <DashboardOverview token={token} />
                          </div>
                        )}
                      </section>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

export default App
