import React, { ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import Login from './components/Login/Login'
import MissionList from './components/Mission/MissionList'
import OnboardingTour, { TourStep } from './components/Onboarding/OnboardingTour'
import DashboardOverview from './components/Profile/DashboardOverview'
import ProfileDetails from './components/Profile/ProfileDetails'
import Sheet from './components/Feedback/Sheet'
import EnvironmentRoadmap from './components/Environment/EnvironmentRoadmap'
import EnvironmentTabs from './components/Environment/EnvironmentTabs'
import Terminal from './components/Terminal/Terminal'
import InvestigationGuide from './components/Mission/InvestigationGuide'
import { ChartIcon, ChatIcon, GuideIcon, ListIcon, TerminalIcon } from './components/Mission/Icons'
import { insertTerminalCommand } from './utils/terminal'
import {
  capabilityList,
  getEnvironmentMeta,
  getEnvironmentTerminal,
  getGrafanaDataProbeUrl,
  getGrafanaUrl,
  hasCapability,
  isSelectableStatus,
} from './config/environments'
import {
  GRAFANA_PROBE_HIDDEN_MS,
  GRAFANA_PROBE_INTERVAL_MS,
  GRAFANA_PROBE_MAX_ATTEMPTS,
  MAX_BACKOFF_MS,
  PROFILE_POLL_HIDDEN_MS,
  PROFILE_POLL_INTERVAL_MS,
} from './config/polling'
import { usePolling } from './hooks/usePolling'
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

/** 작업 화면의 네 영역. 모바일 하단 탭 바가 한 번에 하나를 보여준다 (FE-26). */
type WorkspaceTab = 'missions' | 'terminal' | 'tutor' | 'observe'
/** 데스크톱 미션 중 보조 패널의 세그먼트. */
type AuxTab = 'briefing' | 'tutor' | 'observe'

/**
 * 탭 목록의 방향키 이동 (WAI-ARIA tabs). 포커스를 옮기면서 바로 선택한다.
 * 환경 탭(EnvironmentTabs)과 같은 규칙이다.
 */
const moveTabFocus = <T extends string>(
  event: React.KeyboardEvent<HTMLElement>,
  ids: T[],
  current: T,
  select: (id: T) => void,
) => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const from = Math.max(0, ids.indexOf(current))
  const last = ids.length - 1
  const next =
    event.key === 'Home' ? 0
      : event.key === 'End' ? last
        : event.key === 'ArrowRight' ? (from >= last ? 0 : from + 1)
          : (from <= 0 ? last : from - 1)
  select(ids[next])
  const tabs = event.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')
  tabs[next]?.focus()
}

const AREA_IDS: Record<WorkspaceTab, string> = {
  missions: 'area-mission',
  terminal: 'area-terminal',
  tutor: 'area-tutor',
  observe: 'area-observe',
}

/** 사용자별 마지막 선택 환경. 계획서에 정해진 키를 그대로 쓴다. */
const ENVIRONMENT_STORAGE_KEY = 'afterfail:environment:v1'

const GRAFANA_DATA_FALLBACK_FAILURES = 3
const INTRO_TOUR_STORAGE_KEY = 'afterfail:introTour:v1'
const MISSION_TOUR_STORAGE_KEY = 'afterfail:missionTour:v1'
const scopedStorageKey = (key: string, scope: string | null) => `${key}:${scope || 'anonymous'}`

const INTRO_TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="profile"]',
    eyebrow: '상단 정보',
    title: '학습 현황과 세션 정보',
    body: '프로필과 총점이 여기 있습니다. 프로필을 열면 완료한 미션, 학습 기록, 훈련 환경 로드맵을 볼 수 있어요.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="env-tabs"]',
    eyebrow: '훈련 환경',
    title: '훈련 환경 선택',
    body: '훈련할 환경을 고릅니다. 열리지 않은 환경은 탭 안에 그 이유가 적혀 있습니다.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="mission-list"]',
    eyebrow: '미션',
    title: '미션을 고르고 시작',
    body: '장애 상황을 고르면 시작 전에 제한 시간과 점수 규칙을 보여 줍니다. 잠긴 미션은 이전 레벨을 완료하면 열립니다.',
    placement: 'right',
  },
  {
    target: '[data-tour="field-guide"]',
    eyebrow: '시작 가이드',
    title: '시작 전 가이드',
    body: '조사 순서와 자주 쓰는 명령을 미리 볼 수 있습니다. 미션을 시작하면 이 자리에 터미널이 열립니다.',
    placement: 'left',
  },
  {
    target: '[data-tour="learning-dashboard"]',
    eyebrow: '학습 현황',
    title: '학습 대시보드',
    body: '진행률과 기록을 볼 수 있습니다. 미션 중에는 이 자리가 관측 대시보드로 바뀝니다.',
    placement: 'left',
  },
]

