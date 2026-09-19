import React from 'react'

import {
  ENVIRONMENT_ROADMAP,
  getEnvironmentMeta,
  isSelectableStatus,
  RESEARCH_TOPICS,
  showsRoadmap,
  unavailableNote,
} from '../../config/environments'
import { EnvironmentItem } from '../../types/training'

interface EnvironmentRoadmapProps {
  items: EnvironmentItem[]
}

/**
 * 선택할 수 없는 환경과 후속 연구 영역 안내.
 *
 * 준비 중 탭은 눌러도 아무 일이 없으므로(FE-03), 무엇이 열릴 예정인지는 이 영역에서
 * 보여준다. Application / DB 는 캡스톤2 스코프가 아니라 후속 연구로 표기한다(AGENTS.md).
 *
 * 닫힌 환경을 한 묶음으로 보여주지 않는 이유 (FE-23): 아직 만들지 않은 환경과 다 만들고
 * 이 배포에서만 닫은 환경은 사용자가 기다려야 하는지가 다르다. 후자를 "준비 중 · 열릴
 * 예정" 목록에 넣으면 이미 동작하는 기능을 예정으로 광고하게 된다.
 */
const EnvironmentRoadmap: React.FC<EnvironmentRoadmapProps> = ({ items }) => {
  const closed = items.filter((item) => !isSelectableStatus(item.status))
  const pending = closed.filter((item) => showsRoadmap(item))
  const notDeployed = closed.filter((item) => !showsRoadmap(item))

  return (
    <div className="env-roadmap">
      {pending.length > 0 && (
        <div className="env-roadmap-group">
          <span>NEXT / 준비 중 환경</span>
          <ul>
            {pending.map((item) => (
              <li key={item.id}>
                <strong>{getEnvironmentMeta(item.id).label}</strong> · {unavailableNote(item)}
                {ENVIRONMENT_ROADMAP[item.id].length > 0 && (
                  <span className="env-roadmap-detail">{ENVIRONMENT_ROADMAP[item.id].join(' · ')}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {notDeployed.length > 0 && (
        <div className="env-roadmap-group">
          <span>CLOSED / 이 서버에서 열지 않은 환경</span>
          <ul>
            {notDeployed.map((item) => (
              <li key={item.id}>
                <strong>{getEnvironmentMeta(item.id).label}</strong> · 구현은 끝났지만 이 서버에서는 열지 않았습니다
                <span className="env-roadmap-detail">{getEnvironmentMeta(item.id).subtitle}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="env-roadmap-group">
        <span>RESEARCH / 후속 연구</span>
        <ul>
          {RESEARCH_TOPICS.map((topic) => (
            <li key={topic.label}>
              <strong>{topic.label}</strong> · {topic.note}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default EnvironmentRoadmap
