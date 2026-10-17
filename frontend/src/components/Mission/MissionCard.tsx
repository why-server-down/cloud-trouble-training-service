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

/**
 * 미션 큐의 한 줄 (FE-29). 레벨 번호 | 제목·설명·조건 | 상태.
 * 카드 안의 카드와 줄마다 반복되던 환경 칩을 걷어냈다 — 환경은 위의 환경 탭이 말한다.
 */
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
      <span className="mission-index" aria-hidden="true">
        {String(mission.level).padStart(2, '0')}
      </span>
      <span className="mission-title">
        {/* 줄에서 뺀 레벨과 환경은 스크린리더에는 그대로 읽힌다. */}
        <span className="sr-only">레벨 {mission.level} · {getEnvironmentMeta(mission.environment).label} · </span>
        {copy.name}
      </span>
      <span className="mission-description">{copy.description}</span>
      <span className="mission-info">
        <span>제한 시간 {Math.floor(mission.time_limit / 60)}분</span>
        <span>기본 {mission.base_score}점</span>
        <span>힌트 −{mission.hint_penalty}점</span>
      </span>
      {/* 오른쪽 끝은 줄의 상태다: 진행 중, 잠김과 열리는 조건, 또는 시작 안내. */}
      {isActive ? (
        <span className="mission-state mission-active-label">
          <span className="ui-live-dot" aria-hidden="true" />
          진행 중
        </span>
      ) : isLocked ? (
        <span className="mission-state mission-lock-state">
          <span className="ui-chip">
            <LockIcon />
            잠김
          </span>
          <span className="mission-lock-reason">이전 레벨을 완료하면 열립니다</span>
        </span>
      ) : (
        <span className="mission-state mission-start-cue" aria-hidden="true">
          시작 →
        </span>
      )}
    </button>
  )
}

export default MissionCard
