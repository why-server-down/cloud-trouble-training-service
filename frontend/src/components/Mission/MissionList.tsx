import React, { useEffect, useState } from 'react'
import MissionCard from './MissionCard'
import MissionStatus from './MissionStatus'
import { listMissions, startMission, checkMission, abandonMission, useHint } from '../../services/api'
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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchMissions = async () => {
    try {
      const data = await listMissions(token)
      setMissions(data)

      // 진행 중인 미션이 있는지 확인
      try {
        const statusResponse = await fetch('http://localhost:8000/api/missions/status', {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })

        if (statusResponse.ok) {
          const statusData = await statusResponse.json()
          // 진행 중인 미션이 있으면 활성화
          setActiveMissionId(statusData.attempt.mission_id)
        } else {
          // 진행 중인 미션이 없으면 초기화
          setActiveMissionId(null)
        }
      } catch (err) {
        // 진행 중인 미션이 없는 경우 (404 등)
        setActiveMissionId(null)
      }
    } catch (err) {
      console.error('미션 목록 조회 실패:', err)
      setError('미션 목록을 불러올 수 없습니다')
    }
  }

  useEffect(() => {
    fetchMissions()
  }, [token])

  const handleStartMission = async (missionId: string) => {
    if (loading) return

    const confirmed = window.confirm('이 미션을 시작하시겠습니까?')
    if (!confirmed) return

    setLoading(true)
    setError(null)

    try {
      await startMission(token, missionId)
      setActiveMissionId(missionId)
      await fetchMissions()
      alert('미션이 시작되었습니다! 터미널에서 문제를 해결하세요.')
    } catch (err: any) {
      setError(err.message || '미션 시작 실패')
      alert(err.message || '미션 시작에 실패했습니다')
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
        await fetchMissions()
      }
    } catch (err: any) {
      setError(err.message || '미션 확인 실패')
      alert(err.message || '미션 확인에 실패했습니다')
    } finally {
      setLoading(false)
    }
  }

  const handleAbandonMission = async () => {
    if (loading) return

    const confirmed = window.confirm('정말로 미션을 포기하시겠습니까? (0점 처리)')
    if (!confirmed) return

    setLoading(true)
    setError(null)

    try {
      await abandonMission(token)
      setActiveMissionId(null)
      await fetchMissions()
      alert('미션을 포기했습니다')
    } catch (err: any) {
      setError(err.message || '미션 포기 실패')
      alert(err.message || '미션 포기에 실패했습니다')
    } finally {
      setLoading(false)
    }
  }

  const handleUseHint = async () => {
    if (loading) return

    const confirmed = window.confirm('힌트를 사용하시겠습니까? (점수 감점)')
    if (!confirmed) return

    setLoading(true)
    setError(null)

    try {
      await useHint(token)
      alert('힌트가 사용되었습니다. 점수가 감점되었습니다.')
    } catch (err: any) {
      setError(err.message || '힌트 사용 실패')
      alert(err.message || '힌트 사용에 실패했습니다')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mission-panel">
      <div className="mission-header">
        <h2>🎯 미션 목록</h2>
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
        <MissionStatus
          token={token}
          onRefresh={fetchMissions}
          onCheck={handleCheckMission}
          onAbandon={handleAbandonMission}
          onHint={handleUseHint}
        />
      )}
    </div>
  )
}

export default MissionList
