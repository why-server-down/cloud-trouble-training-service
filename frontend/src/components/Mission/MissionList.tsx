import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import ConfirmModal from '../Feedback/ConfirmModal'
import Toast, { ToastMessage } from '../Feedback/Toast'
import {
  abandonMission,
  abandonScenario,
  ApiError,
  checkMission,
  checkScenario,
  getAttempt,
  getMissionStatus,
  getScenarioStatus,
  getUnlockStatus,
  listMissions,
  MissionAttemptResponse,
  MissionResponse,
  MissionStatusResponse,
  requestHint,
  requestScenarioHint,
  ScenarioStatusResponse,
  startMission,
  startRandomScenario,
  UnlockStatusResponse,
} from '../../services/api'
import { getEnvironmentMeta, hasCapability } from '../../config/environments'
import {
  MAX_BACKOFF_MS,
  MISSION_POLL_HIDDEN_MS,
  MISSION_POLL_INTERVAL_MS,
} from '../../config/polling'
import { usePolling } from '../../hooks/usePolling'
import { markStart, measureSince, nextFrame, PERF } from '../../utils/perf'
import {
  ActiveAttemptSummary,
  AttemptType,
  EnvironmentCapability,
  EnvironmentId,
} from '../../types/training'
import MissionCard from './MissionCard'
import { getMissionCause, getMissionCopy } from './missionCopy'
import StartSheet from './StartSheet'
import DebriefSheet, { Debrief, DebriefOutcome } from './DebriefSheet'
import { TERMINAL_COMMAND_EVENT } from '../../utils/terminal'
import MissionStatus, { MissionAction, MissionStatusView } from './MissionStatus'
import { CheckIcon, LockIcon } from './Icons'
import TutorChat from './TutorChat'
import './Mission.css'

interface MissionListProps {
  token: string
  storageScope: string | null
  /** 현재 선택된 훈련 환경. AI 시나리오 생성 요청에 그대로 실려 나간다. */
  environment: EnvironmentId
  /**
   * 이 환경이 광고하는 기능 (FE-22). `null` 은 판정할 근거가 없다는 뜻이고
   * 그때는 아무것도 숨기지 않는다 — 규칙은 `config/environments.ts` 의
   * `hasCapability` 한 곳에 있다.
   */
  capabilities: EnvironmentCapability[] | null
  /**
   * 진행 상황(인시던트 바)과 튜터를 그릴 자리 (FE-26). App 이 터미널 위와 보조 패널에
   * 둔 요소다. 없으면 이 컴포넌트 안에 그대로 그린다(단독 렌더·테스트).
   */
  incidentSlot?: HTMLElement | null
  tutorSlot?: HTMLElement | null
  /** 첫 미션이면 시작 시트에 작업 화면 안내를 넣는다 (FE-27, 타이머가 도는 투어 대신). */
  showFirstRunGuide?: boolean
  onFirstRunGuideSeen?: () => void
  /** 힌트를 샀다. App 이 튜터를 앞으로 꺼낸다 (FE-28). */
  onHintUsed?: () => void
  /**
   * 이 배포에서 열리지 않은 환경 이름 (FE-28). AI 잠금 조건은 모든 환경의 기본 미션을
   * 세므로, 닫힌 환경이 있으면 지금은 조건을 채울 수 없다는 사실을 함께 말한다.
   */
  closedEnvironmentLabels?: string[]
  /** 서버 status 로 만든 활성 시도 요약. 없으면 null. App 이 이걸로 환경 탭을 잠근다. */
  onActiveAttemptChange: (summary: ActiveAttemptSummary | null) => void
  /**
   * 시도가 완료된 순간 (FE-15). App 이 이걸 받아 대시보드를 한 번 갱신한다.
   * attemptId 를 함께 주므로 같은 완료 이벤트가 두 번 반영되지 않는다.
   */
  onAttemptCompleted?: (attemptId: string) => void
}

interface Confirmation {
  title: string
  message: string
  confirmLabel: string
  danger?: boolean
  /** 어떤 액션인지. 실행 중 버튼 문구를 액션별로 바꾸기 위한 것이다 (FE-16). */
  kind?: MissionAction
  action: () => Promise<void>
}

type Difficulty = 'beginner' | 'intermediate' | 'advanced' | 'expert'

/** 시작 시트가 열린 이유 (FE-27). */
type StartRequest = { kind: 'mission'; missionId: string } | { kind: 'scenario' }

/** 서버 시작·종료 시각으로 잰 걸린 시간. 모르면 null. */
const attemptDuration = (attempt: Pick<MissionAttemptResponse, 'start_time' | 'end_time'>) => {
  if (!attempt.end_time) return null
  const seconds = Math.round((Date.parse(attempt.end_time) - Date.parse(attempt.start_time)) / 1000)
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null
}

/**
 * 404 로 끝난 시도를 시간 초과로 볼 남은 시간의 상한(초). 상태 폴링 간격(5초)에
 * 한 번 늦는 응답을 더한 값이다.
 */
const TIMEOUT_INFERENCE_SECONDS = 10

const outcomeOf = (status: string): DebriefOutcome =>
  status === 'completed' ? 'completed' : status === 'abandoned' ? 'abandoned' : 'failed'

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  beginner: '입문',
  intermediate: '중급',
  advanced: '고급',
  expert: '전문가',
}

const ACTIVE_ATTEMPT_TYPE_KEY = 'activeAttemptType'
const DEMO_AI_UNLOCK_STORAGE_KEY = 'demoAiScenarioUnlocked'
/**
 * 시연 모드 (FE-28). 심사·시연 때만 주소에 `?demo=1` 을 붙여 AI 문제 잠금 해제 버튼을 연다.
 * 학생 화면에 "시연용" 버튼이 보이면 훈련 규칙을 우회하라는 신호가 된다.
 */
const isDemoMode = () => typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('demo')
const scopedStorageKey = (key: string, scope: string | null) => `${key}:${scope || 'anonymous'}`

