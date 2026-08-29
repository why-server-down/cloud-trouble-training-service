import React, { useCallback, useEffect, useState } from 'react'
import ConfirmModal from '../Feedback/ConfirmModal'
import Toast, { ToastMessage } from '../Feedback/Toast'
import {
  abandonMission,
  abandonScenario,
  ApiError,
  checkMission,
  checkScenario,
  getMissionStatus,
  getScenarioStatus,
  getUnlockStatus,
  listMissions,
  MissionResponse,
  MissionStatusResponse,
  requestHint,
  requestScenarioHint,
  ScenarioStatusResponse,
  startMission,
  startRandomScenario,
  UnlockStatusResponse,
} from '../../services/api'
import { getEnvironmentMeta } from '../../config/environments'
import { ActiveAttemptSummary, AttemptType, EnvironmentId } from '../../types/training'
import MissionCard from './MissionCard'
import MissionStatus from './MissionStatus'
import TutorChat from './TutorChat'
import './Mission.css'

interface MissionListProps {
  token: string
  storageScope: string | null
  /** 현재 선택된 훈련 환경. AI 시나리오 생성 요청에 그대로 실려 나간다. */
  environment: EnvironmentId
  /** 서버 status 로 만든 활성 시도 요약. 없으면 null. App 이 이걸로 환경 탭을 잠근다. */
  onActiveAttemptChange: (summary: ActiveAttemptSummary | null) => void
}

interface Confirmation {
  title: string
  message: string
  confirmLabel: string
  danger?: boolean
  action: () => Promise<void>
}

type Difficulty = 'beginner' | 'intermediate' | 'advanced' | 'expert'

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  beginner: 'Beginner',
  intermediate: 'Intermediate',
  advanced: 'Advanced',
  expert: 'Expert',
}

const ACTIVE_ATTEMPT_TYPE_KEY = 'activeAttemptType'
const DEMO_AI_UNLOCK_STORAGE_KEY = 'demoAiScenarioUnlocked'
const scopedStorageKey = (key: string, scope: string | null) => `${key}:${scope || 'anonymous'}`

