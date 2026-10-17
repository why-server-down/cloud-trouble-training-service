import React, { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getMissionStatus, MissionStatusResponse } from '../../services/api'
import { usePolling } from '../../hooks/usePolling'
import {
  MAX_BACKOFF_MS,
  MISSION_POLL_HIDDEN_MS,
  MISSION_POLL_INTERVAL_MS,
} from '../../config/polling'
import { HINT_LEVELS, hintLevelOf, MAX_HINT_LEVEL } from './missionCopy'

/** 진행 중인 액션. 요청 중 중복 클릭을 막고 어떤 액션이 도는지 문구로 알린다 (FE-16). */
export type MissionAction = 'check' | 'hint' | 'abandon'

interface MissionStatusProps {
  token: string
  refreshKey: number
  /** 진행 중인 액션. null 이면 유휴 상태다. */
  pendingAction: MissionAction | null
  /** 활성 미션의 힌트 감점. status 응답에는 없어서 미션 목록 값을 받는다. */
  hintPenalty?: number | null
  /** 인시던트 바에 보일 미션 이름과 환경 (FE-26). */
  missionTitle?: string
  environmentLabel?: string
  onStatusChange: (status: MissionStatusResponse) => void
  /**
   * 시도가 끝났다. 서버가 끝난 상태(완료·시간 초과·포기)를 알려 주면 그 값을 넘긴다 —
   * 디브리프가 결과와 점수를 그리는 근거다. 시도가 사라져 404 면 null 이다.
   */
  onMissionEnd: (status: MissionStatusResponse | null, lastRemainingSeconds: number | null) => void
  /** 완료 확인이 실패한 이유 (FE-27). 인시던트 바 안에 남긴다. */
  feedback?: string | null
  onCheck: () => void
  onAbandon: () => void
  onHint: () => void
}

const ACTION_LABELS: Record<MissionAction, string> = {
  check: '확인 중...',
  hint: '힌트 요청 중...',
  abandon: '포기 처리 중...',
}

const formatClock = (totalSeconds: number) =>
  `${Math.floor(totalSeconds / 60)}:${(totalSeconds % 60).toString().padStart(2, '0')}`

interface MissionStatusViewProps {
  /** 영역 이름. 스크린리더가 읽는다. */
  title: string
  /** 인시던트 바에 크게 보일 미션 이름. 없으면 title 을 쓴다 (FE-26). */
  missionTitle?: string
  environmentLabel?: string
  remainingSeconds: number
  score: number
  hintsUsed: number
  /** 힌트 1회 감점. 알 수 있을 때만 버튼에 비용을 적는다 (설계 문서 5.1). */
  hintPenalty?: number | null
  pendingAction: MissionAction | null
  busy: boolean
  abandonLabel: string
  /** 마지막 조회가 실패해 값이 낡았는가. */
  isStale?: boolean
  /**
   * 완료 확인이 아직 통과하지 못한 이유 (FE-27). 3.5초 토스트로 사라지면 무엇이 남았는지
   * 다시 확인할 수 없어 바 안에 둔다. 다음 확인이나 미션 종료 때 지워진다.
   */
  feedback?: string | null
  onCheck: () => void
  onHint: () => void
  onAbandon: () => void
}

/**
 * 진행 상황 표시. 정적 미션과 AI 시나리오가 같은 모양을 쓴다 —
 * 두 벌로 적어 두면 한쪽만 고치는 사고가 난다.
 */
