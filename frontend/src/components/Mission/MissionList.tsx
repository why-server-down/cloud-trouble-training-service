import React, { useCallback, useEffect, useState } from 'react'
import ConfirmModal from '../Feedback/ConfirmModal'
import Toast, { ToastMessage } from '../Feedback/Toast'
import {
  abandonMission,
  checkMission,
  getMissionStatus,
  listMissions,
  MissionStatusResponse,
  startMission,
  useHint,
} from '../../services/api'
import MissionCard from './MissionCard'
import MissionStatus from './MissionStatus'
import TutorChat from './TutorChat'
import './Mission.css'

interface Mission {
  id: string
  name: string
  level: number
  description: string
  chaos_type: string
  base_score: number
  time_limit: number
  hint_penalty: number
  is_unlocked: boolean
}

interface MissionListProps {
  token: string
}

interface Confirmation {
  title: string
  message: string
  confirmLabel: string
  danger?: boolean
  action: () => Promise<void>
}

const MissionList: React.FC<MissionListProps> = ({ token }) => {
  const [missions, setMissions] = useState<Mission[]>([])
  const [activeMissionId, setActiveMissionId] = useState<string | null>(null)
  const [hintsUsed, setHintsUsed] = useState(0)
  const [statusRefreshKey, setStatusRefreshKey] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<ToastMessage | null>(null)
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)

  const showToast = useCallback((kind: ToastMessage['kind'], text: string) => setToast({ kind, text }), [])

  const fetchMissions = useCallback(async () => {
    try {
      setError(null)
      setMissions(await listMissions(token))

      try {
        const status = await getMissionStatus(token)
        setActiveMissionId(status.attempt.mission_id)
        setHintsUsed(status.attempt.hints_used)
      } catch {
        setActiveMissionId(null)
        setHintsUsed(0)
      }
    } catch (err) {
      console.error('미션 목록 조회 실패:', err)
      setError('미션 목록을 불러오지 못했습니다.')
    }
  }, [token])

  useEffect(() => {
    void fetchMissions()
  }, [fetchMissions])

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

  const handleStartMission = (missionId: string) => {
    setConfirmation({
      title: '미션 시작',
      message: '선택한 미션을 시작하시겠습니까?',
      confirmLabel: '시작',
      action: async () => {
        try {
          await startMission(token, missionId)
          setActiveMissionId(missionId)
          setHintsUsed(0)
          setStatusRefreshKey((current) => current + 1)
          await fetchMissions()
          showToast('success', '미션을 시작했습니다. 터미널에서 문제를 해결해 보세요.')
        } catch (err) {
          const message = err instanceof Error ? err.message : '미션 시작에 실패했습니다.'
          setError(message)
          showToast('error', message)
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
          ? `미션을 완료했습니다. 최종 점수는 ${result.attempt.final_score}점입니다.`
          : '아직 해결되지 않았습니다. 리소스 상태를 다시 확인해 주세요.',
      )
      if (result.attempt.status === 'completed') {
        setActiveMissionId(null)
        setHintsUsed(0)
        await fetchMissions()
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '미션 확인에 실패했습니다.'
      setError(message)
      showToast('error', message)
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
          setActiveMissionId(null)
          setHintsUsed(0)
          await fetchMissions()
          showToast('info', '미션을 포기했습니다.')
        } catch (err) {
          const message = err instanceof Error ? err.message : '미션 포기에 실패했습니다.'
          setError(message)
          showToast('error', message)
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
          const attempt = await useHint(token)
          setHintsUsed(attempt.hints_used)
          setStatusRefreshKey((current) => current + 1)
          showToast('info', '힌트를 사용했습니다. 현재 점수를 확인해 주세요.')
        } catch (err) {
          const message = err instanceof Error ? err.message : '힌트 사용에 실패했습니다.'
          setError(message)
          showToast('error', message)
        }
      },
    })
  }

  const handleStatusChange = useCallback((status: MissionStatusResponse) => setHintsUsed(status.attempt.hints_used), [])
  const handleMissionEnd = useCallback(() => {
    setActiveMissionId(null)
    setHintsUsed(0)
    void fetchMissions()
  }, [fetchMissions])

  return (
    <div className="mission-panel">
      <div className="mission-header">
        <span className="panel-index">RUNBOOK / INCIDENT QUEUE</span>
        <h2>미션 목록</h2>
      </div>
      <div className="mission-list">
        {error && <div className="mission-error">{error}</div>}
        {missions.length === 0 ? <div className="empty-state">미션을 불러오는 중...</div> : missions.map((mission) => (
          <MissionCard key={mission.id} mission={mission} isActive={mission.id === activeMissionId} onStart={handleStartMission} />
        ))}
      </div>
      {activeMissionId && (
        <>
          <MissionStatus token={token} refreshKey={statusRefreshKey} loading={loading} onStatusChange={handleStatusChange} onMissionEnd={handleMissionEnd} onCheck={handleCheckMission} onAbandon={handleAbandonMission} onHint={handleUseHint} />
          <TutorChat token={token} missionId={activeMissionId} hintsUsed={hintsUsed} disabled={loading} />
        </>
      )}
      {confirmation && <ConfirmModal title={confirmation.title} message={confirmation.message} confirmLabel={confirmation.confirmLabel} danger={confirmation.danger} onConfirm={() => void runConfirmedAction()} onCancel={() => setConfirmation(null)} />}
      {toast && <Toast {...toast} onClose={() => setToast(null)} />}
    </div>
  )
}

export default MissionList
