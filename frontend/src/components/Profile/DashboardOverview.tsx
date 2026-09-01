import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AchievementsResponse,
  DashboardEnvironmentFilter,
  DashboardStatsResponse,
  getAchievements,
  getDashboardStats,
  getLeaderboard,
  getLearningCurve,
  LeaderboardEntry,
  LearningCurveEntry,
} from '../../services/api'
import { ENVIRONMENT_META, ENVIRONMENT_ORDER } from '../../config/environments'
import {
  DASHBOARD_POLL_HIDDEN_MS,
  DASHBOARD_POLL_INTERVAL_MS,
  MAX_BACKOFF_MS,
} from '../../config/polling'
import { usePolling } from '../../hooks/usePolling'
import { average, curvePolyline, formatDuration, radarPolygon } from '../../utils/dashboard'

interface DashboardOverviewProps {
  token: string
  /**
   * 처음 보여줄 환경 필터 (FE-13). 이후 선택은 이 컴포넌트가 소유한다 —
   * 대시보드 필터는 훈련 환경 탭과 독립적으로 움직여야 환경 간 비교가 된다.
   */
  environment?: DashboardEnvironmentFilter
  /**
   * 단조 증가하는 갱신 키 (FE-15). 미션 완료 직후 App 이 1 올려 한 번 갱신시킨다.
   * 프론트가 점수·MTTR 을 미리 더하지 않고 서버 값을 다시 읽는다.
   */
  refreshKey?: number
}

const SKILL_AXES = [
  ['Troubleshooting', 'troubleshooting'],
  ['Resources', 'resource'],
  ['Network', 'network'],
  ['Operations', 'ops'],
] as const

const FILTERS: DashboardEnvironmentFilter[] = ['all', ...ENVIRONMENT_ORDER]

const filterLabel = (filter: DashboardEnvironmentFilter) =>
  filter === 'all' ? '전체' : ENVIRONMENT_META[filter].label

const emptyAchievements: AchievementsResponse = {
  unlocked: 0,
  total: 0,
  progress: 0,
  items: [],
}

