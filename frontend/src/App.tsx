import { useCallback, useEffect, useRef, useState } from 'react'
import Login from './components/Login/Login'
import MissionList from './components/Mission/MissionList'
import OnboardingTour, { TourStep } from './components/Onboarding/OnboardingTour'
import DashboardOverview from './components/Profile/DashboardOverview'
import ProfileDetails from './components/Profile/ProfileDetails'
import EnvironmentRoadmap from './components/Environment/EnvironmentRoadmap'
import EnvironmentTabs from './components/Environment/EnvironmentTabs'
import Terminal from './components/Terminal/Terminal'
import {
  getEnvironmentMeta,
  getEnvironmentTerminal,
  getGrafanaDataProbeUrl,
  getGrafanaUrl,
  isSelectableStatus,
} from './config/environments'
import {
  ActiveAttemptSummary,
  DEFAULT_ENVIRONMENT,
  EnvironmentId,
  EnvironmentItem,
  isEnvironmentId,
} from './types/training'
import {
  AUTH_EXPIRED_EVENT,
  getEnvironments,
  getProfile,
  logoutUser,
  UserProfileResponse,
} from './services/api'
import { useEnvironmentSessions } from './hooks/useEnvironmentSessions'
import './App.css'

type WorkspaceTab = 'missions' | 'terminal'

/** 사용자별 마지막 선택 환경. 계획서에 정해진 키를 그대로 쓴다. */
const ENVIRONMENT_STORAGE_KEY = 'afterfail:environment:v1'

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

type PrometheusQueryResponse = {
  status: string
  data?: {
    result?: Array<{
      value?: [number, string]
    }>
  }
}

