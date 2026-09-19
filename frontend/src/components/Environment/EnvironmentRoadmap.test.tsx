import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import EnvironmentRoadmap from './EnvironmentRoadmap'
import { EnvironmentItem } from '../../types/training'

const renderRoadmap = (items: EnvironmentItem[]) => render(<EnvironmentRoadmap items={items} />)

/** 그룹 제목으로 목록을 찾아 그 안의 텍스트만 본다. */
const groupText = (title: string) => {
  const heading = screen.getByText(title)
  return heading.parentElement?.textContent ?? ''
}

const hasGroup = (title: string) => screen.queryByText(title) !== null

const NEXT = 'NEXT / 준비 중 환경'
const CLOSED = 'CLOSED / 이 서버에서 열지 않은 환경'

afterEach(cleanup)

describe('닫힌 환경 안내 (FE-23)', () => {
  it('아직 만들지 않은 환경은 무엇이 열릴지와 함께 준비 중으로 보여준다', () => {
    renderRoadmap([
      { id: 'kubernetes', status: 'available', capabilities: ['terminal'] },
      { id: 'linux', status: 'preparing', capabilities: [], reason: 'not_implemented' },
    ])

    expect(groupText(NEXT)).toContain('Linux')
    expect(groupText(NEXT)).toContain('준비 중')
    // 로드맵 항목(열릴 예정 기능)이 함께 보인다.
    expect(groupText(NEXT)).toContain('프로세스 및 서비스 장애 대응')
    expect(hasGroup(CLOSED)).toBe(false)
  })

  it('구현이 끝난 환경은 예정 목록이 아니라 닫힘 목록에 넣는다', () => {
    renderRoadmap([
      { id: 'kubernetes', status: 'available', capabilities: ['terminal'] },
      { id: 'docker', status: 'preparing', capabilities: [], reason: 'not_deployed' },
    ])

    expect(hasGroup(NEXT)).toBe(false)
    expect(groupText(CLOSED)).toContain('Docker')
    // 이미 동작하는 기능을 "열릴 예정"으로 광고하지 않는다.
    expect(groupText(CLOSED)).not.toContain('Docker Compose 서비스 장애 시뮬레이션')
  })

  it('두 이유가 섞여 오면 따로 나눠 보여준다', () => {
    renderRoadmap([
      { id: 'kubernetes', status: 'available', capabilities: ['terminal'] },
      { id: 'docker', status: 'preparing', capabilities: [], reason: 'not_deployed' },
      { id: 'linux', status: 'preparing', capabilities: [], reason: 'not_implemented' },
    ])

    expect(groupText(CLOSED)).toContain('Docker')
    expect(groupText(CLOSED)).not.toContain('Linux')
    expect(groupText(NEXT)).toContain('Linux')
    expect(groupText(NEXT)).not.toContain('Docker')
  })

  it('이유가 없으면 이 계약 이전과 같이 준비 중 목록에만 들어간다', () => {
    renderRoadmap([
      { id: 'kubernetes', status: 'available', capabilities: ['terminal'] },
      { id: 'docker', status: 'preparing', capabilities: [] },
    ])

    expect(groupText(NEXT)).toContain('Docker')
    expect(hasGroup(CLOSED)).toBe(false)
  })

  it('닫힌 환경이 없어도 후속 연구 안내는 남는다', () => {
    renderRoadmap([{ id: 'kubernetes', status: 'available', capabilities: ['terminal'] }])

    expect(hasGroup(NEXT)).toBe(false)
    expect(hasGroup(CLOSED)).toBe(false)
    expect(groupText('RESEARCH / 후속 연구')).toContain('Application')
  })
})
