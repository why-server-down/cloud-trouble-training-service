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

const missionCopy: Record<string, { name: string; description: string }> = {
  pod_failure: {
    name: '사라진 애플리케이션',
    description: 'Nginx Pod가 ImagePullBackOff 상태입니다. 이미지 이름을 수정하여 Pod를 정상 상태로 복구하세요.',
  },
  memory_stress: {
    name: '메모리 부족',
    description: '애플리케이션 Pod가 메모리 부족으로 종료됩니다. 리소스 제한을 확인하고 조정하세요.',
  },
  service_misconfig: {
    name: '끊어진 연결',
    description: 'Service 설정 오류로 트래픽이 Pod에 전달되지 않습니다. selector 설정을 확인하세요.',
  },
  network_latency: {
    name: '응답 없는 서버',
    description: 'Pod에 지속적인 장애가 발생합니다. 상태 확인 설정을 점검하고 자동 복구되도록 구성하세요.',
  },
}

const MissionCard: React.FC<MissionCardProps> = ({ mission, isActive, onStart }) => {
  const copy = missionCopy[mission.chaos_type] || { name: mission.name, description: mission.description }

  return (
  <button
    className={`mission-card ${!mission.is_unlocked ? 'locked' : ''} ${isActive ? 'active' : ''}`}
    type="button"
    onClick={() => onStart(mission.id)}
    disabled={!mission.is_unlocked || isActive}
  >
    <span className="mission-card-header">
      <span className="mission-title">{!mission.is_unlocked && 'LOCKED / '}{copy.name}</span>
      <span className="mission-level">Level {mission.level}</span>
    </span>
    <span className="mission-description">{copy.description}</span>
    <span className="mission-info">
      <span>제한 시간 {Math.floor(mission.time_limit / 60)}분</span>
      <span>기본 {mission.base_score}점</span>
      <span>힌트 -{mission.hint_penalty}점</span>
    </span>
    {isActive && <span className="mission-active-label">LIVE INCIDENT</span>}
  </button>
  )
}

export default MissionCard