const hasPrometheusResponse = (payload: PrometheusQueryResponse) =>
  payload.status === 'success' && Array.isArray(payload.data?.result)

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [profile, setProfile] = useState<UserProfileResponse | null>(null)
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('missions')
  const [environments, setEnvironments] = useState<EnvironmentItem[] | null>(null)
  const [environmentsError, setEnvironmentsError] = useState<string | null>(null)
  const [activeEnvironment, setActiveEnvironment] = useState<EnvironmentId | null>(null)
  const [isProfileOpen, setIsProfileOpen] = useState(false)
  const [isProfileLoading, setIsProfileLoading] = useState(false)
  /**
   * 프로필 조회가 끝났는가(성공·실패 무관). 저장된 환경은 사용자별 키에 있어
   * 프로필이 와야 읽을 수 있다. 실패해도 true 로 둔다 — 영원히 터미널을
   * 못 여는 편이 더 나쁘다.
   */
  const [isAccountScopeResolved, setIsAccountScopeResolved] = useState(false)
  /** `activeEnvironment` 를 마지막으로 계산할 때 쓴 계정 범위. */
  const [environmentScope, setEnvironmentScope] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [activeAttempt, setActiveAttempt] = useState<ActiveAttemptSummary | null>(null)
  const [isGrafanaFrameReady, setIsGrafanaFrameReady] = useState(false)
  const [isGrafanaDataReady, setIsGrafanaDataReady] = useState(false)
  /**
   * Prometheus probe 가 계속 실패해 iframe load 만으로 ready 처리한 경우 (FE-08).
   * 화면은 열어주되 "지표가 실제로 들어오는지 확인하지 못했다"는 사실을 숨기지 않는다.
   */
  const [isObservabilityDegraded, setIsObservabilityDegraded] = useState(false)
  /**
   * 대시보드 갱신 키 (FE-15). 미션 완료 때만 단조 증가한다.
   * 같은 attempt 의 완료 이벤트가 두 번 와도 한 번만 올린다.
   */
  const [dashboardRefreshKey, setDashboardRefreshKey] = useState(0)
  const lastCompletedAttemptRef = useRef<string | null>(null)
  const [activeTour, setActiveTour] = useState<'intro' | 'mission' | null>(null)
  const [hasSeenIntroTour, setHasSeenIntroTour] = useState(() => localStorage.getItem(INTRO_TOUR_STORAGE_KEY) === 'done')
  const [hasSeenMissionTour, setHasSeenMissionTour] = useState(() => localStorage.getItem(MISSION_TOUR_STORAGE_KEY) === 'done')
  const { sessionOf, stateOf, ensure, retry, closeAll } = useEnvironmentSessions(token)

  const hasActiveAttempt = activeAttempt !== null
  /**
   * 세션을 만들 환경. 활성 attempt 가 있으면 그 환경이 곧 실행 환경이므로
   * `activeEnvironment` state 가 서버 값을 따라잡기를 기다리지 않는다 —
   * 기다리면 그 한 렌더 동안 엉뚱한 환경의 샌드박스를 하나 더 만든다.
   */
  const sessionEnvironment = activeAttempt?.environment ?? activeEnvironment
  const activeSession = sessionOf(sessionEnvironment)
  const activeSessionState = stateOf(sessionEnvironment)
  /** namespace 는 세션 응답에서만 온다. 세션을 지연 생성하므로 그 전에는 알 수 없다. */
  const namespace = activeSession?.namespace ?? null
  const accountStorageScope = profile?.id ?? null
  /**
   * 관측 URL 은 활성 attempt 의 환경으로 만든다 (FE-08).
   * 대시보드가 없는 환경은 null 이 오고, 그때는 iframe 대신 안내를 띄운다 —
   * K8s 대시보드로 대체하면 사용자는 남의 환경 지표를 자기 것으로 읽는다.
   */
  const grafanaUrl = getGrafanaUrl(sessionEnvironment, namespace)
  const grafanaProbeUrl = getGrafanaDataProbeUrl(sessionEnvironment, namespace)
  const hasObservability = grafanaUrl !== null
  /** 관측 패널 문구에 쓰는 환경 이름. iframe title 에도 넣어 스크린리더가 구분할 수 있게 한다. */
  const observabilityLabel = sessionEnvironment ? getEnvironmentMeta(sessionEnvironment).label : ''
  /*
   * 미션 시작 전 field guide 는 선택된 환경 기준으로 그린다 (FE-09).
   * 예전에는 kubectl 명령이 하드코딩돼 Docker / Linux 탭에서도 그대로 보였다.
   */
  const fieldGuideTerminal = activeEnvironment ? getEnvironmentTerminal(activeEnvironment) : null
  /** 실행 파일이 고정된 환경만 이름을 문장에 넣는다. Linux 는 단일 바이너리가 없다. */
  const fieldGuideLabel = fieldGuideTerminal?.binary ?? null
  const fieldGuideStarters = fieldGuideTerminal?.investigationStarters ?? []
  const fieldGuideInvestigationHint = activeEnvironment
    ? getEnvironmentMeta(activeEnvironment).investigationHint
    : '현재 상태와 최근 변화를 차례로 확인합니다.'
  const isGrafanaLoading =
    hasActiveAttempt && hasObservability && (!isGrafanaFrameReady || !isGrafanaDataReady)
  const activeEnvironmentItem = environments?.find((item) => item.id === activeEnvironment) ?? null
  const isActiveEnvironmentDegraded = activeEnvironmentItem?.status === 'degraded'
  /**
   * 터미널 workspace 가 실제로 필요한 시점.
   * 로그인했다는 이유만으로는 세션을 만들지 않는다 (FE-04).
   */
  /**
   * 저장된 환경이 `activeEnvironment` 에 실제로 반영됐는가.
   * 프로필 도착만 보면 안 된다 — 프로필이 들어온 그 렌더에서는 복원 effect 가
   * 아직 돌지 않아 `activeEnvironment` 가 기본값이고, 그 값으로 세션을 만들면
   * 복원될 환경과 기본 환경 두 개가 생긴다.
   */
  const isEnvironmentSettled = isAccountScopeResolved && environmentScope === accountStorageScope
  const needsWorkspace = hasActiveAttempt || (activeTab === 'terminal' && isEnvironmentSettled)

  /** 완료 직후 profile 과 dashboard 를 한 번 갱신한다 (FE-15). */
  const handleAttemptCompleted = useCallback((attemptId: string) => {
    if (lastCompletedAttemptRef.current === attemptId) return
    lastCompletedAttemptRef.current = attemptId
    setDashboardRefreshKey((key) => key + 1)
  }, [])

  const clearAuthState = useCallback(() => {
    setToken(null)
    setProfile(null)
    setActiveAttempt(null)
    setEnvironments(null)
    setEnvironmentsError(null)
    setActiveEnvironment(null)
    setActiveTab('missions')
    setIsProfileOpen(false)
    setIsAccountScopeResolved(false)
    setEnvironmentScope(null)
    localStorage.removeItem('token')
    localStorage.removeItem('sessionId')
    localStorage.removeItem('namespace')
  }, [])

  /**
   * 토큰 복원. 예전에는 여기서 터미널 세션을 만들어 보고 실패하면 로그아웃시켰지만,
   * 세션 생성은 이제 환경이 정해지고 터미널이 필요해진 뒤의 일이다.
   * 샌드박스가 잠깐 준비되지 않았다고 로그인 자체를 잃으면 안 된다.
   */
  useEffect(() => {
    const savedToken = localStorage.getItem('token')
    if (savedToken) setToken(savedToken)
    // 환경별 세션으로 바뀌어 단일 키 저장은 의미가 없다. 예전 값이 남아 있으면 지운다.
    localStorage.removeItem('sessionId')
    localStorage.removeItem('namespace')
    setIsLoading(false)
  }, [])

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
      setIsAccountScopeResolved(true)
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

    const resolved = (): EnvironmentId | null => {
      if (activeAttempt) return activeAttempt.environment

      const selectable = environments.filter((item) => isSelectableStatus(item.status)).map((item) => item.id)
      const saved = accountStorageScope
        ? localStorage.getItem(scopedStorageKey(ENVIRONMENT_STORAGE_KEY, accountStorageScope))
        : null

      if (saved && isEnvironmentId(saved) && selectable.includes(saved)) return saved
      return selectable.includes(DEFAULT_ENVIRONMENT) ? DEFAULT_ENVIRONMENT : selectable[0] ?? null
    }

    setActiveEnvironment(resolved())
    setEnvironmentScope(accountStorageScope)
  }, [accountStorageScope, activeAttempt, environments])

  useEffect(() => {
    if (!activeEnvironment || !accountStorageScope) return
    localStorage.setItem(scopedStorageKey(ENVIRONMENT_STORAGE_KEY, accountStorageScope), activeEnvironment)
  }, [accountStorageScope, activeEnvironment])

  /** 선택된 환경의 터미널이 필요해진 순간에만 세션을 만든다. 이미 있으면 훅이 막는다. */
  useEffect(() => {
    if (!sessionEnvironment || !needsWorkspace) return
    ensure(sessionEnvironment)
  }, [ensure, needsWorkspace, sessionEnvironment])

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
    if (!token || hasSeenIntroTour || isProfileOpen || activeTour) return
    setActiveTab('missions')
    const timer = window.setTimeout(() => setActiveTour('intro'), 450)
    return () => window.clearTimeout(timer)
  }, [activeTour, hasSeenIntroTour, isProfileOpen, token])

  useEffect(() => {
    if (!token || !hasActiveAttempt || hasSeenMissionTour || activeTour) return
    setActiveTab(window.innerWidth <= 768 ? 'missions' : 'terminal')
    const timer = window.setTimeout(() => setActiveTour('mission'), 650)
    return () => window.clearTimeout(timer)
  }, [activeTour, hasActiveAttempt, hasSeenMissionTour, token])

  useEffect(() => {
    setIsGrafanaFrameReady(false)
    setIsGrafanaDataReady(false)
    setIsObservabilityDegraded(false)
  }, [grafanaUrl, hasActiveAttempt])

  useEffect(() => {
    /*
     * 미션이 없거나 이 환경에 대시보드가 없으면 probe 자체를 시작하지 않는다 (FE-08).
     * 예전에는 미션 종료 후에도 K8s 쿼리를 계속 던졌고, 대시보드가 없는 환경에서는
     * 아무도 읽지 않는 실패 로그만 1초마다 쌓였다.
     */
    if (!hasActiveAttempt || !grafanaProbeUrl) return

    let cancelled = false
    let failures = 0
    let intervalId: number | undefined

    const markDataReady = (degraded = false) => {
      if (cancelled) return
      setIsGrafanaDataReady(true)
      if (degraded) setIsObservabilityDegraded(true)
      if (intervalId) window.clearInterval(intervalId)
    }

    const probeGrafanaData = async () => {
      try {
        const response = await fetch(grafanaProbeUrl, { cache: 'no-store' })
        if (!response.ok) throw new Error(`Prometheus responded with ${response.status}`)

        const payload = await response.json() as PrometheusQueryResponse
        if (hasPrometheusResponse(payload)) markDataReady()
      } catch (error) {
        failures += 1
        console.warn('Grafana data readiness probe failed:', error)
        // iframe 은 떴으니 화면은 열어준다. 다만 degraded 로 표시한다.
        if (isGrafanaFrameReady && failures >= GRAFANA_DATA_FALLBACK_FAILURES) markDataReady(true)
      }
    }

    void probeGrafanaData()
    intervalId = window.setInterval(probeGrafanaData, GRAFANA_DATA_POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      if (intervalId) window.clearInterval(intervalId)
    }
  }, [grafanaProbeUrl, hasActiveAttempt, isGrafanaFrameReady])

  const handleLoginSuccess = (newToken: string) => {
    setToken(newToken)
    localStorage.setItem('token', newToken)
  }

  /**
   * 로그아웃. 샌드박스 정리와 로그아웃 요청은 best-effort 로 던져 두고
   * 화면은 즉시 로그인으로 되돌린다 — 정리 실패가 로그아웃을 막으면 안 된다.
   */
  const handleLogout = () => {
    const expiringToken = token
    void closeAll()
    if (expiringToken) {
      void logoutUser(expiringToken).catch((error) => console.error('로그아웃 요청 실패:', error))
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
  if (!token) return <Login onLoginSuccess={handleLoginSuccess} />

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
                  <div className={`mission-section ${activeTab !== 'missions' ? 'mobile-hidden' : ''}`} data-tour="mission-list"><MissionList token={token} storageScope={accountStorageScope} environment={activeEnvironment} onActiveAttemptChange={handleActiveAttemptChange} onAttemptCompleted={handleAttemptCompleted} /></div>
                  <div className={`terminal-section ${activeTab !== 'terminal' ? 'mobile-hidden' : ''}`}>
                    <div className="terminal-workspace">
                      {activeAttempt ? (
                        <div className="terminal-tour-target" data-tour="terminal">
                          {activeSession ? (
                            /*
                             * key 로 세션마다 새 Terminal 을 만든다. 환경을 바꾸면
                             * 이전 WebSocket·입력 queue 를 물려받은 인스턴스가 남지 않는다.
                             */
                            <Terminal
                              key={activeSession.id}
                              environment={activeAttempt.environment}
                              sessionId={activeSession.id}
                              token={token}
                              namespace={activeSession.namespace}
                            />
                          ) : activeSessionState.status === 'error' ? (
                            <section className="env-notice env-notice-error" role="alert">
                              <span className="env-notice-title">터미널 세션을 준비하지 못했습니다</span>
                              <p>{activeSessionState.message}</p>
                              <button
                                className="env-notice-action"
                                type="button"
                                onClick={() => retry(activeAttempt.environment)}
                              >
                                다시 시도
                              </button>
                            </section>
                          ) : (
                            <section className="env-notice" role="status" aria-live="polite">
                              <span className="env-notice-title">
                                {getEnvironmentMeta(activeAttempt.environment).label} 터미널 세션을 준비하는 중...
                              </span>
                            </section>
                          )}
                        </div>
                      ) : (
                        <section className="tutorial-panel" data-tour="field-guide">
                          <div className="tutorial-panel-header">
                            <span className="terminal-label">GETTING STARTED / FIELD GUIDE</span>
                          </div>
                          <div className="tutorial-content">
                            <span className="tutorial-kicker">AfterFail</span>
                            <h2>장애를 직접 관찰하고 복구해 보세요.</h2>
                            <p>
                              왼쪽 목록에서 미션을 시작하면 이 영역에 터미널이 열립니다.
                              {fieldGuideLabel
                                ? ` ${fieldGuideLabel} 명령으로 상태를 조사해 원인을 찾아보세요.`
                                : ' 터미널 명령으로 상태를 조사해 원인을 찾아보세요.'}
                            </p>
                            <div className="tutorial-steps">
                              <article>
                                <strong>01 / 미션 선택</strong>
                                <span>왼쪽에서 잠금 해제된 미션을 고르고 시작합니다.</span>
                              </article>
                              <article>
                                <strong>02 / 상태 조사</strong>
                                <span>{fieldGuideInvestigationHint}</span>
                              </article>
                              <article>
                                <strong>03 / 복구 및 검증</strong>
                                <span>원인을 수정한 뒤 미션 패널에서 완료 확인을 실행합니다.</span>
                              </article>
                            </div>
                            <div className="tutorial-commands">
                              <span>INVESTIGATION STARTERS</span>
                              {fieldGuideStarters.map((command) => (
                                <code key={command}>{command}</code>
                              ))}
                            </div>
                            <EnvironmentRoadmap items={environments} />
                          </div>
                        </section>
                      )}
                      <section className="grafana-panel" data-tour={hasActiveAttempt ? 'grafana' : 'learning-dashboard'}>
                        <div className="grafana-panel-header">
                          <span className="terminal-label">
                            {hasActiveAttempt
                              ? `OBSERVABILITY / ${observabilityLabel.toUpperCase()}`
                              : 'PROFILE / LEARNING DASHBOARD'}
                          </span>
                          {hasActiveAttempt && grafanaUrl && (
                            <a href={grafanaUrl} target="_blank" rel="noreferrer">새 창</a>
                          )}
                        </div>
                        {!hasActiveAttempt ? (
                          <div className="workspace-dashboard">
                            <DashboardOverview token={token} refreshKey={dashboardRefreshKey} />
                          </div>
                        ) : hasObservability && grafanaUrl ? (
                          <div className="grafana-frame-wrap">
                            <iframe
                              className="grafana-frame"
                              src={grafanaUrl}
                              title={`${observabilityLabel} Grafana dashboard`}
                              onLoad={() => setIsGrafanaFrameReady(true)}
                            />
                            {isGrafanaLoading && (
                              <div className="grafana-loading-overlay" role="status" aria-live="polite">
                                <strong>데이터 로딩중입니다..</strong>
                              </div>
                            )}
                            {!isGrafanaLoading && isObservabilityDegraded && (
                              <p className="grafana-degraded-note" role="status" aria-live="polite">
                                Prometheus 지표 확인에 실패했습니다. 대시보드는 열려 있지만 값이 비어
                                있을 수 있습니다. 터미널 조사와 미션 검증에는 영향이 없습니다.
                              </p>
                            )}
                          </div>
                        ) : (
                          /* 이 환경 전용 대시보드가 없다 (FE-08). 다른 환경 대시보드로 대체하지 않는다. */
                          <div className="grafana-frame-wrap grafana-frame-empty">
                            <section className="env-notice" role="status">
                              <span className="env-notice-title">
                                {observabilityLabel} 환경은 관측 대시보드가 아직 없습니다
                              </span>
                              <p>
                                터미널 명령으로 상태를 조사하세요. 미션 진행·자동 검증·점수에는
                                영향이 없습니다.
                              </p>
                            </section>
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
