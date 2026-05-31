import React, { useCallback, useEffect, useState } from 'react'
import MissionCard from './MissionCard'
import MissionStatus from './MissionStatus'
import TutorChat from './TutorChat'
import {
  abandonMission,
  checkMission,
  getMissionStatus,
  listMissions,
  MissionStatusResponse,
  startMission,
  useHint,
} from '../../services/api'
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

const MissionList: React.FC<MissionListProps> = ({ token }) => {
  const [missions, setMissions] = useState<Mission[]>([])
  const [activeMissionId, setActiveMissionId] = useState<string | null>(null)
  const [hintsUsed, setHintsUsed] = useState(0)
  const [statusRefreshKey, setStatusRefreshKey] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchMissions = useCallback(async () => {
    try {
      const data = await listMissions(token)
      setMissions(data)

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
      setError('미션 목록을 불러오지 못했습니다')
    }
  }, [token])

  useEffect(() => {
    void fetchMissions()
  }, [fetchMissions])

  const handleStartMission = async (missionId: string) => {
    if (loading || !window.confirm('미션을 시작하시겠습니까?')) return

    setLoading(true)
    setError(null)

    try {
      await startMission(token, missionId)
      setActiveMissionId(missionId)
      setHintsUsed(0)
      setStatusRefreshKey((current) => current + 1)
      await fetchMissions()
      alert('미션을 시작했습니다. 터미널에서 문제를 해결해 보세요.')
    } catch (err) {
      const message = err instanceof Error ? err.message : '미션 시작 실패'
      setError(message)
      alert(message)
    } finally {
      setLoading(false)
    }
  }

  const handleCheckMission = async () => {
    if (loading) return

    setLoading(true)
    setError(null)

    try {
      const result = await checkMission(token)
      alert(result.message)

      if (result.attempt.status === 'completed') {
        setActiveMissionId(null)
        setHintsUsed(0)
        await fetchMissions()
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '미션 확인 실패'
      setError(message)
      alert(message)
    } finally {
      setLoading(false)
    }
  }

  const handleAbandonMission = async () => {
    if (loading || !window.confirm('미션을 포기하시겠습니까? 점수는 0점으로 처리됩니다.')) return

    setLoading(true)
    setError(null)

    try {
      await abandonMission(token)
      setActiveMissionId(null)
      setHintsUsed(0)
      await fetchMissions()
      alert('미션을 포기했습니다.')
    } catch (err) {
      const message = err instanceof Error ? err.message : '미션 포기 실패'
      setError(message)
      alert(message)
    } finally {
      setLoading(false)
    }
  }

  const handleUseHint = async () => {
    if (loading || !window.confirm('힌트를 사용하시겠습니까? 점수가 차감됩니다.')) return

    setLoading(true)
    setError(null)

    try {
      const attempt = await useHint(token)
      setHintsUsed(attempt.hints_used)
      setStatusRefreshKey((current) => current + 1)
      alert('힌트를 사용했습니다. 점수가 차감되었습니다.')
    } catch (err) {
      const message = err instanceof Error ? err.message : '힌트 사용 실패'
      setError(message)
      alert(message)
    } finally {
      setLoading(false)
    }
  }

  const handleStatusChange = useCallback((status: MissionStatusResponse) => {
    setHintsUsed(status.attempt.hints_used)
  }, [])

  const handleMissionEnd = useCallback(() => {
    setActiveMissionId(null)
    setHintsUsed(0)
    void fetchMissions()
  }, [fetchMissions])

  return (
    <div className="mission-panel">
      <div className="mission-header">
        <h2>미션 목록</h2>
      </div>

      <div className="mission-list">
        {error && (
          <div style={{ color: '#f44336', padding: '1rem', textAlign: 'center' }}>
            {error}
          </div>
        )}

        {missions.length === 0 ? (
          <div className="empty-state">미션을 불러오는 중...</div>
        ) : (
          missions.map((mission) => (
            <MissionCard
              key={mission.id}
              mission={mission}
              isActive={mission.id === activeMissionId}
              onStart={handleStartMission}
            />
          ))
        )}
      </div>

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
          <TutorChat token={token} missionId={activeMissionId} hintsUsed={hintsUsed} />
        </>
      )}
    </div>
  )
}

export default MissionList
