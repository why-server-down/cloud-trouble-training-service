import React from 'react'

import {
  ENVIRONMENT_ROADMAP,
  getEnvironmentMeta,
  isSelectableStatus,
  RESEARCH_TOPICS,
  statusNote,
} from '../../config/environments'
import { EnvironmentItem } from '../../types/training'

interface EnvironmentRoadmapProps {
  items: EnvironmentItem[]
}

/**
 * 준비 중 환경과 후속 연구 영역 안내.
 *
 * 준비 중 탭은 눌러도 아무 일이 없으므로(FE-03), 무엇이 열릴 예정인지는 이 영역에서
 * 보여준다. Application / DB 는 캡스톤2 스코프가 아니라 후속 연구로 표기한다(AGENTS.md).
 */
const EnvironmentRoadmap: React.FC<EnvironmentRoadmapProps> = ({ items }) => {
  const pending = items.filter((item) => !isSelectableStatus(item.status))

  return (
    <div className="env-roadmap">
      {pending.length > 0 && (
        <div className="env-roadmap-group">
          <span>NEXT / 준비 중 환경</span>
          <ul>
            {pending.map((item) => (
              <li key={item.id}>
                <strong>{getEnvironmentMeta(item.id).label}</strong> · {statusNote(item.status)}
                {ENVIRONMENT_ROADMAP[item.id].length > 0 && (
                  <span className="env-roadmap-detail">{ENVIRONMENT_ROADMAP[item.id].join(' · ')}</span>
                )}
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
