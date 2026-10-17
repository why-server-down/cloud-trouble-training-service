import React from 'react'
import { getEnvironmentMeta } from '../../config/environments'
import { MissionResponse } from '../../types/training'
import { getMissionCopy } from './missionCopy'
import { LockIcon } from './Icons'

interface MissionCardProps {
  mission: MissionResponse
  isActive: boolean
  onStart: (missionId: string) => void
}

const MissionCard: React.FC<MissionCardProps> = ({ mission, isActive, onStart }) => {
  const copy = getMissionCopy(mission)
  const isLocked = !mission.is_unlocked
  /*
   * 잠긴 카드와 진행 중 카드는 disabled 대신 aria-disabled 로 둔다 (설계 문서 8).
   * disabled 는 Tab 순서에서 빠져 키보드·스크린리더 사용자가 "왜 못 누르는지"를 듣지 못한다.
   * 대신 클릭은 여기서 막는다.
   */
  const isInert = isLocked || isActive

  return (
    <button
      className={`mission-card${isLocked ? ' locked' : ''}${isActive ? ' active' : ''}`}
      type="button"
      onClick={() => {
        if (!isInert) onStart(mission.id)
      }}
      aria-disabled={isInert || undefined}
    >
      {isActive && (
        <span className="mission-active-label">
          <span className="ui-live-dot" aria-hidden="true" />
          진행 중
        </span>
      )}
      <span className="mission-card-header">
        <span className="mission-title">{copy.name}</span>
        <span className="ui-chip mission-level">레벨 {mission.level}</span>
      </span>
      <span className="mission-description">{copy.description}</span>
      <span className="mission-info">
        {/* 색이 아니라 글자로 환경을 밝힌다 — 색만으로 구분하면 읽지 못하는 사용자가 생긴다. */}
        <span className="ui-chip mission-environment-badge">{getEnvironmentMeta(mission.environment).label}</span>
        <span>제한 시간 {Math.floor(mission.time_limit / 60)}분</span>
        <span>기본 {mission.base_score}점</span>
        <span>힌트 −{mission.hint_penalty}점</span>
      </span>
      {/* 마지막 줄은 카드의 상태다: 잠김이면 열리는 조건, 열려 있으면 시작 안내. */}
      {isLocked ? (
        <span className="mission-card-status">
          <span className="ui-chip">
            <LockIcon />
            잠김
          </span>
          이전 레벨을 완료하면 열립니다
        </span>
      ) : (
        !isActive && (
          <span className="mission-card-status mission-start-cue" aria-hidden="true">
            시작 →
          </span>
        )
      )}
    </button>
  )
}

export default MissionCard
