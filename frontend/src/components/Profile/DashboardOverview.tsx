import React, { useEffect, useMemo, useState } from 'react'
import {
  AchievementsResponse,
  DashboardStatsResponse,
  getAchievements,
  getDashboardStats,
  getLeaderboard,
  getLearningCurve,
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
      try {
        const [nextStats, nextCurve, nextLeaderboard, nextAchievements] = await Promise.all([
          getDashboardStats(token),
          getLearningCurve(token),
          getLeaderboard(token),
          getAchievements(token),
        ])
        if (!active) return
        setStats(nextStats)
        setCurve(nextCurve)
        setLeaderboard(nextLeaderboard)
        setAchievements(nextAchievements)
        setError(null)
      } catch (loadError) {
        if (active) setError(loadError instanceof Error ? loadError.message : 'Failed to load dashboard.')
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

  if (error) return <div className="dashboard-error">{error}</div>
  if (!stats || !achievements) return <div className="dashboard-empty">Loading learning dashboard...</div>

  return (
    <div className="learning-dashboard">
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
          <ol className="leaderboard-list">
            {leaderboard.map((entry) => (
              <li className={entry.is_current_user ? 'current-user' : ''} key={entry.user_id}>
                <b>#{entry.rank}</b><span>{entry.username}</span><strong>{entry.total_score}</strong>
              </li>
            ))}
          </ol>
        </section>

        <section className="dashboard-card">
          <span className="dashboard-label">ACHIEVEMENTS / {achievements.unlocked} OF {achievements.total}</span>
          <div className="achievement-list">
            {achievements.items.map((achievement) => (
              <article className={achievement.unlocked ? 'unlocked' : ''} key={achievement.id}>
                <strong>{achievement.name}</strong>
                <span>{achievement.description}</span>
              </article>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

export default DashboardOverview
