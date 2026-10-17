import React, { useEffect, useState } from 'react'
import { DashboardStatsResponse, getDashboardStats } from '../../services/api'
import './Profile.css'

interface ProgressSummaryProps {
  token: string
  /** 미션 완료 때 App 이 올리는 키 (FE-15). 바뀌면 서버 값을 다시 읽는다. */
  refreshKey?: number
  onOpenProfile: () => void
}

/**
 * 미션 전 화면의 학습 현황 요약 (FE-29).
 *
 * 전체 대시보드는 프로필 시트에만 둔다. 여기서는 현재 티어, 완료 수, 다음 티어까지만 보여 준다 —
 * 미션 전 화면의 초점은 미션 목록이다. 티어와 진행률은 서버 값이고 프론트에서 계산하지 않는다.
 */
const ProgressSummary: React.FC<ProgressSummaryProps> = ({ token, refreshKey = 0, onOpenProfile }) => {
  const [stats, setStats] = useState<DashboardStatsResponse | null>(null)
  const [failed, setFailed] = useState(false)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setFailed(false)
    getDashboardStats(token, 'all', controller.signal)
      .then(setStats)
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => controller.abort()
  }, [token, refreshKey, retry])

  const tier = stats?.current_tier

  return (
    /* 영역 이름(학습 현황)은 이 요약을 담는 작업 화면 영역이 붙인다. 같은 이름의 영역을 겹치지 않는다. */
    <div className="progress-summary" data-tour="progress-summary">
      <div className="progress-summary-header">
        <h2 className="panel-label">학습 현황</h2>
        <button className="ui-button plain small" type="button" onClick={onOpenProfile}>
          프로필에서 자세히
        </button>
      </div>
      {failed && !stats ? (
        <div className="progress-summary-body progress-summary-error" role="alert">
          <p className="progress-summary-note">학습 현황을 불러오지 못했습니다.</p>
          <button className="ui-button small" type="button" onClick={() => setRetry((count) => count + 1)}>
            다시 시도
          </button>
        </div>
      ) : !stats || !tier ? (
        <p className="progress-summary-body progress-summary-note" role="status">
          불러오는 중...
        </p>
      ) : (
        <div className="progress-summary-body">
          <p className="progress-summary-line">
            {/* 티어 색은 쓰지 않는다. 강조색은 1차 동작과 진행 중 표시에만 쓴다 (FE-29). */}
            <span className="ui-chip">
              <span className="sr-only">현재 티어 </span>
              {tier.name}
            </span>
            {/* 총점은 헤더가 늘 보여 주므로 반복하지 않는다. */}
            <span>
              완료 <span className="progress-summary-number">{stats.missions_completed}</span>건
            </span>
          </p>
          <div className="progress-summary-next">
            <span>{tier.next_tier ? `${tier.next_tier}까지` : '최고 티어'}</span>
            <div
              className="tier-progress"
              role="progressbar"
              aria-label="다음 티어까지 진행률"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={tier.progress}
            >
              <i style={{ width: `${tier.progress}%` }} />
            </div>
            {/* 서버 진행률은 소수일 수 있다. 막대는 그대로, 글자는 정수로 보여 준다. */}
            <span className="progress-summary-number">{Math.round(tier.progress)}%</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default ProgressSummary
