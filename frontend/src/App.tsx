import { useCallback, useEffect, useState } from 'react'
import Login from './components/Login/Login'
import MissionList from './components/Mission/MissionList'
import OnboardingTour, { TourStep } from './components/Onboarding/OnboardingTour'
import DashboardOverview from './components/Profile/DashboardOverview'
import ProfileDetails from './components/Profile/ProfileDetails'
import EnvironmentRoadmap from './components/Environment/EnvironmentRoadmap'
import EnvironmentTabs from './components/Environment/EnvironmentTabs'
import Terminal from './components/Terminal/Terminal'
import { getEnvironmentMeta, isSelectableStatus } from './config/environments'
import {
  ActiveAttemptSummary,
  DEFAULT_ENVIRONMENT,
  EnvironmentId,
  EnvironmentItem,
  isEnvironmentId,
} from './types/training'
import {
  AUTH_EXPIRED_EVENT,
  createTerminalSession,
  getEnvironments,
  getProfile,
  logoutUser,
  UserProfileResponse,
} from './services/api'
import './App.css'

type WorkspaceTab = 'missions' | 'terminal'

/** 사용자별 마지막 선택 환경. 계획서에 정해진 키를 그대로 쓴다. */
const ENVIRONMENT_STORAGE_KEY = 'afterfail:environment:v1'

const GRAFANA_BASE_URL = import.meta.env.VITE_GRAFANA_BASE_URL || 'http://localhost:3001'
const PROMETHEUS_BASE_URL = import.meta.env.VITE_PROMETHEUS_BASE_URL || 'http://localhost:9090'
const DASHBOARD_UID = 'k8s-survival-overview'
const GRAFANA_DATA_POLL_INTERVAL_MS = 1000
const GRAFANA_DATA_FALLBACK_FAILURES = 3
const INTRO_TOUR_STORAGE_KEY = 'afterfail:introTour:v1'
const MISSION_TOUR_STORAGE_KEY = 'afterfail:missionTour:v1'
const scopedStorageKey = (key: string, scope: string | null) => `${key}:${scope || 'anonymous'}`

const INTRO_TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="profile"]',
    eyebrow: 'TOUR / WELCOME',
    title: '학습 현황과 세션 정보',
    body: '상단에서는 프로필, 점수, 현재 실습 namespace를 확인할 수 있어요. 프로필을 열면 완료한 미션과 학습 기록도 볼 수 있습니다.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="env-tabs"]',
    eyebrow: 'TOUR / ENVIRONMENT',
    title: '훈련 환경 선택',
    body: 'Kubernetes 훈련이 먼저 열려 있습니다. Docker와 Linux는 준비가 끝나면 탭이 열리고, Application·DB는 후속 연구 영역입니다.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="mission-list"]',
    eyebrow: 'TOUR / MISSIONS',
    title: '미션을 고르고 시작',
    body: '왼쪽 목록에서 장애 상황을 선택하면 실제 조사와 복구 흐름이 시작됩니다. 잠긴 미션은 앞 단계 완료 후 열립니다.',
    placement: 'right',
  },
  {
    target: '[data-tour="field-guide"]',
    eyebrow: 'TOUR / FIELD GUIDE',
    title: '시작 전 가이드',
    body: '미션이 없을 때는 오른쪽에 조사 순서와 자주 쓰는 kubectl 명령 힌트가 표시됩니다.',
    placement: 'left',
  },
  {
    target: '[data-tour="learning-dashboard"]',
    eyebrow: 'TOUR / DASHBOARD',
    title: '학습 대시보드',
    body: '아직 미션을 시작하지 않은 상태에서는 진행률과 기록을 볼 수 있고, 미션 중에는 관측 대시보드로 바뀝니다.',
    placement: 'left',
  },
]

const MISSION_TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="mission-progress"]',
    eyebrow: 'MISSION TOUR / STATUS',
    title: '미션 진행 상태',
    body: '남은 시간, 현재 점수, 힌트 사용 횟수를 확인하고 완료 확인, 힌트 사용, 포기 같은 액션을 실행할 수 있어요.',
    placement: 'right',
  },
  {
    target: '[data-tour="terminal"]',
    eyebrow: 'MISSION TOUR / TERMINAL',
    title: '터미널에서 원인 조사',
    body: '여기에서 kubectl 명령을 입력해 Pod, Service, Deployment 상태를 조사하고 복구 명령을 실행합니다.',
    placement: 'right',
  },
  {
    target: '[data-tour="grafana"]',
    eyebrow: 'MISSION TOUR / OBSERVE',
    title: 'Grafana로 상태 관측',
    body: '장애 지표와 복구 상태를 보면서 명령 결과가 실제 환경에 반영되는지 확인할 수 있습니다.',
    placement: 'left',
  },
]

