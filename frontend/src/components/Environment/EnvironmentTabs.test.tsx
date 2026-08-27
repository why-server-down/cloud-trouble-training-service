import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import EnvironmentTabs from './EnvironmentTabs'
import { EnvironmentItem } from '../../types/training'

const items: EnvironmentItem[] = [
  { id: 'kubernetes', status: 'available', capabilities: ['terminal'] },
  { id: 'docker', status: 'preparing', capabilities: [] },
  { id: 'linux', status: 'preparing', capabilities: [] },
]

const renderTabs = (override: Partial<React.ComponentProps<typeof EnvironmentTabs>> = {}) => {
  const onSelect = vi.fn()
  render(
    <EnvironmentTabs
      items={items}
      active="kubernetes"
      lockedTo={null}
      onSelect={onSelect}
      {...override}
    />,
  )
  return { onSelect }
}

const tab = (label: string) => screen.getByRole('tab', { name: new RegExp(label) })

afterEach(cleanup)

describe('환경 탭 상태 표시', () => {
  it('available 환경만 선택 가능하고 준비 중은 aria-disabled 다', () => {
    renderTabs()

    expect(tab('Kubernetes').getAttribute('aria-disabled')).toBe('false')
    expect(tab('Kubernetes').getAttribute('aria-selected')).toBe('true')
    expect(tab('Docker').getAttribute('aria-disabled')).toBe('true')
    expect(tab('Linux').getAttribute('aria-disabled')).toBe('true')
  })

  it('상태 문구를 tooltip 없이 탭 안에 노출한다', () => {
    renderTabs()

    expect(tab('Docker').textContent).toContain('준비 중')
    expect(tab('Kubernetes').textContent).toContain('쿠버네티스 장애 대응')
  })

  it('degraded 는 진입 가능하다', () => {
    const { onSelect } = renderTabs({
      items: [{ id: 'kubernetes', status: 'available', capabilities: [] }, { id: 'docker', status: 'degraded', capabilities: [] }],
    })

    expect(tab('Docker').getAttribute('aria-disabled')).toBe('false')
    fireEvent.click(tab('Docker'))
    expect(onSelect).toHaveBeenCalledWith('docker')
  })

  it('백엔드가 모르는 status 는 선택 불가로 처리한다', () => {
    const { onSelect } = renderTabs({
      items: [{ id: 'kubernetes', status: 'available', capabilities: [] }, { id: 'docker', status: 'exploded', capabilities: [] }],
    })

    expect(tab('Docker').textContent).toContain('상태 확인 불가')
    fireEvent.click(tab('Docker'))
    expect(onSelect).not.toHaveBeenCalled()
  })
})

describe('선택 동작', () => {
  it('준비 중 탭을 클릭해도 선택 콜백이 불리지 않는다', () => {
    const { onSelect } = renderTabs()

    fireEvent.click(tab('Docker'))
    fireEvent.click(tab('Linux'))

    expect(onSelect).not.toHaveBeenCalled()
  })

  it('활성 attempt 환경이 있으면 다른 환경은 잠기고 이유가 보인다', () => {
    const { onSelect } = renderTabs({
      items: [
        { id: 'kubernetes', status: 'available', capabilities: [] },
        { id: 'docker', status: 'available', capabilities: [] },
      ],
      lockedTo: 'kubernetes',
    })

    expect(tab('Docker').getAttribute('aria-disabled')).toBe('true')
    expect(tab('Docker').textContent).toContain('진행 중인 미션 환경으로 고정')

    fireEvent.click(tab('Docker'))
    expect(onSelect).not.toHaveBeenCalled()
  })
})

describe('키보드 조작', () => {
  it('활성 탭만 Tab 순서에 들어간다 (roving tabindex)', () => {
    renderTabs()

    expect(tab('Kubernetes').getAttribute('tabindex')).toBe('0')
    expect(tab('Docker').getAttribute('tabindex')).toBe('-1')
  })

  it('화살표로 이동하면 선택 가능한 환경은 즉시 선택된다', () => {
    const { onSelect } = renderTabs({
      items: [
        { id: 'kubernetes', status: 'available', capabilities: [] },
        { id: 'docker', status: 'available', capabilities: [] },
      ],
    })

    tab('Kubernetes').focus()
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' })

    expect(document.activeElement).toBe(tab('Docker'))
    expect(onSelect).toHaveBeenCalledWith('docker')
  })

  it('화살표가 준비 중 탭에 닿으면 포커스만 가고 선택되지 않는다', () => {
    const { onSelect } = renderTabs()

    tab('Kubernetes').focus()
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' })

    expect(document.activeElement).toBe(tab('Docker'))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('End / Home 으로 양끝으로 이동한다', () => {
    renderTabs()

    tab('Kubernetes').focus()
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'End' })
    expect(document.activeElement).toBe(tab('Linux'))

    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'Home' })
    expect(document.activeElement).toBe(tab('Kubernetes'))
  })

  it('ArrowLeft 는 첫 탭에서 마지막으로 감싼다', () => {
    renderTabs()

    tab('Kubernetes').focus()
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowLeft' })

    expect(document.activeElement).toBe(tab('Linux'))
  })
})
