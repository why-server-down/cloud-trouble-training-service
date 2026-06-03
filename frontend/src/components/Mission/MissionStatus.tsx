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

const MissionStatus: React.FC<MissionStatusProps> = ({
  token, refreshKey, loading, onStatusChange, onMissionEnd, onCheck, onAbandon, onHint,
}) => {
  const [status, setStatus] = useState<MissionStatusResponse | null>(null)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await getMissionStatus(token)
        setStatus(data)
        onStatusChange(data)
        if (data.attempt.status !== 'in_progress') onMissionEnd()
      } catch (error) {
        console.error('미션 상태 조회 실패:', error)
      }
    }

    void fetchStatus()
    const interval = window.setInterval(fetchStatus, 1000)
    return () => window.clearInterval(interval)
  }, [token, refreshKey, onStatusChange, onMissionEnd])

  if (!status) return <div className="mission-status-panel"><div className="empty-state">미션 상태를 불러오는 중...</div></div>

  const minutes = Math.floor(status.remaining_seconds / 60)
  const seconds = status.remaining_seconds % 60
  const timeClass = status.remaining_seconds < 60 ? 'danger' : status.remaining_seconds < 300 ? 'warning' : ''

  return (
    <div className="mission-status-panel">
      <div className="status-header">미션 진행 상황</div>
      <div className="status-item"><span>남은 시간</span><span className={`status-value ${timeClass}`}>{minutes}:{seconds.toString().padStart(2, '0')}</span></div>
      <div className="status-item"><span>현재 점수</span><span className="status-value">{status.current_score}점</span></div>
      <div className="status-item"><span>사용한 힌트</span><span className="status-value">{status.attempt.hints_used}개</span></div>
      <div className="status-actions">
        <button className="btn btn-success" type="button" onClick={onCheck} disabled={loading}>완료 확인</button>
        <button className="btn btn-warning" type="button" onClick={onHint} disabled={loading}>힌트 사용</button>
        <button className="btn btn-danger" type="button" onClick={onAbandon} disabled={loading}>미션 포기</button>
      </div>
    </div>
  )
}

export default MissionStatus
