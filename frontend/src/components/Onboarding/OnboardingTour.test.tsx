import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import OnboardingTour, { TourStep } from './OnboardingTour'

const steps: TourStep[] = [
  { target: '[data-tour="none-1"]', eyebrow: '상단 정보', title: '첫 단계', body: '첫 설명' },
  { target: '[data-tour="none-2"]', eyebrow: '미션', title: '둘째 단계', body: '둘째 설명' },
]

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('온보딩 투어 접근성 (FE-24)', () => {
  it('열리면 카드가 dialog 로 이름을 갖고 focus 를 받는다', () => {
    render(<OnboardingTour steps={steps} run onClose={vi.fn()} />)

    const dialog = screen.getByRole('dialog', { name: '첫 단계' })
    expect(document.activeElement).toBe(dialog)
    expect(screen.getByText('1 / 2')).toBeTruthy()
  })

  it('건너뛰기 버튼에서 Enter 를 눌러도 다음 단계로 넘어가지 않는다', () => {
    const onClose = vi.fn()
    render(<OnboardingTour steps={steps} run onClose={onClose} />)

    const skip = screen.getByRole('button', { name: '건너뛰기' })
    skip.focus()
    fireEvent.keyDown(skip, { key: 'Enter' })

    // Enter 는 focus 된 버튼의 기본 동작에 맡긴다. 전역 처리기가 '다음'으로 가로채지 않는다.
    expect(screen.getByRole('dialog', { name: '첫 단계' })).toBeTruthy()
  })

  it('카드에 focus 가 있을 때 Enter 는 다음, 마지막 단계에서는 닫기다', () => {
    const onClose = vi.fn()
    render(<OnboardingTour steps={steps} run onClose={onClose} />)

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Enter' })
    const second = screen.getByRole('dialog', { name: '둘째 단계' })
    expect(document.activeElement).toBe(second)
    expect(screen.getByRole('button', { name: '이전' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '완료' })).toBeTruthy()

    fireEvent.keyDown(second, { key: 'Enter' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Escape 로 닫힌다', () => {
    const onClose = vi.fn()
    render(<OnboardingTour steps={steps} run onClose={onClose} />)

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
