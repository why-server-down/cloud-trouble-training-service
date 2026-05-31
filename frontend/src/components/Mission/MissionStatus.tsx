import React, { useEffect, useState } from 'react'
import { getMissionStatus, MissionStatusResponse } from '../../services/api'

interface MissionStatusProps {
  token: string
  refreshKey: number
  loading: boolean
  onStatusChange: (status: MissionStatusResponse) => void
  onMissionEnd: () => void
  onCheck: () => void
  onAbandon: () => void
  onHint: () => void
}

interface StatusData {
  remainingSeconds: number
  currentScore: number
  hintsUsed: number
}

const MissionStatus: React.FC<MissionStatusProps> = ({
  token,
  refreshKey,
  loading,
  onStatusChange,
  onMissionEnd,
  onCheck,
  onAbandon,
  onHint,
}) => {
  const [status, setStatus] = useState<StatusData | null>(null)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await getMissionStatus(token)
        setStatus({
          remainingSeconds: data.remaining_seconds,
          currentScore: data.current_score,
          hintsUsed: data.attempt.hints_used,
        })
        onStatusChange(data)

        if (data.attempt.status !== 'in_progress') {
          onMissionEnd()
        }
      } catch (error) {
        console.error('미션 상태 조회 실패:', error)
      }
    }

    void fetchStatus()
    const interval = setInterval(fetchStatus, 1000)

    return () => clearInterval(interval)
  }, [token, refreshKey, onStatusChange, onMissionEnd])

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const getTimeClass = (remaining: number) => {
    if (remaining < 60) return 'danger'
    if (remaining < 300) return 'warning'
    return ''
  }

  if (!status) {
    return (
      <div className="mission-status-panel">
        <div className="empty-state">미션 상태를 불러오는 중...</div>
      </div>
    )
  }

  return (
    <div className="mission-status-panel">
      <div className="status-header">미션 진행 상황</div>

      <div className="status-item">
        <span>남은 시간</span>
        <span className={`status-value ${getTimeClass(status.remainingSeconds)}`}>
          {formatTime(status.remainingSeconds)}
        </span>
      </div>

      <div className="status-item">
        <span>현재 점수</span>
        <span className="status-value">{status.currentScore}점</span>
      </div>

      <div className="status-item">
        <span>사용한 힌트</span>
        <span className="status-value">{status.hintsUsed}개</span>
      </div>

      <div className="status-actions">
        <button className="btn btn-success" onClick={onCheck} disabled={loading}>
          완료 확인
        </button>
        <button className="btn btn-warning" onClick={onHint} disabled={loading}>
          힌트 사용
        </button>
        <button className="btn btn-danger" onClick={onAbandon} disabled={loading}>
          미션 포기
        </button>
      </div>
    </div>
  )
}

export default MissionStatus
