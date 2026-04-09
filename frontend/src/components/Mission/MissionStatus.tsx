import React, { useEffect, useState } from 'react'

interface MissionStatusProps {
  token: string
  onRefresh: () => void
  onCheck: () => void
  onAbandon: () => void
  onHint: () => void
}

interface StatusData {
  elapsed_seconds: number
  remaining_seconds: number
  current_score: number
  hints_used: number
}

const MissionStatus: React.FC<MissionStatusProps> = ({
  token,
  onRefresh,
  onCheck,
  onAbandon,
  onHint,
}) => {
  const [status, setStatus] = useState<StatusData | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/missions/status', {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })

        if (response.ok) {
          const data = await response.json()
          setStatus({
            elapsed_seconds: data.elapsed_seconds,
            remaining_seconds: data.remaining_seconds,
            current_score: data.current_score,
            hints_used: data.attempt.hints_used,
          })
        }
      } catch (error) {
        console.error('상태 조회 실패:', error)
      }
    }

    fetchStatus()
    const interval = setInterval(fetchStatus, 1000)

    return () => clearInterval(interval)
  }, [token])

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
        <div className="empty-state">미션을 시작하세요</div>
      </div>
    )
  }

  return (
    <div className="mission-status-panel">
      <div className="status-header">📊 미션 진행 상황</div>

      <div className="status-item">
        <span>남은 시간</span>
        <span className={`status-value ${getTimeClass(status.remaining_seconds)}`}>
          {formatTime(status.remaining_seconds)}
        </span>
      </div>

      <div className="status-item">
        <span>현재 점수</span>
        <span className="status-value">{status.current_score}점</span>
      </div>

      <div className="status-item">
        <span>사용한 힌트</span>
        <span className="status-value">{status.hints_used}개</span>
      </div>

      <div className="status-actions">
        <button
          className="btn btn-success"
          onClick={onCheck}
          disabled={loading}
        >
          ✅ 완료 확인
        </button>
        <button
          className="btn btn-warning"
          onClick={onHint}
          disabled={loading}
        >
          💡 힌트 사용
        </button>
        <button
          className="btn btn-danger"
          onClick={onAbandon}
          disabled={loading}
        >
          ❌ 미션 포기
        </button>
      </div>
    </div>
  )
}

export default MissionStatus