const DashboardOverview: React.FC<DashboardOverviewProps> = ({
  token,
  environment = 'all',
  refreshKey = 0,
}) => {
  const [filter, setFilter] = useState<DashboardEnvironmentFilter>(environment)
  const [stats, setStats] = useState<DashboardStatsResponse | null>(null)
  const [statsFailed, setStatsFailed] = useState(false)
  const [curve, setCurve] = useState<LearningCurveEntry[]>([])
  const [curveFailed, setCurveFailed] = useState(false)
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([])
  const [achievements, setAchievements] = useState<AchievementsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  /**
   * 필터 전환 시 이전 요청을 끊기 위한 controller (FE-13).
   * 중복 호출 자체는 usePolling 이 다음 실행을 직접 예약하는 구조로 막는다 (FE-16) —
   * inFlight 플래그가 필요 없다.
   */
  const controllerRef = useRef<AbortController | null>(null)

  const load = useCallback(
    async (signal: AbortSignal) => {
      try {
        const [statsResult, curveResult, leaderboardResult, achievementsResult] =
          await Promise.allSettled([
            getDashboardStats(token, filter, signal),
            getLearningCurve(token, filter, signal),
            getLeaderboard(token),
            getAchievements(token),
          ])

        if (signal.aborted) return

        // 실패한 지표는 값을 만들어 넣지 않고 실패로 남긴다 (FE-13).
        if (statsResult.status === 'fulfilled') {
          setStats(statsResult.value)
          setStatsFailed(false)
        } else {
          setStats(null)
          setStatsFailed(true)
        }

        if (curveResult.status === 'fulfilled') {
          setCurve(curveResult.value)
          setCurveFailed(false)
        } else {
          setCurve([])
          setCurveFailed(true)
        }

        if (leaderboardResult.status === 'fulfilled') setLeaderboard(leaderboardResult.value)
        if (achievementsResult.status === 'fulfilled') setAchievements(achievementsResult.value)
        else setAchievements((current) => current ?? emptyAchievements)

        const failed = [
          statsResult.status === 'rejected' ? '통계' : null,
          curveResult.status === 'rejected' ? '학습 곡선' : null,
          leaderboardResult.status === 'rejected' ? '리더보드' : null,
          achievementsResult.status === 'rejected' ? '업적' : null,
        ].filter(Boolean)

        setError(failed.length ? `일부 데이터를 불러오지 못했습니다: ${failed.join(', ')}` : null)
      } finally {
        if (!signal.aborted) setIsLoading(false)
      }
    },
    [filter, token],
  )

  /*
   * 필터가 바뀌면 이전 요청을 취소한다 (FE-13).
   * 취소하지 않으면 늦게 도착한 전체 응답이 Docker 화면을 덮는다.
   */
  useEffect(() => {
    setIsLoading(true)
    const controller = new AbortController()
    controllerRef.current = controller

    return () => {
      controller.abort()
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [filter, refreshKey, token])

  const poll = useCallback(async () => {
    const signal = controllerRef.current?.signal
    if (!signal || signal.aborted) return 'continue' as const
    await load(signal)
    return 'continue' as const
  }, [load])

  usePolling(poll, {
    intervalMs: DASHBOARD_POLL_INTERVAL_MS,
    hiddenIntervalMs: DASHBOARD_POLL_HIDDEN_MS,
    maxBackoffMs: MAX_BACKOFF_MS,
    restartKey: `${token}:${filter}:${refreshKey}`,
  })

  const skillValues = useMemo(
    () => (stats ? SKILL_AXES.map(([, key]) => stats.skill_scores[key]) : []),
    [stats],
  )

  /** 환경 역량 3축. 전체 보기에서만 쓴다 (FE-14). */
  const environmentAxes = useMemo(() => {
    const byEnvironment = stats?.environment_stats ?? {}
    return ENVIRONMENT_ORDER.map((id) => ({
      id,
      label: ENVIRONMENT_META[id].label,
      entry: byEnvironment[id] ?? null,
    }))
  }, [stats])

  const isAllView = filter === 'all'
  /*
   * 엔트리가 있는지가 아니라 **competency 가 계산됐는지**를 본다.
   * 백엔드는 environment=all 조회에서 완료가 0건이어도 세 환경 엔트리를 모두 채워
   * 보내고 competency 만 null 로 둔다(analytics_service._environment_stats).
   * 엔트리 유무로 판정하면 신규 사용자에게 중심으로 찌그러진 0축 레이더가 보인다.
   */
  const hasEnvironmentBreakdown =
    isAllView && environmentAxes.some((axis) => axis.entry?.competency != null)

  const radarValues = isAllView
    ? environmentAxes.map((axis) => axis.entry?.competency ?? 0)
    : skillValues
  const radarRings = [25, 50, 75, 100]
  const radarAxisCount = radarValues.length

  const completed = stats?.missions_completed ?? 0
  const averageScore = stats ? average(stats.total_score, completed) : null
  /*
   * 평균 MTTR. 필터를 건 조회에서는 백엔드가 environment_stats 를 채우지 않으므로
   * total_time_spent / missions_completed 로 구한다 — 백엔드 average_mttr 과
   * 같은 정의다 (`sum(_completion_seconds) / count`).
   */
  const averageMttr = stats ? average(stats.total_time_spent, completed) : null

  const noData = (label: string) => (
    <span className="metric-empty" aria-label={`${label} 데이터 없음`}>
      데이터 없음
    </span>
  )

  const radarLabel = isAllView
    ? `환경 역량 레이더. ${environmentAxes
        .map((axis) => `${axis.label} ${axis.entry?.competency ?? '데이터 없음'}`)
        .join(', ')}`
    : `${filterLabel(filter)} 스킬 레이더. ${SKILL_AXES.map(
        ([label, key]) => `${label} ${stats?.skill_scores[key] ?? 0}`,
      ).join(', ')}`

  if (isLoading && !stats && !statsFailed) {
    return <div className="dashboard-empty">학습 대시보드를 불러오는 중...</div>
  }

  return (
    <div className="learning-dashboard">
      {error && (
        <div className="dashboard-warning" role="status">
          {error}
        </div>
      )}

      <div className="dashboard-filter" role="group" aria-label="환경 필터">
        {FILTERS.map((option) => (
          <button
            key={option}
            type="button"
            className={option === filter ? 'active' : ''}
            aria-pressed={option === filter}
            onClick={() => setFilter(option)}
          >
            {filterLabel(option)}
          </button>
        ))}
      </div>

      <section className="dashboard-tier-card">
        {statsFailed ? (
          <div className="dashboard-empty" role="alert">
            통계를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
          </div>
        ) : (
          <>
            <div>
              <span className="dashboard-label">
                CURRENT TIER / {filterLabel(filter).toUpperCase()}
              </span>
              <h3 style={{ color: stats?.current_tier.color }}>{stats?.current_tier.name}</h3>
              <p>
                {stats?.total_score ?? 0}점 / 완료 {completed}건
              </p>
            </div>
            <div className="tier-progress-wrap">
              <span>
                {stats?.current_tier.next_tier
                  ? `다음 티어: ${stats.current_tier.next_tier}`
                  : '최고 티어에 도달했습니다'}
              </span>
              <div className="tier-progress">
                <i style={{ width: `${stats?.current_tier.progress ?? 0}%` }} />
              </div>
            </div>
          </>
        )}
      </section>

      {/* 핵심 지표 (FE-13). 완료 0건과 조회 실패를 다르게 표시한다. */}
      <section className="dashboard-metrics" aria-label={`${filterLabel(filter)} 핵심 지표`}>
        <article>
          <span>완료 미션</span>
          {statsFailed ? noData('완료 미션') : <strong>{completed}건</strong>}
        </article>
        <article>
          <span>평균 점수</span>
          {statsFailed || averageScore === null ? (
            noData('평균 점수')
          ) : (
            <strong>{averageScore}점</strong>
          )}
        </article>
        <article>
          <span>평균 MTTR</span>
          {statsFailed || averageMttr === null ? (
            noData('평균 MTTR')
          ) : (
            <strong>{formatDuration(averageMttr)}</strong>
          )}
        </article>
        <article>
          <span>총 힌트</span>
          {statsFailed ? noData('총 힌트') : <strong>{stats?.hints_used ?? 0}회</strong>}
        </article>
        <article>
          <span>누적 학습 시간</span>
          {statsFailed ? (
            noData('누적 학습 시간')
          ) : (
            <strong>{formatDuration(stats?.total_time_spent ?? 0)}</strong>
          )}
        </article>
      </section>

      <div className="dashboard-grid">
        <section className="dashboard-card skill-card">
          <span className="dashboard-label">
            {isAllView
              ? 'ENVIRONMENT COMPETENCY'
              : `SKILL RADAR / ${filterLabel(filter).toUpperCase()}`}
          </span>
          {isAllView && !hasEnvironmentBreakdown ? (
            <p className="dashboard-empty">
              완료한 미션이 없어 환경 역량을 계산할 수 없습니다. 미션을 하나 완료해 보세요.
            </p>
          ) : (
            <>
              <svg className="skill-radar" viewBox="0 0 200 200" role="img" aria-label={radarLabel}>
                {radarRings.map((ring) => (
                  <polygon key={ring} points={radarPolygon(new Array(radarAxisCount).fill(ring))} />
                ))}
                <polygon className="skill-radar-value" points={radarPolygon(radarValues)} />
              </svg>
              {/* SVG 를 못 읽는 환경에서도 수치를 읽을 수 있게 텍스트로 함께 낸다. */}
              <div className="skill-list">
                {isAllView
                  ? environmentAxes.map((axis) => (
                      <span key={axis.id}>
                        {axis.label}
                        <strong>{axis.entry?.competency ?? '—'}</strong>
                      </span>
                    ))
                  : SKILL_AXES.map(([label, key]) => (
                      <span key={key}>
                        {label}
                        <strong>{stats?.skill_scores[key] ?? 0}</strong>
                      </span>
                    ))}
              </div>
            </>
          )}
        </section>

        <section className="dashboard-card">
          <span className="dashboard-label">
            LEARNING CURVE / {filterLabel(filter).toUpperCase()}
          </span>
          {curveFailed ? (
            <p className="dashboard-empty" role="alert">
              학습 곡선을 불러오지 못했습니다.
            </p>
          ) : curve.length ? (
            <>
              <svg
                className="learning-curve"
                viewBox="0 0 300 110"
                preserveAspectRatio="none"
                role="img"
                aria-label={`완료 시간 추이 ${curve.length}건. ${curve
                  .slice(-4)
                  .map(
                    (entry) =>
                      `${entry.mission_name} ${formatDuration(entry.completion_time)} ${entry.score}점`,
                  )
                  .join(', ')}`}
              >
                <polyline points={curvePolyline(curve)} />
              </svg>
              <div className="curve-history">
                {curve.slice(-4).map((entry) => (
                  <span key={entry.attempt_id}>
                    {entry.mission_name}
                    <strong>
                      {formatDuration(entry.completion_time)} · {entry.score}점
                    </strong>
                  </span>
                ))}
              </div>
            </>
          ) : (
            <p className="dashboard-empty">
              {filterLabel(filter)} 환경에서 완료한 미션이 없습니다. 미션을 완료하면 곡선이
              생깁니다.
            </p>
          )}
        </section>

        <section className="dashboard-card">
          <span className="dashboard-label">LEADERBOARD / TOP 10</span>
          {leaderboard.length ? (
            <ol className="leaderboard-list">
              {leaderboard.map((entry) => (
                <li className={entry.is_current_user ? 'current-user' : ''} key={entry.user_id}>
                  <b>#{entry.rank}</b>
                  <span>{entry.username}</span>
                  <strong>{entry.total_score}</strong>
                </li>
              ))}
            </ol>
          ) : (
            <p className="dashboard-empty">리더보드 데이터가 아직 없습니다.</p>
          )}
        </section>

        <section className="dashboard-card">
          <span className="dashboard-label">
            ACHIEVEMENTS / {achievements?.unlocked ?? 0} OF {achievements?.total ?? 0}
          </span>
          {achievements?.items.length ? (
            <div className="achievement-list">
              {achievements.items.map((achievement) => (
                <article className={achievement.unlocked ? 'unlocked' : ''} key={achievement.id}>
                  <strong>{achievement.name}</strong>
                  <span>{achievement.description}</span>
                </article>
              ))}
            </div>
          ) : (
            <p className="dashboard-empty">업적 데이터가 아직 없습니다.</p>
          )}
        </section>
      </div>
    </div>
  )
}

export default DashboardOverview
