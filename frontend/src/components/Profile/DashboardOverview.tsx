import React, { useEffect, useMemo, useState } from 'react'
import {
  AchievementsResponse,
  DashboardStatsResponse,
  getAchievements,
  getDashboardStats,
  getLeaderboard,
  getLearningCurve,
  getProfile,
  LeaderboardEntry,
  LearningCurveEntry,
} from '../../services/api'

interface DashboardOverviewProps {
  token: string
}

const skillLabels = [
  ['Troubleshooting', 'troubleshooting'],
  ['Resources', 'resource'],
  ['Network', 'network'],
  ['Operations', 'ops'],
] as const

const emptyStats: DashboardStatsResponse = {
  username: '',
  total_score: 0,
  missions_completed: 0,
  total_time_spent: 0,
  hints_used: 0,
  current_tier: {
    name: 'Bronze',
    min_score: 0,
    max_score: 200,
    color: '#cd7f32',
    progress: 0,
    next_tier: 'Silver',
  },
  skill_scores: {
    troubleshooting: 0,
    resource: 0,
    network: 0,
    ops: 0,
  },
}

const emptyAchievements: AchievementsResponse = {
  unlocked: 0,
  total: 0,
  progress: 0,
  items: [],
}

const getFallbackStats = async (token: string): Promise<DashboardStatsResponse> => {
  try {
    const profile = await getProfile(token)
    return {
      ...emptyStats,
      username: profile.username,
      total_score: profile.total_score,
      missions_completed: profile.missions_completed,
    }
  } catch {
    return emptyStats
  }
}

const formatDuration = (seconds: number) => {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${seconds % 60}s`
}

const point = (index: number, value: number, radius = 72) => {
  const angle = -Math.PI / 2 + index * (Math.PI / 2)
  const distance = radius * (value / 100)
  return `${100 + Math.cos(angle) * distance},${100 + Math.sin(angle) * distance}`
}

const DashboardOverview: React.FC<DashboardOverviewProps> = ({ token }) => {
  const [stats, setStats] = useState<DashboardStatsResponse | null>(null)
  const [curve, setCurve] = useState<LearningCurveEntry[]>([])
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([])
  const [achievements, setAchievements] = useState<AchievementsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      const [statsResult, curveResult, leaderboardResult, achievementsResult] = await Promise.allSettled([
        getDashboardStats(token),
        getLearningCurve(token),
        getLeaderboard(token),
        getAchievements(token),
      ])

      if (!active) return

      setStats(statsResult.status === 'fulfilled' ? statsResult.value : await getFallbackStats(token))
      setCurve(curveResult.status === 'fulfilled' ? curveResult.value : [])
      setLeaderboard(leaderboardResult.status === 'fulfilled' ? leaderboardResult.value : [])
      setAchievements(achievementsResult.status === 'fulfilled' ? achievementsResult.value : emptyAchievements)

      const failedLabels = [
        statsResult.status === 'rejected' ? 'stats' : null,
        curveResult.status === 'rejected' ? 'learning curve' : null,
        leaderboardResult.status === 'rejected' ? 'leaderboard' : null,
        achievementsResult.status === 'rejected' ? 'achievements' : null,
      ].filter(Boolean)

      if (failedLabels.length) {
        setError(`Some dashboard data is temporarily unavailable: ${failedLabels.join(', ')}.`)
      } else {
        setError(null)
      }
    }
    void load()
    const interval = window.setInterval(load, 15000)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [token])

  const radarPoints = useMemo(
    () => stats ? skillLabels.map(([, key], index) => point(index, stats.skill_scores[key])).join(' ') : '',
    [stats],
  )
  const maxTime = Math.max(...curve.map((entry) => entry.completion_time), 1)
  const curvePoints = curve.map((entry, index) => {
    const x = curve.length === 1 ? 10 : 10 + (index / (curve.length - 1)) * 280
    const y = 95 - (entry.completion_time / maxTime) * 75
    return `${x},${y}`
  }).join(' ')

  if (!stats || !achievements) return <div className="dashboard-empty">Loading learning dashboard...</div>

  return (
    <div className="learning-dashboard">
      {error && <div className="dashboard-warning">{error}</div>}
      <section className="dashboard-tier-card">
        <div>
          <span className="dashboard-label">CURRENT TIER</span>
          <h3 style={{ color: stats.current_tier.color }}>{stats.current_tier.name}</h3>
          <p>{stats.total_score} points / {stats.missions_completed} completed missions</p>
        </div>
        <div className="tier-progress-wrap">
          <span>{stats.current_tier.next_tier ? `Next: ${stats.current_tier.next_tier}` : 'Highest tier reached'}</span>
          <div className="tier-progress"><i style={{ width: `${stats.current_tier.progress}%` }} /></div>
        </div>
      </section>

      <div className="dashboard-grid">
        <section className="dashboard-card skill-card">
          <span className="dashboard-label">SKILL RADAR</span>
          <svg className="skill-radar" viewBox="0 0 200 200" role="img" aria-label="Skill radar chart">
            {[25, 50, 75, 100].map((value) => <polygon key={value} points={[0, 1, 2, 3].map((index) => point(index, value)).join(' ')} />)}
            <polygon className="skill-radar-value" points={radarPoints} />
          </svg>
          <div className="skill-list">
            {skillLabels.map(([label, key]) => <span key={key}>{label}<strong>{stats.skill_scores[key]}</strong></span>)}
          </div>
        </section>

        <section className="dashboard-card">
          <span className="dashboard-label">LEARNING CURVE / COMPLETION TIME</span>
          {curve.length ? (
            <>
              <svg className="learning-curve" viewBox="0 0 300 110" preserveAspectRatio="none" role="img" aria-label="Completion time trend">
                <polyline points={curvePoints} />
              </svg>
              <div className="curve-history">
                {curve.slice(-4).map((entry) => <span key={entry.attempt_id}>{entry.mission_name}<strong>{formatDuration(entry.completion_time)}</strong></span>)}
              </div>
            </>
          ) : <p className="dashboard-empty">Complete a mission to start your learning curve.</p>}
        </section>

        <section className="dashboard-card">
          <span className="dashboard-label">LEADERBOARD / TOP 10</span>
          {leaderboard.length ? (
            <ol className="leaderboard-list">
              {leaderboard.map((entry) => (
                <li className={entry.is_current_user ? 'current-user' : ''} key={entry.user_id}>
                  <b>#{entry.rank}</b><span>{entry.username}</span><strong>{entry.total_score}</strong>
                </li>
              ))}
            </ol>
          ) : <p className="dashboard-empty">Leaderboard data is not available yet.</p>}
        </section>

        <section className="dashboard-card">
          <span className="dashboard-label">ACHIEVEMENTS / {achievements.unlocked} OF {achievements.total}</span>
          {achievements.items.length ? (
            <div className="achievement-list">
              {achievements.items.map((achievement) => (
                <article className={achievement.unlocked ? 'unlocked' : ''} key={achievement.id}>
                  <strong>{achievement.name}</strong>
                  <span>{achievement.description}</span>
                </article>
              ))}
            </div>
          ) : <p className="dashboard-empty">Achievement data is not available yet.</p>}
        </section>
      </div>
    </div>
  )
}

export default DashboardOverview
