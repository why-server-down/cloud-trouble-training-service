import React, { useRef } from 'react'

import { getEnvironmentMeta, isSelectableStatus, statusNote } from '../../config/environments'
import { EnvironmentId, EnvironmentItem } from '../../types/training'

interface EnvironmentTabsProps {
  items: EnvironmentItem[]
  active: EnvironmentId | null
  /** 활성 attempt 의 환경. 값이 있으면 그 환경 외의 탭은 모두 잠긴다 (FE-05). */
  lockedTo: EnvironmentId | null
  onSelect: (environment: EnvironmentId) => void
}

const MOVE_KEYS = ['ArrowRight', 'ArrowLeft', 'Home', 'End']

/**
 * 환경 선택 탭.
 *
 * - 선택 가능 여부는 서버가 준 status 와 활성 attempt 로만 결정한다.
 * - 선택 불가 탭은 `disabled` 가 아니라 `aria-disabled` 다. 포커스는 받을 수 있어야
 *   이유(준비 중 / 미션 고정)를 읽을 수 있고, 클릭·자동활성화는 막힌다.
 * - 이유 문구는 tooltip 이 아니라 탭 안에 직접 노출한다 (FE-03 인수 조건).
 */
const EnvironmentTabs: React.FC<EnvironmentTabsProps> = ({ items, active, lockedTo, onSelect }) => {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])

  const disabledReason = (item: EnvironmentItem): string | null => {
    if (lockedTo && lockedTo !== item.id) return '진행 중인 미션 환경으로 고정'
    if (!isSelectableStatus(item.status)) return statusNote(item.status)
    return null
  }

  // 선택 불가 탭에서는 아무 일도 하지 않는다 — 세션 생성이나 API 요청이 나가면 안 된다.
  const select = (item: EnvironmentItem) => {
    if (disabledReason(item)) return
    onSelect(item.id)
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!MOVE_KEYS.includes(event.key)) return
    event.preventDefault()

    const focused = tabRefs.current.findIndex((tab) => tab === document.activeElement)
    const from = focused >= 0 ? focused : items.findIndex((item) => item.id === active)
    const last = items.length - 1
    const next =
      event.key === 'Home' ? 0
        : event.key === 'End' ? last
          : event.key === 'ArrowRight' ? (from >= last ? 0 : from + 1)
            : (from <= 0 ? last : from - 1)

    tabRefs.current[next]?.focus()
    // 이동과 동시에 활성화한다. 잠긴 탭은 포커스만 가고 선택되지 않는다.
    select(items[next])
  }

  return (
    <div
      className="env-tabs"
      role="tablist"
      aria-label="환경 선택"
      data-tour="env-tabs"
      onKeyDown={handleKeyDown}
    >
      {items.map((item, index) => {
        const meta = getEnvironmentMeta(item.id)
        const reason = disabledReason(item)
        const isActive = active === item.id

        return (
          <button
            key={item.id}
            ref={(node) => {
              tabRefs.current[index] = node
            }}
            type="button"
            role="tab"
            id={`env-tab-${item.id}`}
            data-environment={item.id}
            className={`env-tab${isActive ? ' active' : ''}`}
            aria-selected={isActive}
            aria-disabled={reason !== null}
            aria-controls="env-panel"
            tabIndex={isActive ? 0 : -1}
            onClick={() => select(item)}
          >
            <span className="env-tab-label">{meta.label}</span>
            <span className="env-tab-sub">{reason ?? meta.subtitle}</span>
          </button>
        )
      })}
    </div>
  )
}

export default EnvironmentTabs
