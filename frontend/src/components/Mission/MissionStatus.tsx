import React, { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getMissionStatus, MissionStatusResponse } from '../../services/api'
import { usePolling } from '../../hooks/usePolling'
import {
  MAX_BACKOFF_MS,
  MISSION_POLL_HIDDEN_MS,
  MISSION_POLL_INTERVAL_MS,
} from '../../config/polling'

/** 진행 중인 액션. 요청 중 중복 클릭을 막고 어떤 액션이 도는지 문구로 알린다 (FE-16). */
export type MissionAction = 'check' | 'hint' | 'abandon'

interface MissionStatusProps {
  token: string
  refreshKey: number
  /** 진행 중인 액션. null 이면 유휴 상태다. */
  pendingAction: MissionAction | null
  onStatusChange: (status: MissionStatusResponse) => void
  onMissionEnd: () => void
  onCheck: () => void
  onAbandon: () => void
  onHint: () => void
}

const ACTION_LABELS: Record<MissionAction, string> = {
  check: '확인 중...',
  hint: '힌트 요청 중...',
  abandon: '포기 처리 중...',
}

const MissionStatus: React.FC<MissionStatusProps> = ({
  token,
  refreshKey,
  pendingAction,
  onStatusChange,
  onMissionEnd,
  onCheck,
  onAbandon,
  onHint,
}) => {
  const [status, setStatus] = useState<MissionStatusResponse | null>(null)
  /**
   * 화면에 보여줄 남은 시간 (FE-16).
   *
   * 서버 폴링을 5초로 늦추면서 이 값을 그대로 쓰면 카운트다운이 5초씩 튄다.
   * 서버 값이 도착할 때 이 값을 맞추고, 그 사이에는 로컬에서 1초씩 줄인다 —
   * 표시는 매끄럽게, 요청은 드물게.
   */
  const [remaining, setRemaining] = useState<number | null>(null)
  const [isStale, setIsStale] = useState(false)

  // 최신 콜백만 들고 있는다. 폴링 재시작 없이 반영하기 위한 것이다.
  const onStatusChangeRef = useRef(onStatusChange)
  onStatusChangeRef.current = onStatusChange
  const onMissionEndRef = useRef(onMissionEnd)
  onMissionEndRef.current = onMissionEnd

  const poll = useCallback(async () => {
    try {
      const data = await getMissionStatus(token)
      setStatus(data)
      setRemaining(data.remaining_seconds)
      setIsStale(false)
      onStatusChangeRef.current(data)

      // 완료·실패·포기에서 즉시 멈춘다. 끝난 미션을 계속 물을 이유가 없다.
      if (data.attempt.status !== 'in_progress') {
        onMissionEndRef.current()
        return 'stop' as const
      }
      return 'continue' as const
    } catch (error) {
      // 404 는 활성 attempt 가 사라진 것이다. 오류가 아니라 종료 신호다.
      if (error instanceof ApiError && error.status === 404) {
        onMissionEndRef.current()
        return 'stop' as const
      }

      // 그 밖의 실패는 backoff 대상이다. 화면에는 값이 낡았음을 알린다.
      setIsStale(true)
      throw error
    }
  }, [token])

  /*
   * refreshKey 가 바뀌면 폴링을 다시 시작해 즉시 한 번 조회한다
   * (힌트 사용 직후처럼 서버 값이 방금 바뀐 시점).
   */
  usePolling(poll, {
    intervalMs: MISSION_POLL_INTERVAL_MS,
    hiddenIntervalMs: MISSION_POLL_HIDDEN_MS,
    maxBackoffMs: MAX_BACKOFF_MS,
    restartKey: `${token}:${refreshKey}`,
  })

  useEffect(() => {
    setStatus(null)
    setRemaining(null)
    setIsStale(false)
  }, [token])

  /**
   * 표시용 1초 tick. 서버 값이 도착하면 위에서 다시 맞춰진다.
   * `remaining` 자체를 의존성에 두면 매초 타이머를 새로 만들므로 있는지만 본다.
   */
  const hasRemaining = remaining !== null
  useEffect(() => {
    if (!hasRemaining) return undefined

    const tick = window.setInterval(() => {
      setRemaining((current) => (current === null ? null : Math.max(0, current - 1)))
    }, 1000)

    return () => window.clearInterval(tick)
  }, [hasRemaining])

  if (!status) {
    return (
      <div className="mission-status-panel" data-tour="mission-progress">
        <div className="empty-state">미션 상태를 불러오는 중...</div>
      </div>
    )
  }

  const shown = remaining ?? status.remaining_seconds
  const minutes = Math.floor(shown / 60)
  const seconds = shown % 60
  const timeClass = shown < 60 ? 'danger' : shown < 300 ? 'warning' : ''
  const isBusy = pendingAction !== null

  return (
    <div className="mission-status-panel" data-tour="mission-progress">
      <div className="status-header">미션 진행 상황</div>
      {isStale && (
        <p className="status-stale-note" role="status" aria-live="polite">
          상태 조회에 실패했습니다. 연결이 돌아오면 자동으로 다시 시도합니다.
        </p>
      )}
      <div className="status-item">
        <span>남은 시간</span>
        <span className={`status-value ${timeClass}`}>
          {minutes}:{seconds.toString().padStart(2, '0')}
        </span>
      </div>
      <div className="status-item">
        <span>현재 점수</span>
        <span className="status-value">{status.current_score}점</span>
      </div>
      <div className="status-item">
        <span>사용한 힌트</span>
        <span className="status-value">{status.attempt.hints_used}개</span>
      </div>
      <div className="status-actions">
        <button className="btn btn-success" type="button" onClick={onCheck} disabled={isBusy}>
          {pendingAction === 'check' ? ACTION_LABELS.check : '완료 확인'}
        </button>
        <button className="btn btn-warning" type="button" onClick={onHint} disabled={isBusy}>
          {pendingAction === 'hint' ? ACTION_LABELS.hint : '힌트 사용'}
        </button>
        <button className="btn btn-danger" type="button" onClick={onAbandon} disabled={isBusy}>
          {pendingAction === 'abandon' ? ACTION_LABELS.abandon : '미션 포기'}
        </button>
      </div>
    </div>
  )
}

export default MissionStatus