export const MissionStatusView: React.FC<MissionStatusViewProps> = ({
  title,
  missionTitle,
  environmentLabel,
  remainingSeconds,
  score,
  hintsUsed,
  hintPenalty,
  pendingAction,
  busy,
  abandonLabel,
  isStale = false,
  feedback = null,
  onCheck,
  onHint,
  onAbandon,
}) => {
  const timeState = remainingSeconds < 60 ? 'danger' : remainingSeconds < 300 ? 'warning' : ''
  /*
   * 버튼은 '힌트 사용'이 아니라 올라갈 단계를 말한다. 힌트는 튜터 답의 구체성 단계라서,
   * 3단계를 넘게 사도 더 받는 것이 없다 — 그때는 잠근다.
   */
  const hintLevel = hintLevelOf(hintsUsed)
  const hintsExhausted = hintLevel >= MAX_HINT_LEVEL
  const nextHint = hintsExhausted ? null : HINT_LEVELS[hintLevel + 1]
  const hintLabel = hintsExhausted
    ? '힌트 모두 사용'
    : `힌트 ${hintLevel + 1}단계${hintPenalty ? ` −${hintPenalty}점` : ''}`

  return (
    <section className="mission-status-panel incident-bar" data-tour="mission-progress" aria-label={title}>
      <div className="incident-identity">
        <span className="incident-live">
          <span className="ui-live-dot" aria-hidden="true" />
          진행 중{environmentLabel ? ` · ${environmentLabel}` : ''}
        </span>
        <h3 className="incident-title status-header">{missionTitle ?? title}</h3>
      </div>
      {isStale && (
        <p className="status-stale-note" role="status" aria-live="polite">
          상태 조회에 실패했습니다. 연결이 돌아오면 자동으로 다시 시도합니다.
        </p>
      )}
      <div className="status-metrics">
        <div className="status-timer">
          <span className="status-label">
            <span className="status-label-text">남은 시간</span>
            {/* 색만으로 알리지 않는다. 경계를 넘을 때 글자로도 읽히게 영역을 미리 둔다. */}
            <span className={`status-time-flag ${timeState}`} role="status">
              {timeState === 'danger' ? '1분 미만' : timeState === 'warning' ? '5분 미만' : ''}
            </span>
          </span>
          <span className={`status-value status-timer-value ${timeState}`}>{formatClock(remainingSeconds)}</span>
        </div>
        <div className="status-item">
          <span className="status-label">현재 점수</span>
          <span className="status-value">{score}점</span>
        </div>
        <div className="status-item">
          <span className="status-label">힌트 단계</span>
          <span className="status-value">
            {hintLevel}/{MAX_HINT_LEVEL}
          </span>
        </div>
      </div>
      <div className="status-actions">
        <button className="ui-button primary" type="button" onClick={onCheck} disabled={busy}>
          {pendingAction === 'check' ? ACTION_LABELS.check : '완료 확인'}
        </button>
        <button
          className="ui-button"
          type="button"
          onClick={onHint}
          disabled={busy || hintsExhausted}
          title={nextHint ? `${nextHint.name}: ${nextHint.detail}` : '튜터가 가장 구체적인 단계로 답하고 있습니다.'}
        >
          {pendingAction === 'hint' ? ACTION_LABELS.hint : hintLabel}
        </button>
        <span className="status-actions-divider" aria-hidden="true" />
        <button className="ui-button danger" type="button" onClick={onAbandon} disabled={busy}>
          {pendingAction === 'abandon' ? ACTION_LABELS.abandon : abandonLabel}
        </button>
      </div>
      {feedback && (
        <p className="status-feedback" role="status" aria-live="polite">
          <strong>아직 해결되지 않았습니다.</strong> {feedback}
        </p>
      )}
    </section>
  )
}

const MissionStatus: React.FC<MissionStatusProps> = ({
  token,
  refreshKey,
  pendingAction,
  hintPenalty,
  missionTitle,
  environmentLabel,
  onStatusChange,
  onMissionEnd,
  feedback,
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
  /*
   * 폴링 콜백이 읽을 마지막 남은 시간. 서버는 시간이 다 된 시도를 실패로 정리한 뒤 404 를
   * 돌려준다 — 끝난 이유를 응답으로 알 수 없어, 거의 0 이었는지를 근거로 넘긴다 (FE-27).
   */
  const remainingRef = useRef<number | null>(null)
  remainingRef.current = remaining
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
        onMissionEndRef.current(data, data.remaining_seconds)
        return 'stop' as const
      }
      return 'continue' as const
    } catch (error) {
      // 404 는 활성 attempt 가 사라진 것이다. 오류가 아니라 종료 신호다.
      if (error instanceof ApiError && error.status === 404) {
        onMissionEndRef.current(null, remainingRef.current)
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
      <div className="mission-status-panel incident-bar is-loading" data-tour="mission-progress">
        <div className="empty-state">미션 상태를 불러오는 중...</div>
      </div>
    )
  }

  return (
    <MissionStatusView
      title="미션 진행 상황"
      missionTitle={missionTitle}
      environmentLabel={environmentLabel}
      remainingSeconds={remaining ?? status.remaining_seconds}
      score={status.current_score}
      hintsUsed={status.attempt.hints_used}
      hintPenalty={hintPenalty}
      pendingAction={pendingAction}
      busy={pendingAction !== null}
      abandonLabel="미션 포기"
      isStale={isStale}
      feedback={feedback}
      onCheck={onCheck}
      onHint={onHint}
      onAbandon={onAbandon}
    />
  )
}

export default MissionStatus