const MissionList: React.FC<MissionListProps> = ({ token, storageScope, environment, onActiveAttemptChange }) => {
  const [missions, setMissions] = useState<MissionResponse[]>([])
  const [activeMissionId, setActiveMissionId] = useState<string | null>(null)
  const [hintsUsed, setHintsUsed] = useState(0)
  const [statusRefreshKey, setStatusRefreshKey] = useState(0)
  const [loading, setLoading] = useState(false)
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

  const showToast = useCallback((kind: ToastMessage['kind'], text: string) => setToast({ kind, text }), [])

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
        setHintsUsed(0)
      }
      if (summary?.attemptType !== 'ai_scenario') {
        setActiveScenario(null)
        setScenarioHintsUsed(0)
      }

      // 서버에 활성 attempt 가 없으면 stale localStorage 값을 지운다.
      if (summary) rememberActiveAttempt(summary.attemptType)
      else forgetActiveAttempt()

      onActiveAttemptChange(summary)

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
  }, [environment, forgetActiveAttempt, onActiveAttemptChange, rememberActiveAttempt, storageScope, token])

  useEffect(() => {
    setDemoAiUnlocked(localStorage.getItem(scopedStorageKey(DEMO_AI_UNLOCK_STORAGE_KEY, storageScope)) === 'true')
    setMissions([])
    setMissionsStatus('loading')
    setError(null)
    setActiveMissionId(null)
    setActiveScenario(null)
    setHintsUsed(0)
    setScenarioHintsUsed(0)
    onActiveAttemptChange(null)
  }, [environment, onActiveAttemptChange, storageScope])

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

  // AI 시나리오 진행 중일 때 1초마다 상태 갱신
  useEffect(() => {
    if (!activeScenario || activeScenario.status !== 'in_progress') return
    const interval = window.setInterval(async () => {
      try {
        const status = await getScenarioStatus(token)
        setActiveScenario(status)
        setScenarioHintsUsed(status.hints_used)
        if (status.status !== 'in_progress') {
          forgetActiveAttempt()
          setActiveScenario(null)
          setScenarioHintsUsed(0)
          onActiveAttemptChange(null)
          await fetchMissions()
        }
      } catch {
        // 시나리오 종료 시 404 발생 → 정리
        forgetActiveAttempt()
        setActiveScenario(null)
        onActiveAttemptChange(null)
      }
    }, 1000)
    return () => window.clearInterval(interval)
  }, [activeScenario, token, onActiveAttemptChange, fetchMissions, forgetActiveAttempt])

  const runConfirmedAction = async () => {
    const action = confirmation?.action
    setConfirmation(null)
    if (!action || loading) return
    setLoading(true)
    setError(null)
    try {
      await action()
    } finally {
      setLoading(false)
    }
  }

  // ── 정적 미션 핸들러 ──────────────────────────────────────

  const handleStartMission = (missionId: string) => {
    setConfirmation({
      title: '미션 시작',
      message: '선택한 미션을 시작하시겠습니까?',
      confirmLabel: '시작',
      action: async () => {
        try {
          const attempt = await startMission(token, missionId)
          rememberActiveAttempt('static_mission')
          setActiveMissionId(missionId)
          setHintsUsed(0)
          onActiveAttemptChange({
            attemptId: attempt.id,
            attemptType: 'static_mission',
            environment: attempt.environment,
            status: attempt.status,
          })
          setStatusRefreshKey((k) => k + 1)
          await fetchMissions()
          showToast('success', '미션을 시작했습니다. 터미널에서 문제를 해결해 보세요.')
        } catch (err) {
          const msg = err instanceof Error ? err.message : '미션 시작에 실패했습니다.'
          setError(msg)
          showToast('error', msg)
        }
      },
    })
  }

  const handleCheckMission = async () => {
    if (loading) return
    setLoading(true)
    setError(null)
    try {
      const result = await checkMission(token)
      showToast(
        result.attempt.status === 'completed' ? 'success' : 'info',
        result.attempt.status === 'completed'
          ? `미션을 완료했습니다. 최종 점수: ${result.attempt.final_score}점`
          : '아직 해결되지 않았습니다. 리소스 상태를 다시 확인해 주세요.',
      )
      if (result.attempt.status === 'completed') {
        forgetActiveAttempt()
        setActiveMissionId(null)
        setHintsUsed(0)
        onActiveAttemptChange(null)
        await fetchMissions()
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '미션 확인에 실패했습니다.'
      setError(msg)
      showToast('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const handleAbandonMission = () => {
    setConfirmation({
      title: '미션 포기',
      message: '진행 중인 미션을 포기하시겠습니까? 점수는 0점으로 처리됩니다.',
      confirmLabel: '포기',
      danger: true,
      action: async () => {
        try {
          await abandonMission(token)
          forgetActiveAttempt()
          setActiveMissionId(null)
          setHintsUsed(0)
          onActiveAttemptChange(null)
          await fetchMissions()
          showToast('info', '미션을 포기했습니다.')
        } catch (err) {
          const msg = err instanceof Error ? err.message : '미션 포기에 실패했습니다.'
          setError(msg)
          showToast('error', msg)
        }
      },
    })
  }

  const handleUseHint = () => {
    setConfirmation({
      title: '힌트 사용',
      message: '힌트를 사용하시겠습니까? 현재 미션 점수가 차감됩니다.',
      confirmLabel: '힌트 사용',
      action: async () => {
        try {
          const attempt = await requestHint(token)
          setHintsUsed(attempt.hints_used)
          setStatusRefreshKey((k) => k + 1)
          showToast('info', '힌트를 사용했습니다. 현재 점수를 확인해 주세요.')
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
  const handleMissionEnd = useCallback(() => {
    forgetActiveAttempt()
    setActiveMissionId(null)
    setHintsUsed(0)
    onActiveAttemptChange(null)
    void fetchMissions()
  }, [fetchMissions, forgetActiveAttempt, onActiveAttemptChange])

  // ── AI 시나리오 핸들러 ─────────────────────────────────────

  const handleStartScenario = () => {
    setConfirmation({
      title: 'AI 시나리오 시작',
      message: `${DIFFICULTY_LABELS[selectedDifficulty]} 난이도로 AI 장애를 생성하시겠습니까?`,
      confirmLabel: '시작',
      action: async () => {
        try {
          const scenario = await startRandomScenario(token, selectedDifficulty, environment, demoAiUnlocked)
          rememberActiveAttempt('ai_scenario')
          // ScenarioResponse 에는 attempt id 가 없다. 요약은 서버 status 로 만든다.
          const started = await getScenarioStatus(token)
          setActiveScenario(started)
          setScenarioHintsUsed(started.hints_used)
          onActiveAttemptChange({
            attemptId: started.attempt_id,
            attemptType: 'ai_scenario',
            environment: started.environment,
            status: started.status,
          })
          await fetchMissions()
          showToast('success', `"${scenario.title}" 시나리오가 시작됐습니다. 터미널에서 문제를 해결해 보세요.`)
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'AI 시나리오 시작에 실패했습니다.'
          setError(msg)
          showToast('error', msg)
        }
      },
    })
  }

  const handleCheckScenario = async () => {
    if (loading) return
    setLoading(true)
    setError(null)
    try {
      const result = await checkScenario(token)
      showToast(
        result.resolved ? 'success' : 'info',
        result.resolved
          ? `시나리오를 완료했습니다! 최종 점수: ${result.score}점`
          : '아직 정상화 조건을 만족하지 못했습니다. 상태를 다시 확인해 주세요.',
      )
      if (result.resolved) {
        forgetActiveAttempt()
        setActiveScenario(null)
        setScenarioHintsUsed(0)
        onActiveAttemptChange(null)
        await fetchMissions()
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'AI 시나리오 확인에 실패했습니다.'
      setError(msg)
      showToast('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const handleAbandonScenario = () => {
    setConfirmation({
      title: 'AI 시나리오 포기',
      message: '진행 중인 AI 시나리오를 포기하시겠습니까?',
      confirmLabel: '포기',
      danger: true,
      action: async () => {
        try {
          await abandonScenario(token)
          forgetActiveAttempt()
          setActiveScenario(null)
          setScenarioHintsUsed(0)
          onActiveAttemptChange(null)
          await fetchMissions()
          showToast('info', 'AI 시나리오를 포기했습니다.')
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
      message: '힌트를 사용하시겠습니까? 점수가 차감됩니다.',
      confirmLabel: '힌트 사용',
      action: async () => {
        try {
          const attempt = await requestScenarioHint(token)
          setScenarioHintsUsed(attempt.hints_used)
          showToast('info', '힌트를 사용했습니다.')
        } catch (err) {
          const msg = err instanceof Error ? err.message : '힌트 사용에 실패했습니다.'
          setError(msg)
          showToast('error', msg)
        }
      },
    })
  }

  // 시나리오 시간 표시
  const scenarioTimeClass =
    activeScenario && activeScenario.remaining_seconds < 60
      ? 'danger'
      : activeScenario && activeScenario.remaining_seconds < 300
        ? 'warning'
        : ''
  const isActiveScenario = activeScenario?.status === 'in_progress'
  const scenarioMinutes = activeScenario ? Math.floor(activeScenario.remaining_seconds / 60) : 0
  const scenarioSeconds = activeScenario ? activeScenario.remaining_seconds % 60 : 0
  const displayedMissions = activeMissionId
    ? missions.filter((mission) => mission.id === activeMissionId)
    : isActiveScenario
      ? []
    : missions

  return (
    <div className={`mission-panel${activeMissionId || isActiveScenario ? ' mission-active' : ''}`}>
      <div className="mission-header">
        <span className="panel-index">RUNBOOK / INCIDENT QUEUE</span>
        <h2>미션 목록</h2>
      </div>

      {/* 정적 미션 목록 */}
      <div className={`mission-list${activeMissionId || isActiveScenario ? ' active-only' : ''}`}>
        {error && <div className="mission-error">{error}</div>}
        {isActiveScenario && activeScenario && (
          <div className="mission-card active ai-mission-card">
            <span className="mission-card-header">
              <span className="mission-title">{activeScenario.title}</span>
              <span className="mission-level">{DIFFICULTY_LABELS[activeScenario.difficulty as Difficulty] ?? activeScenario.difficulty}</span>
            </span>
            <span className="mission-description">{activeScenario.student_brief}</span>
            <span className="mission-info">
              <span>남은 시간 {scenarioMinutes}:{scenarioSeconds.toString().padStart(2, '0')}</span>
              <span>현재 {activeScenario.current_score}점</span>
              <span>힌트 {activeScenario.hints_used}개</span>
            </span>
            <span className="mission-active-label">LIVE AI INCIDENT</span>
          </div>
        )}
        {/*
          * 목록이 비는 이유는 세 가지고 문구가 달라야 한다 (FE-06).
          * 조회 실패는 위 mission-error 배너가 이유까지 말하므로 여기서 반복하지 않는다.
          */}
        {displayedMissions.length === 0 && !isActiveScenario && missionsStatus !== 'error' ? (
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
          <MissionStatus
            token={token}
            refreshKey={statusRefreshKey}
            loading={loading}
            onStatusChange={handleStatusChange}
            onMissionEnd={handleMissionEnd}
            onCheck={handleCheckMission}
            onAbandon={handleAbandonMission}
            onHint={handleUseHint}
          />
          <TutorChat
            token={token}
            missionId={activeMissionId}
            hintsUsed={hintsUsed}
            disabled={loading}
            floating
            floatingOpen={isTutorFloatingOpen}
            onToggleFloating={() => setIsTutorFloatingOpen((open) => !open)}
          />
        </>
      )}

      {isActiveScenario && activeScenario && (
        <>
          <div className="mission-status-panel" data-tour="mission-progress">
            <div className="status-header">AI 시나리오 진행 상황</div>
            <div className="status-item">
              <span>남은 시간</span>
              <span className={`status-value ${scenarioTimeClass}`}>
                {scenarioMinutes}:{scenarioSeconds.toString().padStart(2, '0')}
              </span>
            </div>
            <div className="status-item">
              <span>현재 점수</span>
              <span className="status-value">{activeScenario.current_score}점</span>
            </div>
            <div className="status-item">
              <span>사용한 힌트</span>
              <span className="status-value">{activeScenario.hints_used}개</span>
            </div>
            <div className="status-actions">
              <button className="btn btn-success" type="button" onClick={handleCheckScenario} disabled={loading}>
                완료 확인
              </button>
              <button className="btn btn-warning" type="button" onClick={handleUseScenarioHint} disabled={loading}>
                힌트 사용
              </button>
              <button className="btn btn-danger" type="button" onClick={handleAbandonScenario} disabled={loading}>
                포기
              </button>
            </div>
          </div>
          <TutorChat
            token={token}
            missionId={activeScenario.scenario_id}
            hintsUsed={scenarioHintsUsed}
            disabled={loading}
            floating
            floatingOpen={isTutorFloatingOpen}
            onToggleFloating={() => setIsTutorFloatingOpen((open) => !open)}
          />
        </>
      )}

      {/* AI 문제 더 풀기 섹션 */}
      {!activeMissionId && !isActiveScenario && (
        <div className="ai-scenario-section">
          <div className="ai-section-header">
            <span className="panel-index">AI CHALLENGE MODE</span>
            {!isAiUnlocked && (
              <button
                type="button"
                className="demo-unlock-btn"
                onClick={unlockAiScenariosForDemo}
              >
                시연용 잠금 해제
              </button>
            )}
            <h3>AI 문제 더 풀기</h3>
          </div>

          {/* 잠금 상태 표시 */}
          {unlockStatus && !isAiUnlocked && (
            <div className="ai-lock-notice">
              <span className="ai-lock-icon">🔒</span>
              <span>
                AI 문제 모드는 계정 단위로 열립니다. 기본 미션을 모두 완료하면 모든 환경에서
                활성화됩니다 ({unlockStatus.completed_static}/{unlockStatus.total_static} 완료)
              </span>
            </div>
          )}

          {/* AI 시나리오 진행 중 */}
          {activeScenario && activeScenario.status === 'in_progress' && (
            <>
              <div className="ai-scenario-active">
                <div className="ai-scenario-title">{activeScenario.title}</div>
                <div className="ai-scenario-brief">{activeScenario.student_brief}</div>
                <div className="ai-difficulty-badge">{DIFFICULTY_LABELS[activeScenario.difficulty as Difficulty] ?? activeScenario.difficulty}</div>
              </div>
              <div className="mission-status-panel" data-tour="mission-progress">
                <div className="status-header">AI 시나리오 진행 상황</div>
                <div className="status-item">
                  <span>남은 시간</span>
                  <span className={`status-value ${scenarioTimeClass}`}>
                    {scenarioMinutes}:{scenarioSeconds.toString().padStart(2, '0')}
                  </span>
                </div>
                <div className="status-item">
                  <span>현재 점수</span>
                  <span className="status-value">{activeScenario.current_score}점</span>
                </div>
                <div className="status-item">
                  <span>사용한 힌트</span>
                  <span className="status-value">{activeScenario.hints_used}개</span>
                </div>
                <div className="status-actions">
                  <button className="btn btn-success" type="button" onClick={handleCheckScenario} disabled={loading}>
                    완료 확인
                  </button>
                  <button className="btn btn-warning" type="button" onClick={handleUseScenarioHint} disabled={loading}>
                    힌트 사용
                  </button>
                  <button className="btn btn-danger" type="button" onClick={handleAbandonScenario} disabled={loading}>
                    포기
                  </button>
                </div>
              </div>
              <TutorChat
                token={token}
                missionId={activeScenario.scenario_id}
                hintsUsed={scenarioHintsUsed}
                disabled={loading}
                floating
                floatingOpen={isTutorFloatingOpen}
                onToggleFloating={() => setIsTutorFloatingOpen((open) => !open)}
              />
            </>
          )}

          {/* 잠금 해제 + AI 시나리오 없을 때: 난이도 선택 */}
          {isAiUnlocked && !activeScenario && (
            <div className="ai-difficulty-selector">
              <div className="ai-selector-label">난이도 선택</div>
              <div className="difficulty-btns">
                {(Object.keys(DIFFICULTY_LABELS) as Difficulty[]).map((d) => (
                  <button
                    key={d}
                    type="button"
                    className={`difficulty-btn${selectedDifficulty === d ? ' selected' : ''}`}
                    onClick={() => setSelectedDifficulty(d)}
                  >
                    {DIFFICULTY_LABELS[d]}
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="btn ai-start-btn"
                onClick={handleStartScenario}
                disabled={loading}
              >
                AI 장애 생성 시작
              </button>
            </div>
          )}
        </div>
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
      {toast && <Toast {...toast} onClose={() => setToast(null)} />}
    </div>
  )
}

export default MissionList
