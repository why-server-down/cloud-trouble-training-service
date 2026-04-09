import React from 'react'

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

interface MissionCardProps {
  mission: Mission
  isActive: boolean
  onStart: (missionId: string) => void
}

const MissionCard: React.FC<MissionCardProps> = ({ mission, isActive, onStart }) => {
  const handleClick = () => {
    if (!mission.is_unlocked || isActive) return
    onStart(mission.id)
  }

  const formatTime = (seconds: number) => {
    const minutes = Math.floor(seconds / 60)
    return `${minutes}분`
  }

  return (
    <div
      className={`mission-card ${!mission.is_unlocked ? 'locked' : ''} ${isActive ? 'active' : ''}`}
      onClick={handleClick}
    >
      <div className="mission-card-header">
        <span className="mission-title">
          {!mission.is_unlocked && '🔒 '}
          {mission.name}
        </span>
        <span className="mission-level">Level {mission.level}</span>
      </div>
      <p className="mission-description">{mission.description}</p>
      <div className="mission-info">
        <span>⏱️ {formatTime(mission.time_limit)}</span>
        <span>⭐ {mission.base_score}점</span>
        <span>💡 -{mission.hint_penalty}점</span>
      </div>
      {isActive && (
        <div style={{ marginTop: '0.5rem', color: '#4caf50', fontWeight: 'bold' }}>
          ▶ 진행 중
        </div>
      )}
    </div>
  )
}

export default MissionCard