const MISSION_TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="mission-progress"]',
    eyebrow: '진행 상태',
    title: '미션 진행 상태',
    body: '남은 시간·점수·힌트와 완료 확인 버튼이 있습니다. 완료 확인이 통과하지 못하면 그 이유가 이 바 안에 남습니다.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="terminal"]',
    eyebrow: '터미널',
    title: '터미널에서 원인 조사',
    body: '명령으로 상태를 조사하고 원인을 고칩니다. 브리핑의 조사 명령을 누르면 실행하지 않고 입력줄에만 들어옵니다.',
    placement: 'right',
  },
  {
    target: '[data-tour="grafana"]',
    eyebrow: '관측',
    title: '관측과 튜터',
    body: '관측 탭에서 장애 지표와 복구 상태를 확인합니다. 막히면 튜터 탭에서 물어보세요. 질문은 감점이 없습니다.',
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
  const [auxTab, setAuxTab] = useState<AuxTab>('briefing')
  /*
   * MissionList 가 진행 상황과 튜터를 portal 할 자리 (FE-26). 상태 소유자(MissionList)는
   * 그대로 두고 그리는 위치만 터미널 위·보조 패널로 옮긴다.
   */
  const [incidentSlot, setIncidentSlot] = useState<HTMLDivElement | null>(null)
  const [tutorSlot, setTutorSlot] = useState<HTMLDivElement | null>(null)
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
  /*
   * 환경이 광고하는 기능 (FE-22). 화면 분기를 프론트 하드코딩이 아니라 응답으로 판정한다.
   *
   * 목록을 둘로 나눈 이유: 관측 패널은 **진행 중인 시도의 환경**(sessionEnvironment)을
   * 따르고, 미션·튜터 화면은 **선택된 탭의 환경**(activeEnvironment)을 따른다. 활성
   * 시도가 있으면 App 이 탭을 잠가 둘이 같지만, 각자 자기 근거를 쓰는 편이 맞다.
   */
  const findEnvironmentItem = (environment: EnvironmentId | null) =>
    environments?.find((item) => item.id === environment) ?? null
  const activeEnvironmentItem = findEnvironmentItem(activeEnvironment)
  const activeEnvironmentCapabilities = capabilityList(activeEnvironmentItem)
  const sessionEnvironmentCapabilities = capabilityList(findEnvironmentItem(sessionEnvironment))

  /*
   * 대시보드 유무와 capability 는 다른 사실이므로 둘 다 본다 (FE-22).
   * capability 만 보면 대시보드 없는 환경에서 Grafana 404 를, 대시보드만 보면
   * 백엔드가 관측을 떼어낸 환경에서 빈 대시보드를 보여준다.
   */
  const advertisesObservability = hasCapability(sessionEnvironmentCapabilities, 'observability')
  const canUseTerminal = hasCapability(sessionEnvironmentCapabilities, 'terminal')
  const canUseTutor = hasActiveAttempt && hasCapability(sessionEnvironmentCapabilities, 'tutor')

  /*
   * 보이는 탭. 미션이 끝나 튜터가 없어졌는데 튜터 탭에 머물러 있으면 빈 화면이 된다.
   * 그때는 미션 목록으로 돌린다.
   */
  const visibleTab: WorkspaceTab = activeTab === 'tutor' && !canUseTutor ? 'missions' : activeTab

  const auxTabs: Array<{ id: AuxTab; label: string; area: WorkspaceTab }> = [
    { id: 'briefing', label: '브리핑', area: 'missions' },
    ...(canUseTutor ? [{ id: 'tutor' as const, label: '튜터', area: 'tutor' as const }] : []),
    { id: 'observe', label: '관측', area: 'observe' },
  ]

  /* 미션 전에는 목록·가이드·기록 셋, 미션 중에는 미션·터미널·튜터·관측. */
  const mobileTabs: Array<{ id: WorkspaceTab; label: string; icon: ReactNode }> = hasActiveAttempt
    ? [
        { id: 'missions', label: '미션', icon: <ListIcon /> },
        { id: 'terminal', label: '터미널', icon: <TerminalIcon /> },
        ...(canUseTutor ? [{ id: 'tutor' as const, label: '튜터', icon: <ChatIcon /> }] : []),
        { id: 'observe', label: '관측', icon: <ChartIcon /> },
      ]
    : [
        { id: 'missions', label: '미션', icon: <ListIcon /> },
        { id: 'terminal', label: '가이드', icon: <GuideIcon /> },
        { id: 'observe', label: '기록', icon: <ChartIcon /> },
      ]

  /**
   * 관측 URL 은 활성 attempt 의 환경으로 만든다 (FE-08).
   * 대시보드가 없는 환경은 null 이 오고, 그때는 iframe 대신 안내를 띄운다 —
   * K8s 대시보드로 대체하면 사용자는 남의 환경 지표를 자기 것으로 읽는다.
   */
  const grafanaUrl = getGrafanaUrl(sessionEnvironment, namespace)
  /*
   * 실제로 돌릴 probe. 대시보드가 없거나 서버가 관측을 광고하지 않으면 없다.
   * URL 을 여기서 null 로 만들어야 polling 과 effect 가 한 곳에서 함께 꺼진다 —
   * iframe 만 감추면 Prometheus 요청은 계속 나간다 (FE-08 의 "polling 자체를 하지
   * 않는다"는 기준은 이유가 capability 일 때도 같다).
   */
  const grafanaProbeUrl = advertisesObservability
    ? getGrafanaDataProbeUrl(sessionEnvironment, namespace)
    : null
  const hasObservability = grafanaUrl !== null && advertisesObservability
  /** 관측 패널 문구에 쓰는 환경 이름. iframe title 에도 넣어 스크린리더가 구분할 수 있게 한다. */
  const observabilityLabel = sessionEnvironment ? getEnvironmentMeta(sessionEnvironment).label : ''
  /*
   * 미션 시작 전 field guide 는 선택된 환경 기준으로 그린다 (FE-09).
   * 예전에는 kubectl 명령이 하드코딩돼 Docker / Linux 탭에서도 그대로 보였다.
   */
  const fieldGuideTerminal = activeEnvironment ? getEnvironmentTerminal(activeEnvironment) : null
  /** 실행 파일이 고정된 환경만 이름을 문장에 넣는다. Linux 는 단일 바이너리가 없다. */
  const fieldGuideLabel = fieldGuideTerminal?.binary ?? null
  const isGrafanaLoading =
    hasActiveAttempt && hasObservability && (!isGrafanaFrameReady || !isGrafanaDataReady)
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

  /*
   * 프로필 폴링 (FE-16).
   *
   * setInterval 이던 것을 usePolling 으로 바꿨다. 응답이 15초보다 오래 걸리면
   * setInterval 은 요청을 겹쳐 쌓았고, 탭이 백그라운드일 때도 같은 빈도로 돌았다.
   */
  const pollProfile = useCallback(async () => {
    await loadProfile()
    return 'continue' as const
  }, [loadProfile])

  usePolling(pollProfile, {
    intervalMs: PROFILE_POLL_INTERVAL_MS,
    hiddenIntervalMs: PROFILE_POLL_HIDDEN_MS,
    maxBackoffMs: MAX_BACKOFF_MS,
    enabled: Boolean(token),
    restartKey: token ?? '',
  })

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

  /**
   * 선택된 환경의 터미널이 필요해진 순간에만 세션을 만든다. 이미 있으면 훅이 막는다.
   *
   * 서버가 terminal 을 광고하지 않으면 만들지 않는다 (FE-22) — 백엔드
   * `assert_implemented` 가 거절할 요청이라 사용자에게 실패할 로딩만 보여준다.
   */
  useEffect(() => {
    if (!sessionEnvironment || !needsWorkspace || !canUseTerminal) return
    ensure(sessionEnvironment)
  }, [canUseTerminal, ensure, needsWorkspace, sessionEnvironment])

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

  /*
   * 미션 투어를 미션 시작 직후 자동으로 띄우지 않는다 (FE-27). 그때는 이미 타이머가 돌고
   * 있어 투어가 시간을 잡아먹었다. 첫 미션의 시작 시트가 작업 화면 구성을 미리 알려 주고,
   * 미션 중에는 둘러보기로 언제든 다시 볼 수 있다.
   */
  const markMissionTourSeen = useCallback(() => {
    localStorage.setItem(scopedStorageKey(MISSION_TOUR_STORAGE_KEY, accountStorageScope), 'done')
    setHasSeenMissionTour(true)
  }, [accountStorageScope])

  useEffect(() => {
    setIsGrafanaFrameReady(false)
    setIsGrafanaDataReady(false)
    setIsObservabilityDegraded(false)
  }, [grafanaUrl, hasActiveAttempt])

  /*
   * Grafana 데이터 준비 확인 (FE-08 / FE-16).
   *
   * 미션이 없거나 이 환경에 대시보드가 없으면 시작하지 않는다 — 예전에는 미션
   * 종료 후에도 K8s 쿼리를 계속 던졌다. Prometheus 가 영구히 죽어 있어도
   * 1초마다 무한히 두드리지 않도록 시도 상한과 backoff 를 둔다 (FE-16).
   */
  const probeAttemptsRef = useRef(0)
  const probeFailuresRef = useRef(0)

  useEffect(() => {
    probeAttemptsRef.current = 0
    probeFailuresRef.current = 0
  }, [grafanaProbeUrl, hasActiveAttempt])

  const probeGrafanaData = useCallback(async () => {
    probeAttemptsRef.current += 1

    const markReady = (degraded: boolean) => {
      setIsGrafanaDataReady(true)
      if (degraded) setIsObservabilityDegraded(true)
      return 'stop' as const
    }

    try {
      const response = await fetch(grafanaProbeUrl as string, { cache: 'no-store' })
      if (!response.ok) throw new Error(`Prometheus responded with ${response.status}`)

      const payload = (await response.json()) as PrometheusQueryResponse
      if (hasPrometheusResponse(payload)) {
        probeFailuresRef.current = 0
        return markReady(false)
      }
      return 'continue' as const
    } catch (error) {
      probeFailuresRef.current += 1
      console.warn('Grafana data readiness probe failed:', error)

      // iframe 은 떴으니 화면은 열어준다. 다만 degraded 로 표시한다.
      if (isGrafanaFrameReady && probeFailuresRef.current >= GRAFANA_DATA_FALLBACK_FAILURES) {
        return markReady(true)
      }

      /*
       * iframe 도 안 뜨고 Prometheus 도 계속 죽어 있으면 무한히 두드리지 않는다.
       * 상한을 넘기면 degraded 로 열어 준다 — 관측이 없다고 터미널까지 막을 이유가 없다.
       */
      if (probeAttemptsRef.current >= GRAFANA_PROBE_MAX_ATTEMPTS) {
        return markReady(true)
      }

      throw error
    }
  }, [grafanaProbeUrl, isGrafanaFrameReady])

  usePolling(probeGrafanaData, {
    intervalMs: GRAFANA_PROBE_INTERVAL_MS,
    hiddenIntervalMs: GRAFANA_PROBE_HIDDEN_MS,
    maxBackoffMs: MAX_BACKOFF_MS,
    enabled: hasActiveAttempt && grafanaProbeUrl !== null,
    restartKey: `${grafanaProbeUrl ?? ''}:${isGrafanaFrameReady}`,
  })

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

  /** 둘러보기. 미션 중에는 지금 화면(인시던트 바·터미널·관측)을 가리키는 미션 투어를 띄운다. */
  const replayIntroTour = () => {
    setIsProfileOpen(false)
    if (hasActiveAttempt) {
      setActiveTour('mission')
      return
    }
    setActiveTab('missions')
    setActiveTour('intro')
  }

  /* 투어가 가리키는 요소가 숨은 영역에 있으면 그 영역을 먼저 연다 (모바일 탭, 데스크톱 보조 패널). */
  const handleTourStepChange = (step: TourStep) => {
    const target = step.target
    if (target === '[data-tour="mission-list"]') {
      setActiveTab('missions')
      setAuxTab('briefing')
    }
    if (target === '[data-tour="terminal"]' || target === '[data-tour="field-guide"]') setActiveTab('terminal')
    if (target === '[data-tour="grafana"]' || target === '[data-tour="learning-dashboard"]') {
      setActiveTab('observe')
      setAuxTab('observe')
    }
  }

  /**
   * 브리핑의 조사 명령을 터미널 입력줄에 넣는다 (FE-26). 모바일에서는 터미널 탭으로
   * 옮긴 뒤 넣어야 focus 가 들어간다 — 숨은 요소는 focus 를 받지 못한다.
   */
  const insertCommand = useCallback((command: string) => {
    setActiveTab('terminal')
    window.requestAnimationFrame(() => insertTerminalCommand(command))
  }, [])

  /*
   * 새 시도가 시작되면 터미널과 브리핑을 앞에 둔다. 시도가 끝나면 다음 미션을 고를 수
   * 있게 목록으로 돌아간다. 같은 시도의 상태 갱신에는 반응하지 않는다.
   */
  const activeAttemptId = activeAttempt?.attemptId ?? null
  const previousAttemptIdRef = useRef<string | null>(null)
  useEffect(() => {
    const previous = previousAttemptIdRef.current
    previousAttemptIdRef.current = activeAttemptId
    if (activeAttemptId === previous) return
    if (activeAttemptId) {
      setActiveTab('terminal')
      setAuxTab('briefing')
    } else if (previous) {
      setActiveTab('missions')
    }
  }, [activeAttemptId])

  const handleActiveAttemptChange = useCallback((summary: ActiveAttemptSummary | null) => {
    setActiveAttempt(summary)
    if (summary) {
      setIsGrafanaFrameReady(false)
      setIsGrafanaDataReady(false)
    }
  }, [])

  if (isLoading) return <div className="app-loading" role="status">불러오는 중...</div>
  if (!token) return <Login onLoginSuccess={handleLoginSuccess} />

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="brand-wordmark">AfterFail</h1>
        <div className="header-info">
          {profile && (
            <button
              className="profile-summary"
              type="button"
              title="프로필과 학습 기록 보기"
              onClick={() => setIsProfileOpen(true)}
              data-tour="profile"
            >
              <span className="profile-avatar" aria-hidden="true">
                {profile.username.charAt(0).toUpperCase()}
              </span>
              <span className="profile-name">{profile.username}</span>
              <span className="ui-chip profile-score">
                총점 <span className="profile-score-value">{profile.total_score}</span>
              </span>
            </button>
          )}
          {namespace && (
            <span className="namespace-badge" title={namespace}>
              <span className="namespace-badge-label">네임스페이스</span>
              <span className="namespace-badge-value">{namespace}</span>
            </span>
          )}
          <button className="ui-button plain small tour-replay-button" type="button" onClick={replayIntroTour}>
            둘러보기
          </button>
          <button className="ui-button plain small logout-button" type="button" onClick={handleLogout}>
            로그아웃
          </button>
        </div>
      </header>
      <main className="app-main">
        {/*
          * 프로필은 작업 화면을 대체하지 않고 시트로 덮는다 (FE-25).
          * 대체하면 터미널·WebSocket·튜터 대화가 언마운트돼 미션 중에 작업 기록이 사라졌다.
          */}
        <div className="workspace">
            {environmentsError ? (
              <section className="env-notice env-notice-error" role="alert">
                <span className="env-notice-title">환경 목록을 불러오지 못했습니다</span>
                <p>{environmentsError}</p>
                <button className="ui-button small env-notice-action" type="button" onClick={() => void loadEnvironments()}>
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
                  <p className="env-notice env-notice-lock sr-only" role="status">
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
                    {/* 닫힌 이유는 환경마다 다르므로 여기서 단정하지 않는다 — 아래 목록이 이유별로 나눠 말한다 (FE-23). */}
                    <p>서버가 이 배포에서 열어 둔 환경이 없습니다.</p>
                    <EnvironmentRoadmap items={environments} />
                  </section>
                ) : activeEnvironmentCapabilities?.length === 0 ? (
                  /*
                   * status 는 선택 가능한데 광고하는 기능이 하나도 없다 (FE-22).
                   * 빈 배열은 서버가 "없다"고 말한 것이므로 그대로 전한다 — 작업 화면을
                   * 그리면 사용자가 누르는 것마다 백엔드에 거절당한다.
                   * (판정 근거가 없는 경우는 여기 오지 않는다. `capabilityList` 가 null 을 준다)
                   */
                  <section className="env-notice env-notice-empty" id="env-panel" role="tabpanel">
                    <span className="env-notice-title">
                      {getEnvironmentMeta(activeEnvironment).label} 환경은 아직 준비 중입니다
                    </span>
                    <p>서버가 이 환경에서 제공하는 기능을 아직 알리지 않았습니다.</p>
                    <EnvironmentRoadmap items={environments} />
                  </section>
                ) : (
                  <>
                <div
                  className="workspace-grid"
                  data-mode={hasActiveAttempt ? 'active' : 'idle'}
                  data-tab={visibleTab}
                  data-aux={auxTab}
                  id="env-panel"
                  role="tabpanel"
                  aria-labelledby={`env-tab-${activeEnvironment}`}
                >
                  {/* 인시던트 바 자리. MissionList 가 진행 상황을 여기에 portal 한다 (FE-26). */}
                  <div className="incident-slot" ref={setIncidentSlot} />

                  {hasActiveAttempt && (
                    <div className="aux-header">
                      <div
                        className="aux-tabs"
                        role="tablist"
                        aria-label="보조 패널"
                        onKeyDown={(event) => moveTabFocus(event, auxTabs.map((tab) => tab.id), auxTab, setAuxTab)}
                      >
                        {auxTabs.map((tab) => (
                          <button
                            key={tab.id}
                            type="button"
                            role="tab"
                            id={`aux-tab-${tab.id}`}
                            aria-selected={auxTab === tab.id}
                            aria-controls={AREA_IDS[tab.area]}
                            tabIndex={auxTab === tab.id ? 0 : -1}
                            className={auxTab === tab.id ? 'active' : ''}
                            onClick={() => setAuxTab(tab.id)}
                          >
                            {tab.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <section
                    className="area area-mission"
                    id={AREA_IDS.missions}
                    aria-label={hasActiveAttempt ? '브리핑' : '미션'}
                    data-tour="mission-list"
                  >
                    <MissionList
                      token={token}
                      storageScope={accountStorageScope}
                      environment={activeEnvironment}
                      capabilities={activeEnvironmentCapabilities}
                      incidentSlot={incidentSlot}
                      tutorSlot={tutorSlot}
                      showFirstRunGuide={!hasSeenMissionTour}
                      onFirstRunGuideSeen={markMissionTourSeen}
                      onActiveAttemptChange={handleActiveAttemptChange}
                      onAttemptCompleted={handleAttemptCompleted}
                    />
                    {activeAttempt && (
                      <section className="briefing-guide" aria-label="조사 순서">
                        <InvestigationGuide
                          environment={activeAttempt.environment}
                          active
                          onInsertCommand={canUseTerminal && activeSession ? insertCommand : undefined}
                        />
                      </section>
                    )}
                  </section>

                  <section className="area area-terminal" id={AREA_IDS.terminal} aria-label={hasActiveAttempt ? '터미널' : '시작 가이드'}>
                    {activeAttempt && !canUseTerminal ? (
                      /*
                       * 서버가 이 환경에 terminal 을 광고하지 않는다 (FE-22).
                       * 세션 생성을 시도하면 백엔드 assert_implemented 가 거절하므로,
                       * 사용자에게 실패할 로딩을 보여주지 않고 이유를 먼저 알린다.
                       */
                      <section className="env-notice" role="status">
                        <span className="env-notice-title">
                          {getEnvironmentMeta(activeAttempt.environment).label} 환경은 터미널을
                          제공하지 않습니다
                        </span>
                        <p>
                          미션 진행과 검증은 그대로 동작합니다. 터미널이 필요한 미션이라면
                          다른 환경을 선택하세요.
                        </p>
                      </section>
                    ) : activeAttempt ? (
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
                              className="ui-button small env-notice-action"
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
                          <span className="panel-label">시작 가이드</span>
                        </div>
                        <div className="tutorial-content">
                          <div className="tutorial-intro">
                            <h2>장애를 직접 관찰하고 복구해 보세요.</h2>
                            <p>
                              미션을 시작하면 이 자리에 터미널이 열립니다.
                              {fieldGuideLabel
                                ? ` ${fieldGuideLabel} 명령으로 상태를 조사해 원인을 찾아보세요.`
                                : ' 터미널 명령으로 상태를 조사해 원인을 찾아보세요.'}
                            </p>
                          </div>
                          <InvestigationGuide environment={activeEnvironment} />
                        </div>
                      </section>
                    )}
                  </section>

                  <section className="area area-tutor" id={AREA_IDS.tutor} aria-label="AI 튜터">
                    {/* MissionList 가 튜터를 여기에 portal 한다 (FE-26). */}
                    <div className="tutor-slot" ref={setTutorSlot} />
                  </section>

                  <section
                    className="area area-observe"
                    id={AREA_IDS.observe}
                    aria-label={hasActiveAttempt ? '관측' : '학습 현황'}
                  >
                    <section className="grafana-panel" data-tour={hasActiveAttempt ? 'grafana' : 'learning-dashboard'}>
                      <div className="grafana-panel-header">
                        <span className="panel-label">
                          {hasActiveAttempt ? `관측 · ${observabilityLabel}` : '학습 현황'}
                        </span>
                        {hasActiveAttempt && grafanaUrl && (
                          <a className="panel-link" href={grafanaUrl} target="_blank" rel="noreferrer">
                            새 창
                            <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">
                              <path
                                d="M6.5 3.5H4a1 1 0 0 0-1 1V12a1 1 0 0 0 1 1h7.5a1 1 0 0 0 1-1V9.5M9.5 3H13v3.5M13 3 7.5 8.5"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1.5"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                            </svg>
                          </a>
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
                              <span>Grafana 대시보드를 불러오는 중입니다</span>
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
                        /*
                         * 관측 화면을 열 수 없다. 다른 환경 대시보드로 대체하지 않는다 (FE-08).
                         * 이유가 두 가지라 문구를 나눈다 (FE-22) — "대시보드가 없다"와
                         * "서버가 관측을 제공하지 않는다"는 사용자가 할 일이 다르다.
                         */
                        <div className="grafana-frame-wrap grafana-frame-empty">
                          <section className="env-notice" role="status">
                            <span className="env-notice-title">
                              {advertisesObservability
                                ? `${observabilityLabel} 환경은 관측 대시보드가 아직 없습니다`
                                : `${observabilityLabel} 환경은 관측 데이터를 제공하지 않습니다`}
                            </span>
                            <p>
                              터미널 명령으로 상태를 조사하세요. 미션 진행·자동 검증·점수에는
                              영향이 없습니다.
                            </p>
                          </section>
                        </div>
                      )}
                    </section>
                  </section>
                </div>

                {/*
                  * 모바일 하단 탭 바 (FE-26). 한 번에 한 영역만 보이고 나머지는 숨길 뿐
                  * 언마운트하지 않는다 — 터미널 연결과 튜터 대화가 탭 전환으로 사라지면 안 된다.
                  */}
                <nav className="mobile-tabbar material-bar" aria-label="작업 화면">
                  <div
                    className="mobile-tabbar-list"
                    role="tablist"
                    aria-label="작업 화면"
                    onKeyDown={(event) => moveTabFocus(event, mobileTabs.map((tab) => tab.id), visibleTab, setActiveTab)}
                  >
                    {mobileTabs.map((tab) => (
                      <button
                        key={tab.id}
                        type="button"
                        role="tab"
                        aria-selected={visibleTab === tab.id}
                        aria-controls={AREA_IDS[tab.id]}
                        tabIndex={visibleTab === tab.id ? 0 : -1}
                        className={visibleTab === tab.id ? 'active' : ''}
                        onClick={() => setActiveTab(tab.id)}
                      >
                        {tab.icon}
                        <span>{tab.label}</span>
                      </button>
                    ))}
                  </div>
                </nav>
                  </>

                )}
              </>
            )}
        </div>
      </main>
      {isProfileOpen && profile && (
        <Sheet variant="side" labelledBy="profile-sheet-title" onClose={() => setIsProfileOpen(false)}>
          <ProfileDetails
            token={token}
            profile={profile}
            environments={environments}
            loading={isProfileLoading}
            onClose={() => setIsProfileOpen(false)}
            onRefresh={() => void loadProfile()}
          />
        </Sheet>
      )}
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