const MissionList: React.FC<MissionListProps> = ({
  token,
  storageScope,
  environment,
  capabilities,
  incidentSlot,
  tutorSlot,
  showFirstRunGuide = false,
  onFirstRunGuideSeen,
  onHintUsed,
  closedEnvironmentLabels = [],
  onActiveAttemptChange,
  onAttemptCompleted,
}) => {
  const [missions, setMissions] = useState<MissionResponse[]>([])
  const [activeMissionId, setActiveMissionId] = useState<string | null>(null)
  /**
   * 활성 정적 미션의 환경 (FE-11).
   * 튜터 배지를 선택된 탭이 아니라 attempt 의 환경으로 그리기 위한 값이다 —
   * 서버 attempt 가 우선이라는 FE-05 규칙을 튜터에도 그대로 적용한다.
   */
  const [activeMissionEnvironment, setActiveMissionEnvironment] = useState<EnvironmentId | null>(null)
  const [hintsUsed, setHintsUsed] = useState(0)
  const [statusRefreshKey, setStatusRefreshKey] = useState(0)
  const [loading, setLoading] = useState(false)
  /**
   * 진행 중인 액션 (FE-16). loading 하나로는 어떤 버튼이 도는지 알 수 없어
   * 세 버튼 모두 같은 문구로 잠겼다.
   */
  const [pendingAction, setPendingAction] = useState<MissionAction | null>(null)
  const [error, setError] = useState<string | null>(null)
  /** 목록이 비었을 때 "준비 중"과 "조회 실패"를 구분하기 위한 상태 (FE-06). */
  const [missionsStatus, setMissionsStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [toast, setToast] = useState<ToastMessage | null>(null)
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)

  // AI 시나리오 상태
  const [unlockStatus, setUnlockStatus] = useState<UnlockStatusResponse | null>(null)
  const [selectedDifficulty, setSelectedDifficulty] = useState<Difficulty>('beginner')
  const [activeScenario, setActiveScenario] = useState<ScenarioStatusResponse | null>(null)
  const [scenarioHintsUsed, setScenarioHintsUsed] = useState(0)
  const [isTutorFloatingOpen, setIsTutorFloatingOpen] = useState(false)
  const [demoAiUnlocked, setDemoAiUnlocked] = useState(() => localStorage.getItem(scopedStorageKey(DEMO_AI_UNLOCK_STORAGE_KEY, storageScope)) === 'true')
  const hasTutor = Boolean(activeMissionId || activeScenario?.status === 'in_progress')
  const isAiUnlocked = Boolean(unlockStatus?.unlocked || demoAiUnlocked)

  /** 진행 중인 시도의 id. 튜터 대화를 시도 단위로 보존하는 key 로 쓴다 (FE-25). */
  const [activeAttemptId, setActiveAttemptId] = useState<string | null>(null)

  const activeMission = missions.find((mission) => mission.id === activeMissionId) ?? null

  /** 시작 시트 (FE-27). 열린 동안 시작 요청의 진행과 실패를 시트가 직접 말한다. */
  const [startRequest, setStartRequest] = useState<StartRequest | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  /** 미션이 끝난 뒤의 결과 시트와, "다시 도전"이 다시 열 시작 요청. */
  const [debrief, setDebrief] = useState<{ data: Debrief; again: StartRequest } | null>(null)
  /**
   * 힌트를 산 횟수 신호 (FE-28). 바뀌면 튜터가 올라간 단계의 힌트를 바로 요청해 보여 준다.
   * 예전에는 점수만 깎이고 화면에 아무것도 나오지 않았다.
   */
  const [autoHintKey, setAutoHintKey] = useState(0)
  /** 완료 확인이 통과하지 못한 이유. 토스트 대신 인시던트 바 안에 남긴다. */
  const [checkFeedback, setCheckFeedback] = useState<string | null>(null)
  /** 이번 시도에서 터미널에 보낸 명령. 디브리프에만 쓰므로 렌더를 일으키지 않게 ref 로 둔다. */
  const commandLogRef = useRef<string[]>([])
  /** 지금 기록 중인 시도. 시도가 끝나면 null — 기록은 디브리프가 읽을 때까지 남긴다. */
  const loggingAttemptRef = useRef<string | null>(null)
  /** 이 화면에서 시작한 시도인가. 새로고침으로 복원한 시도는 그 전 명령이 기록에 없다. */
  const startedHereRef = useRef<string | null>(null)
  const commandsPartialRef = useRef(false)
  /** 결과 시트를 이미 띄운 시도. 완료 확인과 폴링이 같은 끝을 두 번 알려도 한 번만 띄운다. */
  const debriefedAttemptRef = useRef<string | null>(null)
  /** 시나리오 폴링이 끝을 알렸을 때 할 일. 결과 시트 함수가 폴링 콜백보다 뒤에 있어 ref 로 잇는다. */
  const scenarioEndedRef = useRef<(status: ScenarioStatusResponse | null) => void>(() => undefined)

  /** App 에 활성 시도를 알리면서 id 도 기억한다. 모든 보고가 이 한 곳을 지난다. */
  const reportActiveAttempt = useCallback((summary: ActiveAttemptSummary | null) => {
    const nextId = summary?.attemptId ?? null
    /*
     * 명령 기록 대상은 effect 를 기다리지 않고 여기서 바로 바꾼다. 새 시도면 비우고,
     * 끝나면 기록만 멈춘다(디브리프가 읽어야 하므로 비우지 않는다).
     */
    if (nextId && nextId !== loggingAttemptRef.current) {
      commandLogRef.current = []
      commandsPartialRef.current = startedHereRef.current !== nextId
    }
    loggingAttemptRef.current = nextId
    if (!nextId) setCheckFeedback(null)
    setActiveAttemptId(nextId)
    onActiveAttemptChange(summary)
  }, [onActiveAttemptChange])

  useEffect(() => {
    const handleCommand = (event: Event) => {
      const command = (event as CustomEvent<unknown>).detail
      if (typeof command === 'string' && loggingAttemptRef.current) commandLogRef.current.push(command)
    }
    window.addEventListener(TERMINAL_COMMAND_EVENT, handleCommand)
    return () => window.removeEventListener(TERMINAL_COMMAND_EVENT, handleCommand)
  }, [])

  const showToast = useCallback(
    (kind: ToastMessage['kind'], text: string) => setToast({ kind, text, id: Date.now() }),
    [],
  )

  const rememberActiveAttempt = useCallback((type: AttemptType) => {
    localStorage.setItem(scopedStorageKey(ACTIVE_ATTEMPT_TYPE_KEY, storageScope), type)
  }, [storageScope])

  const forgetActiveAttempt = useCallback(() => {
    localStorage.removeItem(scopedStorageKey(ACTIVE_ATTEMPT_TYPE_KEY, storageScope))
  }, [storageScope])

  const unlockAiScenariosForDemo = useCallback(() => {
    localStorage.setItem(scopedStorageKey(DEMO_AI_UNLOCK_STORAGE_KEY, storageScope), 'true')
    setDemoAiUnlocked(true)
    setUnlockStatus((current) => ({
      unlocked: true,
      completed_static: current?.completed_static ?? current?.total_static ?? 4,
      total_static: current?.total_static ?? 4,
    }))
    showToast('info', '시연용으로 AI 문제 모드를 열었습니다.')
  }, [showToast, storageScope])

  const fetchMissions = useCallback(async (signal?: AbortSignal) => {
    try {
      setError(null)
      const missionList = await listMissions(token, environment, signal)
      if (signal?.aborted) return
      setMissions(missionList)
      setMissionsStatus('ready')

      // localStorage 의 attempt type 은 **조회 순서를 정하는 힌트일 뿐**이다.
      // 값이 없거나 낡아도 두 종류를 모두 확인해 서버 상태를 그대로 따른다 (FE-05).
      const hint = localStorage.getItem(scopedStorageKey(ACTIVE_ATTEMPT_TYPE_KEY, storageScope))
      const probeOrder: AttemptType[] = hint === 'ai_scenario'
        ? ['ai_scenario', 'static_mission']
        : ['static_mission', 'ai_scenario']

      let summary: ActiveAttemptSummary | null = null

      for (const kind of probeOrder) {
        if (summary) break

        if (kind === 'static_mission') {
          try {
            const missionStatus = await getMissionStatus(token)
            if (missionStatus.attempt.status === 'in_progress') {
              summary = {
                attemptId: missionStatus.attempt.id,
                attemptType: 'static_mission',
                environment: missionStatus.attempt.environment,
                status: missionStatus.attempt.status,
              }
              setActiveMissionId(missionStatus.attempt.mission_id ?? null)
              setActiveMissionEnvironment(missionStatus.attempt.environment)
              setHintsUsed(missionStatus.attempt.hints_used)
            }
          } catch {
            // 활성 정적 미션이 없으면 404 다. 다음 종류를 확인한다.
          }
        } else {
          try {
            const scenarioStatus = await getScenarioStatus(token)
            if (scenarioStatus.status === 'in_progress') {
              summary = {
                attemptId: scenarioStatus.attempt_id,
                attemptType: 'ai_scenario',
                environment: scenarioStatus.environment,
                status: scenarioStatus.status,
              }
              setActiveScenario(scenarioStatus)
              setScenarioHintsUsed(scenarioStatus.hints_used)
            }
          } catch {
            // 활성 AI 시나리오가 없으면 404 다.
          }
        }
      }

      if (summary?.attemptType !== 'static_mission') {
        setActiveMissionId(null)
        setActiveMissionEnvironment(null)
        setHintsUsed(0)
      }
      if (summary?.attemptType !== 'ai_scenario') {
        setActiveScenario(null)
        setScenarioHintsUsed(0)
      }

      // 서버에 활성 attempt 가 없으면 stale localStorage 값을 지운다.
      if (summary) rememberActiveAttempt(summary.attemptType)
      else forgetActiveAttempt()

      reportActiveAttempt(summary)

      // AI 잠금 해제 상태
      try {
        const unlock = await getUnlockStatus(token)
        setUnlockStatus(unlock)
      } catch {
        setUnlockStatus(null)
      }
    } catch (err) {
      // 환경을 바꿔 이전 요청을 끊은 것은 실패가 아니다.
      if (signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) return

      console.error('미션 목록 조회 실패:', err)
      setMissionsStatus('error')
      // 계약이 어긋난 경우(다른 환경 미션 혼입 등)는 원인을 그대로 보여준다.
      setError(err instanceof ApiError ? err.message : '미션 목록을 불러오지 못했습니다.')
    }
  }, [environment, forgetActiveAttempt, reportActiveAttempt, rememberActiveAttempt, storageScope, token])

  useEffect(() => {
    setDemoAiUnlocked(localStorage.getItem(scopedStorageKey(DEMO_AI_UNLOCK_STORAGE_KEY, storageScope)) === 'true')
    setMissions([])
    setMissionsStatus('loading')
    setError(null)
    setActiveMissionId(null)
    setActiveScenario(null)
    setHintsUsed(0)
    setScenarioHintsUsed(0)
    reportActiveAttempt(null)
  }, [environment, reportActiveAttempt, storageScope])

  useEffect(() => {
    const controller = new AbortController()
    void fetchMissions(controller.signal)
    return () => controller.abort()
  }, [fetchMissions])

  useEffect(() => {
    if (!hasTutor) {
      setIsTutorFloatingOpen(false)
    }
  }, [hasTutor])

  /*
   * AI 시나리오 진행 상태 폴링 (FE-16).
   *
   * 예전에는 1초 setInterval 이었고 activeScenario 를 의존성으로 물고 있어서
   * 폴링이 setActiveScenario 를 부를 때마다 interval 을 새로 만들었다.
   * 이제 시나리오 id 를 restartKey 로 쓰고 남은 시간 표시는 서버 값으로만 갱신한다.
   */
  const pollScenario = useCallback(async () => {
    try {
      const status = await getScenarioStatus(token)
      setActiveScenario(status)
      setScenarioHintsUsed(status.hints_used)

      if (status.status !== 'in_progress') {
        scenarioEndedRef.current(status)
        forgetActiveAttempt()
        setActiveScenario(null)
        setScenarioHintsUsed(0)
        reportActiveAttempt(null)
        await fetchMissions()
        return 'stop' as const
      }
      return 'continue' as const
    } catch (err) {
      // 404 는 시나리오가 끝난 것이다. 정리하고 멈춘다.
      if (err instanceof ApiError && err.status === 404) {
        scenarioEndedRef.current(null)
        forgetActiveAttempt()
        setActiveScenario(null)
        setScenarioHintsUsed(0)
        reportActiveAttempt(null)
        return 'stop' as const
      }
      // 그 밖의 실패는 진행 중인 시나리오를 지우지 않는다 — 일시적 네트워크
      // 장애로 화면을 비우면 사용자는 훈련이 사라진 줄 안다. backoff 로 재시도한다.
      throw err
    }
  }, [fetchMissions, forgetActiveAttempt, reportActiveAttempt, token])

  usePolling(pollScenario, {
    intervalMs: MISSION_POLL_INTERVAL_MS,
    hiddenIntervalMs: MISSION_POLL_HIDDEN_MS,
    maxBackoffMs: MAX_BACKOFF_MS,
    enabled: activeScenario?.status === 'in_progress',
    restartKey: activeScenario?.scenario_id ?? '',
  })

  const runConfirmedAction = async () => {
    const action = confirmation?.action
    const kind = confirmation?.kind ?? null
    setConfirmation(null)
    // 요청 중 중복 실행을 막는다. 확인 모달을 두 번 눌러도 요청은 한 번만 나간다.
    if (!action || loading) return
    setLoading(true)
    setPendingAction(kind)
    setError(null)
    try {
      await action()
    } finally {
      setLoading(false)
      setPendingAction(null)
    }
  }

  // ── 정적 미션 핸들러 ──────────────────────────────────────

  const handleStartMission = (missionId: string) => {
    // 진행 중인 시도가 있으면 열지 않는다. 서버도 거절하지만 누르기 전에 막는다.
    if (activeAttemptId) return
    setStartError(null)
    setStartRequest({ kind: 'mission', missionId })
  }

  /*
   * 목록이 진행 중인 시도를 복원했는데 시작 시트가 열려 있으면 닫는다. 시작해 봐야 서버가
   * "이미 진행 중"으로 거절한다. (방금 이 시트로 시작한 경우는 isStarting 동안 닫지 않는다)
   */
  useEffect(() => {
    if (activeAttemptId && startRequest && !isStarting) setStartRequest(null)
  }, [activeAttemptId, isStarting, startRequest])

  /** 결과 시트를 연다. 같은 시도의 끝이 두 경로(완료 확인·폴링)로 와도 한 번만 연다. */
  const openDebrief = (attemptId: string | null, data: Debrief, again: StartRequest) => {
    if (!attemptId || debriefedAttemptRef.current === attemptId) return
    debriefedAttemptRef.current = attemptId
    setDebrief({ data, again })
  }

  /**
   * 서버 기록으로 결과를 확정해 연다 (BE-30). 시간 초과·AI 시나리오처럼 끝난 응답에 점수나 시각이
   * 없을 때 쓴다. 조회가 실패하면 `fallback` 이 있을 때만 그것을 보여 준다 — 끝난 이유를 모르면
   * 지어내지 않는다.
   */
  const openDebriefFromServer = async (
    attemptId: string | null,
    base: Debrief,
    again: StartRequest,
    fallback: Debrief | null,
  ) => {
    if (!attemptId || debriefedAttemptRef.current === attemptId) return
    try {
      const attempt = await getAttempt(token, attemptId)
      if (attempt.status === 'in_progress') return
      openDebrief(attemptId, {
        ...base,
        outcome: outcomeOf(attempt.status),
        finalScore: attempt.final_score,
        durationSeconds: attemptDuration(attempt),
        hintsUsed: attempt.hints_used,
      }, again)
    } catch {
      if (fallback) openDebrief(attemptId, fallback, again)
    }
  }

  /**
   * 시작 시트의 확정 (FE-27). 성공할 때까지 시트를 닫지 않고, 실패하면 이유를 시트 안에
   * 남긴다 — 장애 주입은 몇 초 걸릴 수 있고 그동안 무슨 일이 일어나는지 보여야 한다.
   */
  const confirmStart = async () => {
    if (!startRequest || isStarting) return
    setIsStarting(true)
    setStartError(null)
    try {
      if (startRequest.kind === 'mission') {
        const attempt = await startMission(token, startRequest.missionId)
        startedHereRef.current = attempt.id
        rememberActiveAttempt('static_mission')
        setActiveMissionId(startRequest.missionId)
        setActiveMissionEnvironment(attempt.environment)
        setHintsUsed(0)
        reportActiveAttempt({
          attemptId: attempt.id,
          attemptType: 'static_mission',
          environment: attempt.environment,
          status: attempt.status,
        })
        setStatusRefreshKey((k) => k + 1)
      } else {
        await startRandomScenario(token, selectedDifficulty, environment, demoAiUnlocked)
        rememberActiveAttempt('ai_scenario')
        // ScenarioResponse 에는 attempt id 가 없다. 요약은 서버 status 로 만든다.
        let started: ScenarioStatusResponse
        try {
          started = await getScenarioStatus(token)
        } catch {
          /*
           * 생성과 주입은 끝났고 상태 조회만 실패했다. 다시 시작하게 하면 서버가 "이미 진행 중"으로
           * 거절하므로, 시트를 닫고 목록 조회가 진행 중인 시도를 복원하게 둔다.
           */
          setStartRequest(null)
          await fetchMissions()
          return
        }
        startedHereRef.current = started.attempt_id
        setActiveScenario(started)
        setScenarioHintsUsed(started.hints_used)
        reportActiveAttempt({
          attemptId: started.attempt_id,
          attemptType: 'ai_scenario',
          environment: started.environment,
          status: started.status,
        })
      }
      if (showFirstRunGuide) onFirstRunGuideSeen?.()
      setStartRequest(null)
      await fetchMissions()
    } catch (err) {
      setStartError(
        err instanceof Error
          ? err.message
          : startRequest.kind === 'mission'
            ? '미션 시작에 실패했습니다.'
            : 'AI 시나리오 시작에 실패했습니다.',
      )
    } finally {
      setIsStarting(false)
    }
  }

  /** 정적 미션이 끝났을 때의 결과. 점수·시간은 서버 attempt 값만 쓴다. */
  const debriefForMission = (attempt: MissionAttemptResponse, mission: MissionResponse | null): Debrief => ({
    outcome: outcomeOf(attempt.status),
    missionTitle: mission ? getMissionCopy(mission).name : '미션',
    environmentLabel: getEnvironmentMeta(attempt.environment).label,
    finalScore: attempt.final_score,
    baseScore: mission?.base_score ?? null,
    durationSeconds: attemptDuration(attempt),
    hintsUsed: attempt.hints_used,
    cause: mission ? getMissionCause(mission.chaos_type) : null,
    commands: [...commandLogRef.current],
    commandsPartial: commandsPartialRef.current,
  })

  const handleCheckMission = async () => {
    if (loading) return
    /*
     * 자동 채점 300ms 목표는 API 응답과 화면 반영을 구분해 재야 한다 (FE-20).
     * 둘을 합쳐 재면 어느 쪽이 느린지 알 수 없다.
     */
    markStart(PERF.MISSION_CHECK_API)
    markStart(PERF.MISSION_CHECK_COMMIT)
    setLoading(true)
    setPendingAction('check')
    setError(null)
    try {
      setCheckFeedback(null)
      const result = await checkMission(token)
      measureSince(PERF.MISSION_CHECK_API)
      if (result.attempt.status !== 'completed') {
        setCheckFeedback(result.message || '리소스 상태를 다시 확인해 주세요.')
      } else {
        openDebrief(result.attempt.id, debriefForMission(result.attempt, activeMission), {
          kind: 'mission',
          missionId: activeMissionId as string,
        })
        forgetActiveAttempt()
        setActiveMissionId(null)
        setActiveMissionEnvironment(null)
        setHintsUsed(0)
        reportActiveAttempt(null)
        // 점수·MTTR 을 프론트에서 더하지 않고 서버 값을 다시 읽게 한다 (FE-15).
        onAttemptCompleted?.(result.attempt.id)
        await fetchMissions()
      }
      // 화면 반영까지 포함한 시간. 다음 frame 이 그려진 뒤 찍는다.
      await nextFrame()
      measureSince(PERF.MISSION_CHECK_COMMIT)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '미션 확인에 실패했습니다.'
      setError(msg)
      showToast('error', msg)
    } finally {
      setLoading(false)
      setPendingAction(null)
    }
  }

  const handleAbandonMission = () => {
    setConfirmation({
      title: '미션 포기',
      message: '진행 중인 미션을 포기하시겠습니까? 점수는 0점으로 처리됩니다.',
      confirmLabel: '포기',
      danger: true,
      kind: 'abandon',
      action: async () => {
        try {
          const attempt = await abandonMission(token)
          openDebrief(attempt.id, debriefForMission(attempt, activeMission), {
            kind: 'mission',
            missionId: activeMissionId as string,
          })
          forgetActiveAttempt()
          setActiveMissionId(null)
          setHintsUsed(0)
          reportActiveAttempt(null)
          await fetchMissions()
        } catch (err) {
          const msg = err instanceof Error ? err.message : '미션 포기에 실패했습니다.'
          setError(msg)
          showToast('error', msg)
        }
      },
    })
  }

  const canUseTutor = hasCapability(capabilities, 'tutor')

  /** 산 힌트를 보여 준다. 튜터가 있으면 튜터가 바로 답하고, 없으면 단계만 알린다. */
  const revealHint = (level: number) => {
    if (canUseTutor) {
      setAutoHintKey((key) => key + 1)
      onHintUsed?.()
    } else {
      showToast('info', `힌트 ${Math.min(level, 3)}단계가 열렸습니다.`)
    }
  }

  const handleUseHint = () => {
    const penalty = activeMission?.hint_penalty
    setConfirmation({
      title: '힌트 사용',
      message: `${penalty ? `${penalty}점이 깎입니다. ` : '점수가 깎입니다. '}${
        canUseTutor ? '튜터가 한 단계 더 구체적인 힌트를 바로 보여 줍니다.' : '힌트 단계가 한 단계 올라갑니다.'
      }`,
      confirmLabel: penalty ? `힌트 사용 −${penalty}점` : '힌트 사용',
      kind: 'hint',
      action: async () => {
        try {
          const attempt = await requestHint(token)
          setHintsUsed(attempt.hints_used)
          setStatusRefreshKey((k) => k + 1)
          revealHint(attempt.hints_used)
        } catch (err) {
          const msg = err instanceof Error ? err.message : '힌트 사용에 실패했습니다.'
          setError(msg)
          showToast('error', msg)
        }
      },
    })
  }

  const handleStatusChange = useCallback(
    (status: MissionStatusResponse) => setHintsUsed(status.attempt.hints_used),
    [],
  )
  /**
   * 폴링이 시도의 끝을 알렸다 (FE-27). 예전에는 시간 초과가 아무 말 없이 끝났다.
   * 서버가 끝난 상태를 알려 준 경우에만 결과 시트를 띄운다 — 404 로 시도가 사라졌으면
   * 무엇으로 끝났는지 모르므로 지어내지 않는다.
   */
  // MissionStatus 가 최신 콜백을 ref 로 들고 있어 렌더마다 새로 만들어도 폴링이 다시 시작되지 않는다.
  const handleMissionEnd = (status: MissionStatusResponse | null, lastRemainingSeconds: number | null) => {
    if (status && activeMissionId) {
      openDebrief(status.attempt.id, debriefForMission(status.attempt, activeMission), {
        kind: 'mission',
        missionId: activeMissionId,
      })
    } else if (activeMissionId) {
      /*
       * 서버는 시간이 다 된 시도를 정리한 뒤 404 를 준다. 들고 있던 시도 id 로 끝난 기록을 조회해
       * 결과·최종 점수·끝난 시각을 서버 값으로 보여 준다 (BE-30). 조회가 실패하면 남은 시간이
       * 거의 0 이었을 때만 시간 초과로 보고, 받지 못한 점수는 비워 둔다.
       */
      const base: Debrief = {
        outcome: 'failed',
        missionTitle: activeMission ? getMissionCopy(activeMission).name : '미션',
        environmentLabel: getEnvironmentMeta(activeMissionEnvironment ?? environment).label,
        finalScore: null,
        baseScore: activeMission?.base_score ?? null,
        durationSeconds: activeMission?.time_limit ?? null,
        hintsUsed,
        cause: activeMission ? getMissionCause(activeMission.chaos_type) : null,
        commands: [...commandLogRef.current],
        commandsPartial: commandsPartialRef.current,
      }
      const likelyTimedOut = lastRemainingSeconds !== null && lastRemainingSeconds <= TIMEOUT_INFERENCE_SECONDS
      void openDebriefFromServer(activeAttemptId, base, { kind: 'mission', missionId: activeMissionId }, likelyTimedOut ? base : null)
    }
    forgetActiveAttempt()
    setActiveMissionId(null)
    setHintsUsed(0)
    reportActiveAttempt(null)
    void fetchMissions()
  }

  // ── AI 시나리오 핸들러 ─────────────────────────────────────

  const handleStartScenario = () => {
    setStartError(null)
    setStartRequest({ kind: 'scenario' })
  }

  /**
   * AI 시나리오가 끝났을 때의 결과. 시나리오 응답에는 종료 시각이 없어 걸린 시간을 비운다 —
   * 마지막 폴링의 경과 시간은 실제 끝난 시각과 다르다.
   */
  const debriefForScenario = (outcome: DebriefOutcome, scenario: ScenarioStatusResponse, finalScore: number | null): Debrief => ({
    outcome,
    missionTitle: scenario.title,
    environmentLabel: getEnvironmentMeta(scenario.environment).label,
    finalScore,
    baseScore: null,
    durationSeconds: null,
    hintsUsed: Math.max(scenario.hints_used, scenarioHintsUsed),
    cause: null,
    commands: [...commandLogRef.current],
    commandsPartial: commandsPartialRef.current,
  })

  scenarioEndedRef.current = (status) => {
    if (status) {
      const base = debriefForScenario(outcomeOf(status.status), status, null)
      void openDebriefFromServer(status.attempt_id, base, { kind: 'scenario' }, base)
      return
    }
    // 404 — 끝난 기록을 조회한다. 실패하면 남은 시간이 거의 0 이었을 때만 시간 초과로 본다.
    if (activeScenario) {
      const base = debriefForScenario('failed', activeScenario, null)
      const likelyTimedOut = activeScenario.remaining_seconds <= TIMEOUT_INFERENCE_SECONDS
      void openDebriefFromServer(activeScenario.attempt_id, base, { kind: 'scenario' }, likelyTimedOut ? base : null)
    }
  }

  const handleCheckScenario = async () => {
    if (loading) return
    setLoading(true)
    setPendingAction('check')
    setError(null)
    try {
      setCheckFeedback(null)
      const result = await checkScenario(token)
      if (!result.resolved) {
        setCheckFeedback(result.message || '정상화 조건을 아직 만족하지 못했습니다. 상태를 다시 확인해 주세요.')
      } else if (activeScenario) {
        // 완료 응답에는 시각이 없다. 서버 기록으로 걸린 시간을 채우고, 조회가 실패해도 점수는 응답 값으로 보여 준다.
        const base = debriefForScenario('completed', activeScenario, result.score)
        void openDebriefFromServer(activeScenario.attempt_id, base, { kind: 'scenario' }, base)
      }
      if (result.resolved) {
        // 상태를 비우기 전에 attemptId 를 잡아둔다 — 완료 이벤트 중복 판정에 쓰인다.
        const completedAttemptId = activeScenario?.attempt_id ?? null
        forgetActiveAttempt()
        setActiveScenario(null)
        setScenarioHintsUsed(0)
        reportActiveAttempt(null)
        if (completedAttemptId) onAttemptCompleted?.(completedAttemptId)
        await fetchMissions()
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'AI 시나리오 확인에 실패했습니다.'
      setError(msg)
      showToast('error', msg)
    } finally {
      setLoading(false)
      setPendingAction(null)
    }
  }

  const handleAbandonScenario = () => {
    setConfirmation({
      title: 'AI 시나리오 포기',
      message: '진행 중인 AI 시나리오를 포기하시겠습니까?',
      confirmLabel: '포기',
      danger: true,
      kind: 'abandon',
      action: async () => {
        try {
          await abandonScenario(token)
          if (activeScenario) {
            const base = debriefForScenario('abandoned', activeScenario, null)
            void openDebriefFromServer(activeScenario.attempt_id, base, { kind: 'scenario' }, base)
          }
          forgetActiveAttempt()
          setActiveScenario(null)
          setScenarioHintsUsed(0)
          reportActiveAttempt(null)
          await fetchMissions()
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'AI 시나리오 포기에 실패했습니다.'
          setError(msg)
          showToast('error', msg)
        }
      },
    })
  }

  const handleUseScenarioHint = () => {
    setConfirmation({
      title: '힌트 사용',
      message: `점수가 깎입니다. ${
        canUseTutor ? '튜터가 한 단계 더 구체적인 힌트를 바로 보여 줍니다.' : '힌트 단계가 한 단계 올라갑니다.'
      }`,
      confirmLabel: '힌트 사용',
      kind: 'hint',
      action: async () => {
        try {
          const attempt = await requestScenarioHint(token)
          setScenarioHintsUsed(attempt.hints_used)
          revealHint(attempt.hints_used)
        } catch (err) {
          const msg = err instanceof Error ? err.message : '힌트 사용에 실패했습니다.'
          setError(msg)
          showToast('error', msg)
        }
      },
    })
  }

  const isActiveScenario = activeScenario?.status === 'in_progress'
  const displayedMissions = activeMissionId
    ? missions.filter((mission) => mission.id === activeMissionId)
    : isActiveScenario
      ? []
    : missions

  /*
   * 서버가 이 환경에 광고하지 않는 기능은 그리지 않는다 (FE-22).
   * 백엔드 `assert_implemented` 가 요청을 거절하므로, 버튼을 눌러 오류를 받게
   * 하는 대신 화면에서 빼는 편이 맞다. 판정 근거가 없으면(null) 아무것도 숨기지
   * 않는다 — 규칙은 `hasCapability` 한 곳에 있다.
   */
  const canUseStaticMission = hasCapability(capabilities, 'static_mission')
  const canUseAiScenario = hasCapability(capabilities, 'ai_scenario')

  /*
   * 튜터 패널은 세 자리(정적 미션 / AI 시나리오 / 모바일 AI 시나리오)에서 같은 모양으로
   * 쓰인다. 세 번 적어 두면 한 곳만 고치는 사고가 나므로 여기서 만든다.
   * capability 가 없으면 아무것도 그리지 않는다 (FE-22).
   */
  const renderTutorPanel = (
    missionId: string,
    tutorEnvironment: EnvironmentId,
    tutorHintsUsed: number,
  ) => {
    if (!canUseTutor) return null
    const conversationKey = activeAttemptId ? `${activeAttemptId}:${tutorEnvironment}` : undefined
    // 보조 패널 자리가 있으면 거기에 고정해서 그린다. 없을 때만 떠 있는 튜터를 쓴다.
    if (tutorSlot) {
      return createPortal(
        <TutorChat
          token={token}
          missionId={missionId}
          conversationKey={conversationKey}
          environment={tutorEnvironment}
          hintsUsed={tutorHintsUsed}
          autoHintKey={autoHintKey}
          disabled={loading}
        />,
        tutorSlot,
      )
    }
    return (
      <TutorChat
        token={token}
        missionId={missionId}
        conversationKey={conversationKey}
        environment={tutorEnvironment}
        hintsUsed={tutorHintsUsed}
        autoHintKey={autoHintKey}
        disabled={loading}
        floating
        floatingOpen={isTutorFloatingOpen}
        onToggleFloating={() => setIsTutorFloatingOpen((open) => !open)}
      />
    )
  }

  /** 진행 상황은 터미널 위 인시던트 바 자리에 그린다 (FE-26). */
  const placeIncident = (node: React.ReactNode) => (incidentSlot ? createPortal(node, incidentSlot) : node)

  return (
    <div className={`mission-panel${activeMissionId || isActiveScenario ? ' mission-active' : ''}`}>
      <div className="mission-header">
        {/* 결과 시트가 닫힐 때 완료 확인 버튼은 사라지고 없다. focus 는 여기로 돌아온다. */}
        <h2 id="mission-list-heading" tabIndex={-1}>미션 목록</h2>
      </div>

      {/* 정적 미션 목록 */}
      <div className={`mission-list${activeMissionId || isActiveScenario ? ' active-only' : ''}`}>
        {error && (
          <div className="mission-error" role="alert">
            <span>{error}</span>
            {/* 목록 조회 실패일 때만 다시 시도를 준다. 액션 실패는 같은 버튼을 다시 누르면 된다. */}
            {missionsStatus === 'error' && (
              <button type="button" className="ui-button small" onClick={() => void fetchMissions()}>
                다시 시도
              </button>
            )}
          </div>
        )}
        {isActiveScenario && activeScenario && (
          <div className="mission-card active ai-mission-card">
            <span className="mission-index" aria-hidden="true">AI</span>
            <span className="mission-title">{activeScenario.title}</span>
            <span className="mission-description">{activeScenario.student_brief}</span>
            <span className="mission-info">
              <span>AI 문제 · 난이도 {DIFFICULTY_LABELS[activeScenario.difficulty as Difficulty] ?? activeScenario.difficulty}</span>
            </span>
            <span className="mission-state mission-active-label">
              <span className="ui-live-dot" aria-hidden="true" />
              진행 중
            </span>
          </div>
        )}
        {/*
          * 목록이 비는 이유는 세 가지고 문구가 달라야 한다 (FE-06).
          * 조회 실패는 위 mission-error 배너가 이유까지 말하므로 여기서 반복하지 않는다.
          */}
        {!canUseStaticMission ? (
          /*
           * 서버가 이 환경에 static_mission 을 광고하지 않는다 (FE-22).
           * "아직 준비 중"과 다른 사실이라 문구를 나눈다 — 기다리면 열리는 게 아니다.
           * (진행 중인 AI 시나리오 카드는 위에서 이미 그렸으므로 그때는 아무것도 넣지 않는다)
           */
          !isActiveScenario && (
            <div className="empty-state">
              {getEnvironmentMeta(environment).label} 환경은 기본 미션을 제공하지 않습니다.
            </div>
          )
        ) : displayedMissions.length === 0 && !isActiveScenario && missionsStatus !== 'error' ? (
          <div className="empty-state">
            {missionsStatus === 'loading'
              ? '미션을 불러오는 중...'
              : `${getEnvironmentMeta(environment).label} 미션은 아직 준비 중입니다.`}
          </div>
        ) : (
          displayedMissions.map((mission) => (
            <MissionCard
              key={mission.id}
              mission={mission}
              isActive={mission.id === activeMissionId}
              onStart={handleStartMission}
            />
          ))
        )}
      </div>

      {/* 정적 미션 진행 중 상태 */}
      {activeMissionId && (
        <>
          {placeIncident(
            <MissionStatus
              token={token}
              refreshKey={statusRefreshKey}
              pendingAction={pendingAction}
              hintPenalty={activeMission?.hint_penalty}
              missionTitle={activeMission ? getMissionCopy(activeMission).name : undefined}
              environmentLabel={getEnvironmentMeta(activeMissionEnvironment ?? environment).label}
              feedback={checkFeedback}
              onStatusChange={handleStatusChange}
              onMissionEnd={handleMissionEnd}
              onCheck={handleCheckMission}
              onAbandon={handleAbandonMission}
              onHint={handleUseHint}
            />,
          )}
          {renderTutorPanel(activeMissionId, activeMissionEnvironment ?? environment, hintsUsed)}
        </>
      )}

      {isActiveScenario && activeScenario && (
        <>
          {/* ScenarioStatusResponse 에는 힌트 감점이 없어 비용을 적지 않는다. */}
          {placeIncident(
            <MissionStatusView
              title="AI 시나리오 진행 상황"
              missionTitle={activeScenario.title}
              environmentLabel={getEnvironmentMeta(activeScenario.environment).label}
              remainingSeconds={activeScenario.remaining_seconds}
              score={activeScenario.current_score}
              hintsUsed={activeScenario.hints_used}
              pendingAction={pendingAction}
              busy={loading}
              abandonLabel="포기"
              feedback={checkFeedback}
              onCheck={handleCheckScenario}
              onHint={handleUseScenarioHint}
              onAbandon={handleAbandonScenario}
            />,
          )}
          {renderTutorPanel(activeScenario.scenario_id, activeScenario.environment, scenarioHintsUsed)}
        </>
      )}

      {/* AI 문제 더 풀기 섹션. 서버가 ai_scenario 를 광고하지 않으면 그리지 않는다 (FE-22) */}
      {canUseAiScenario && !activeMissionId && !isActiveScenario && (
        <section className="ai-scenario-section" aria-labelledby="ai-scenario-title">
          {unlockStatus && !isAiUnlocked ? (
            /*
             * 잠긴 동안은 한 줄 요약 + 진행 막대만 보이고 긴 설명은 접어 둔다 (FE-29).
             * 펼친 설명이 1366×768 에서 미션 목록 자리를 절반 가까이 차지했다.
             */
            <details className="ai-lock">
              <summary>
                <LockIcon />
                <span className="ai-lock-title" id="ai-scenario-title">AI 문제 더 풀기</span>
                <span className="ai-lock-count">
                  기본 미션 <span className="ai-lock-number">{unlockStatus.completed_static}/{unlockStatus.total_static}</span> 완료
                </span>
                <span className="ai-lock-bar" aria-hidden="true">
                  <i
                    style={{
                      width: `${unlockStatus.total_static ? Math.min(100, (unlockStatus.completed_static / unlockStatus.total_static) * 100) : 0}%`,
                    }}
                  />
                </span>
              </summary>
              <p>
                AI 문제 모드는 계정 단위로 열립니다. Kubernetes · Docker · Linux 를 합친
                서로 다른 기본 미션 {unlockStatus.total_static}개를 모두 완료하면 모든 환경에서
                활성화됩니다.
                {closedEnvironmentLabels.length > 0 && (
                  <>
                    {' '}
                    다만 이 서버에서는 {closedEnvironmentLabels.join(' · ')} 환경이 열려 있지 않아
                    지금은 조건을 모두 채울 수 없습니다.
                  </>
                )}
              </p>
            </details>
          ) : (
            <div className="ai-section-header">
              <h3 id="ai-scenario-title">AI 문제 더 풀기</h3>
            </div>
          )}

          {!isAiUnlocked && isDemoMode() && (
            <button
              type="button"
              className="ui-button plain small demo-unlock-btn"
              onClick={unlockAiScenariosForDemo}
            >
              시연용 잠금 해제
            </button>
          )}

          {/* 잠금 해제 + AI 시나리오 없을 때: 난이도 선택 */}
          {isAiUnlocked && !activeScenario && (
            <div className="ai-difficulty-selector">
              <span className="ai-selector-label" id="ai-difficulty-label">난이도</span>
              {/*
                * 네이티브 radio 를 세그먼트 모양으로 쓴다. 화살표 키 이동과 선택 상태 낭독을
                * 브라우저가 맡으므로 roving tabindex 를 직접 만들지 않는다.
                */}
              <div className="segmented" role="radiogroup" aria-labelledby="ai-difficulty-label">
                {(Object.keys(DIFFICULTY_LABELS) as Difficulty[]).map((d) => (
                  <label key={d} className="segmented-option">
                    <input
                      type="radio"
                      name="ai-difficulty"
                      value={d}
                      checked={selectedDifficulty === d}
                      onChange={() => setSelectedDifficulty(d)}
                    />
                    <span>
                      <CheckIcon />
                      {DIFFICULTY_LABELS[d]}
                    </span>
                  </label>
                ))}
              </div>
              <button
                type="button"
                className="ui-button primary ai-start-btn"
                onClick={handleStartScenario}
                disabled={loading}
              >
                AI 장애 생성 시작
              </button>
            </div>
          )}
        </section>
      )}

      {startRequest && (() => {
        const mission = startRequest.kind === 'mission'
          ? missions.find((item) => item.id === startRequest.missionId) ?? null
          : null
        const copy = mission ? getMissionCopy(mission) : null
        return (
          <StartSheet
            kind={startRequest.kind}
            title={copy?.name ?? 'AI 장애 생성'}
            description={
              copy?.description
              ?? '선택한 난이도에 맞춰 AI가 새 장애 상황을 만듭니다. 어떤 장애인지는 시작한 뒤 브리핑에서 확인할 수 있습니다.'
            }
            environmentLabel={getEnvironmentMeta(mission?.environment ?? environment).label}
            tierLabel={mission ? `레벨 ${mission.level}` : `난이도 ${DIFFICULTY_LABELS[selectedDifficulty]}`}
            timeLimitSeconds={mission?.time_limit}
            baseScore={mission?.base_score}
            hintPenalty={mission?.hint_penalty}
            showFirstRunGuide={showFirstRunGuide}
            busy={isStarting}
            error={startError}
            onConfirm={() => void confirmStart()}
            onCancel={() => setStartRequest(null)}
          />
        )
      })()}
      {debrief && (
        <DebriefSheet
          debrief={debrief.data}
          primaryLabel={
            debrief.data.outcome === 'completed'
              ? debrief.again.kind === 'scenario' ? 'AI 문제 하나 더' : '다음 미션 고르기'
              : '다시 도전'
          }
          onPrimary={() => {
            const again = debrief.again
            const completedStatic = debrief.data.outcome === 'completed' && again.kind === 'mission'
            setDebrief(null)
            // 완료한 정적 미션은 다음 미션을 고르게 목록으로 돌려보낸다. 나머지는 같은 시작 시트를 다시 연다.
            if (!completedStatic) {
              setStartError(null)
              setStartRequest(again)
            }
          }}
          onClose={() => setDebrief(null)}
          returnFocus={() => document.getElementById('mission-list-heading')}
        />
      )}
      {confirmation && (
        <ConfirmModal
          title={confirmation.title}
          message={confirmation.message}
          confirmLabel={confirmation.confirmLabel}
          danger={confirmation.danger}
          onConfirm={() => void runConfirmedAction()}
          onCancel={() => setConfirmation(null)}
        />
      )}
      {toast && <Toast key={toast.id} {...toast} onClose={() => setToast(null)} />}
    </div>
  )
}

export default MissionList