const getGrafanaUrl = (namespace: string | null) =>
  `${GRAFANA_BASE_URL}/d/${DASHBOARD_UID}/afterfail-incident-triage?orgId=1&kiosk&refresh=5s&var-namespace=${encodeURIComponent(namespace || '.*')}`

type PrometheusQueryResponse = {
  status: string
  data?: {
    result?: Array<{
      value?: [number, string]
    }>
  }
}

const escapePrometheusLabelValue = (value: string) =>
  value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')

const hasPrometheusResponse = (payload: PrometheusQueryResponse) =>
  payload.status === 'success' && Array.isArray(payload.data?.result)

const getGrafanaDataProbeUrl = (namespace: string | null) => {
  const namespaceMatcher = escapePrometheusLabelValue(namespace || '.*')
  const query = `sum(kube_pod_status_phase{namespace=~"${namespaceMatcher}"})`
  return `${PROMETHEUS_BASE_URL}/api/v1/query?query=${encodeURIComponent(query)}`
}

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [namespace, setNamespace] = useState<string | null>(null)
  const [profile, setProfile] = useState<UserProfileResponse | null>(null)
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('missions')
  const [environments, setEnvironments] = useState<EnvironmentItem[] | null>(null)
  const [environmentsError, setEnvironmentsError] = useState<string | null>(null)
  const [activeEnvironment, setActiveEnvironment] = useState<EnvironmentId | null>(null)
  const [isProfileOpen, setIsProfileOpen] = useState(false)
  const [isProfileLoading, setIsProfileLoading] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [activeAttempt, setActiveAttempt] = useState<ActiveAttemptSummary | null>(null)
  const [isGrafanaFrameReady, setIsGrafanaFrameReady] = useState(false)
  const [isGrafanaDataReady, setIsGrafanaDataReady] = useState(false)
  const [activeTour, setActiveTour] = useState<'intro' | 'mission' | null>(null)
  const [hasSeenIntroTour, setHasSeenIntroTour] = useState(() => localStorage.getItem(INTRO_TOUR_STORAGE_KEY) === 'done')
  const [hasSeenMissionTour, setHasSeenMissionTour] = useState(() => localStorage.getItem(MISSION_TOUR_STORAGE_KEY) === 'done')
  const accountStorageScope = profile?.id || namespace
  const grafanaUrl = getGrafanaUrl(namespace)
  const hasActiveAttempt = activeAttempt !== null
  const isGrafanaLoading = hasActiveAttempt && (!isGrafanaFrameReady || !isGrafanaDataReady)
  const activeEnvironmentItem = environments?.find((item) => item.id === activeEnvironment) ?? null
  const isActiveEnvironmentDegraded = activeEnvironmentItem?.status === 'degraded'

  const clearAuthState = useCallback(() => {
    setToken(null)
    setSessionId(null)
    setNamespace(null)
    setProfile(null)
    setActiveAttempt(null)
    setEnvironments(null)
    setEnvironmentsError(null)
    setActiveEnvironment(null)
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

  const loadEnvironments = useCallback(async () => {
    if (!token) return

    setEnvironmentsError(null)
    try {
      setEnvironments(await getEnvironments(token))
    } catch (error) {
      console.error('환경 목록 조회 실패:', error)
      setEnvironments(null)
      setEnvironmentsError(error instanceof Error ? error.message : '환경 목록을 불러오지 못했습니다')
    }
  }, [token])

  useEffect(() => {
    void loadEnvironments()
  }, [loadEnvironments])

  /**
   * 활성 환경 확정. 우선순위는
   * ① 서버가 알려준 활성 attempt 의 환경 (실행 대상의 원본은 서버다)
   * ② 사용자별 저장값 ③ kubernetes ④ 첫 선택 가능 환경 ⑤ 없음
   * 이다. attempt 가 끝나면 다시 저장값으로 돌아온다.
   */
  useEffect(() => {
    if (!environments) return

    if (activeAttempt) {
      setActiveEnvironment(activeAttempt.environment)
      return
    }

    const selectable = environments.filter((item) => isSelectableStatus(item.status)).map((item) => item.id)
    const saved = accountStorageScope
      ? localStorage.getItem(scopedStorageKey(ENVIRONMENT_STORAGE_KEY, accountStorageScope))
      : null

    if (saved && isEnvironmentId(saved) && selectable.includes(saved)) {
      setActiveEnvironment(saved)
      return
    }
    setActiveEnvironment(selectable.includes(DEFAULT_ENVIRONMENT) ? DEFAULT_ENVIRONMENT : selectable[0] ?? null)
  }, [accountStorageScope, activeAttempt, environments])

  useEffect(() => {
    if (!activeEnvironment || !accountStorageScope) return
    localStorage.setItem(scopedStorageKey(ENVIRONMENT_STORAGE_KEY, accountStorageScope), activeEnvironment)
  }, [accountStorageScope, activeEnvironment])

  useEffect(() => {
    if (!accountStorageScope) return
    setHasSeenIntroTour(localStorage.getItem(scopedStorageKey(INTRO_TOUR_STORAGE_KEY, accountStorageScope)) === 'done')
    setHasSeenMissionTour(localStorage.getItem(scopedStorageKey(MISSION_TOUR_STORAGE_KEY, accountStorageScope)) === 'done')
  }, [accountStorageScope])

  useEffect(() => {
    const timeout = window.setTimeout(() => window.dispatchEvent(new Event('resize')), 0)
    return () => window.clearTimeout(timeout)
  }, [activeTab])

  useEffect(() => {
    if (!token || !sessionId || hasSeenIntroTour || isProfileOpen || activeTour) return
    setActiveTab('missions')
    const timer = window.setTimeout(() => setActiveTour('intro'), 450)
    return () => window.clearTimeout(timer)
  }, [activeTour, hasSeenIntroTour, isProfileOpen, sessionId, token])

  useEffect(() => {
    if (!token || !sessionId || !hasActiveAttempt || hasSeenMissionTour || activeTour) return
    setActiveTab(window.innerWidth <= 768 ? 'missions' : 'terminal')
    const timer = window.setTimeout(() => setActiveTour('mission'), 650)
    return () => window.clearTimeout(timer)
  }, [activeTour, hasActiveAttempt, hasSeenMissionTour, sessionId, token])

  useEffect(() => {
    setIsGrafanaFrameReady(false)
    setIsGrafanaDataReady(false)
  }, [grafanaUrl, hasActiveAttempt])

  useEffect(() => {
    if (!hasActiveAttempt) return

    let cancelled = false
    let failures = 0
    let intervalId: number | undefined

    const markDataReady = () => {
      if (cancelled) return
      setIsGrafanaDataReady(true)
      if (intervalId) window.clearInterval(intervalId)
    }

    const probeGrafanaData = async () => {
      try {
        const response = await fetch(getGrafanaDataProbeUrl(namespace), { cache: 'no-store' })
        if (!response.ok) throw new Error(`Prometheus responded with ${response.status}`)

        const payload = await response.json() as PrometheusQueryResponse
        if (hasPrometheusResponse(payload)) markDataReady()
      } catch (error) {
        failures += 1
        console.warn('Grafana data readiness probe failed:', error)
        if (isGrafanaFrameReady && failures >= GRAFANA_DATA_FALLBACK_FAILURES) markDataReady()
      }
    }

    void probeGrafanaData()
    intervalId = window.setInterval(probeGrafanaData, GRAFANA_DATA_POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      if (intervalId) window.clearInterval(intervalId)
    }
  }, [grafanaUrl, hasActiveAttempt, isGrafanaFrameReady, namespace])

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

  const finishActiveTour = () => {
    if (activeTour === 'intro') {
      localStorage.setItem(scopedStorageKey(INTRO_TOUR_STORAGE_KEY, accountStorageScope), 'done')
      setHasSeenIntroTour(true)
    }
    if (activeTour === 'mission') {
      localStorage.setItem(scopedStorageKey(MISSION_TOUR_STORAGE_KEY, accountStorageScope), 'done')
      setHasSeenMissionTour(true)
    }
    setActiveTour(null)
  }

  const replayIntroTour = () => {
    setIsProfileOpen(false)
    setActiveTab('missions')
    setActiveTour('intro')
  }

  const handleTourStepChange = (step: TourStep) => {
    if (activeTour !== 'mission') return
    if (step.target === '[data-tour="mission-progress"]') setActiveTab('missions')
    if (step.target === '[data-tour="terminal"]' || step.target === '[data-tour="grafana"]') setActiveTab('terminal')
  }

  const handleActiveAttemptChange = useCallback((summary: ActiveAttemptSummary | null) => {
    setActiveAttempt(summary)
    if (summary) {
      setIsGrafanaFrameReady(false)
      setIsGrafanaDataReady(false)
    }
  }, [])

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
            <button className="profile-summary" type="button" onClick={() => setIsProfileOpen(true)} data-tour="profile">
              {profile.username} | 완료 {profile.missions_completed} | 총점 {profile.total_score}
            </button>
          )}
          {namespace && <span className="namespace-badge">Namespace: {namespace.startsWith('user-') ? namespace.slice(0, 20) + '...' : namespace}</span>}
          <button className="tour-replay-button" type="button" onClick={replayIntroTour}>GUIDE</button>
          <button className="logout-button" type="button" onClick={handleLogout}>로그아웃</button>
        </div>
      </header>
      <main className="app-main">
        {isProfileOpen && profile ? (
          <ProfileDetails token={token} profile={profile} loading={isProfileLoading} onBack={() => setIsProfileOpen(false)} onRefresh={() => void loadProfile()} />
        ) : (
          <div className="workspace">
            {environmentsError ? (
              <section className="env-notice env-notice-error" role="alert">
                <span className="env-notice-title">환경 목록을 불러오지 못했습니다</span>
                <p>{environmentsError}</p>
                <button className="env-notice-action" type="button" onClick={() => void loadEnvironments()}>
                  다시 시도
                </button>
              </section>
            ) : !environments ? (
              <section className="env-notice" role="status" aria-live="polite">
                <span className="env-notice-title">훈련 환경 목록을 불러오는 중...</span>
              </section>
            ) : (
              <>
                <EnvironmentTabs
                  items={environments}
                  active={activeEnvironment}
                  lockedTo={activeAttempt?.environment ?? null}
                  onSelect={setActiveEnvironment}
                />

                {activeAttempt && (
                  <p className="env-notice env-notice-lock" role="status">
                    진행 중인 {getEnvironmentMeta(activeAttempt.environment).label} 훈련이 있어 다른 환경으로 전환할 수 없습니다.
                    미션을 완료하거나 포기하면 해제됩니다.
                  </p>
                )}

                {isActiveEnvironmentDegraded && (
                  <p className="env-notice env-notice-degraded" role="alert">
                    이 환경은 일부 기능이 불안정한 상태입니다. 명령은 실행되지만 검증 결과가 늦게 반영될 수 있습니다.
                  </p>
                )}

                {!activeEnvironment ? (
                  <section className="env-notice env-notice-empty" id="env-panel" role="tabpanel">
                    <span className="env-notice-title">지금 선택할 수 있는 훈련 환경이 없습니다</span>
                    <p>모든 환경이 준비 중이거나 사용 중지 상태입니다.</p>
                    <EnvironmentRoadmap items={environments} />
                  </section>
                ) : (
                  <>
                <nav className="workspace-tabs" aria-label="작업 화면">
                  <button className={activeTab === 'missions' ? 'active' : ''} type="button" onClick={() => setActiveTab('missions')}>미션</button>
                  <button className={activeTab === 'terminal' ? 'active' : ''} type="button" onClick={() => setActiveTab('terminal')}>터미널</button>
                </nav>
                <div
                  className="app-layout"
                  id="env-panel"
                  role="tabpanel"
                  aria-labelledby={`env-tab-${activeEnvironment}`}
                >
                  <div className={`mission-section ${activeTab !== 'missions' ? 'mobile-hidden' : ''}`} data-tour="mission-list"><MissionList token={token} storageScope={accountStorageScope} environment={activeEnvironment} onActiveAttemptChange={handleActiveAttemptChange} /></div>
                  <div className={`terminal-section ${activeTab !== 'terminal' ? 'mobile-hidden' : ''}`}>
                    <div className="terminal-workspace">
                      {hasActiveAttempt ? (
                        <div className="terminal-tour-target" data-tour="terminal">
                          <Terminal sessionId={sessionId} token={token} namespace={namespace || undefined} />
                        </div>
                      ) : (
                        <section className="tutorial-panel" data-tour="field-guide">
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
                            <EnvironmentRoadmap items={environments} />
                          </div>
                        </section>
                      )}
                      <section className="grafana-panel" data-tour={hasActiveAttempt ? 'grafana' : 'learning-dashboard'}>
                        <div className="grafana-panel-header">
                          <span className="terminal-label">{hasActiveAttempt ? 'OBSERVABILITY / GRAFANA' : 'PROFILE / LEARNING DASHBOARD'}</span>
                          {hasActiveAttempt && <a href={grafanaUrl} target="_blank" rel="noreferrer">새 창</a>}
                        </div>
                        {hasActiveAttempt ? (
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
              </>
            )}
          </div>
        )}
      </main>
      <OnboardingTour
        run={Boolean(activeTour)}
        steps={activeTour === 'mission' ? MISSION_TOUR_STEPS : INTRO_TOUR_STEPS}
        onClose={finishActiveTour}
        onStepChange={handleTourStepChange}
      />
    </div>
  )
}

export default App
