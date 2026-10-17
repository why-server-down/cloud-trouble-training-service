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

  it('단계를 한국어 문장으로 함께 읽힌다', () => {
    render(<OnboardingTour steps={steps} run onClose={vi.fn()} />)

    expect(screen.getByRole('dialog').getAttribute('aria-describedby')).toContain('onboarding-tour-step')
    expect(screen.getByText('2단계 중 1단계')).toBeTruthy()
  })
})

describe('투어 카드 배치 (FE-28)', () => {
  const setViewport = (width: number, height: number) => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: height })
  }

  /** getBoundingClientRect 를 고정한 투어 대상. jsdom 은 레이아웃을 하지 않는다. */
  const mountTarget = (rect: { top: number; left: number; width: number; height: number }) => {
    const element = document.createElement('div')
    element.dataset.tour = 'placed'
    element.getBoundingClientRect = () =>
      ({ ...rect, right: rect.left + rect.width, bottom: rect.top + rect.height, x: rect.left, y: rect.top }) as DOMRect
    element.scrollIntoView = () => {}
    document.body.appendChild(element)
    return element
  }

  const original = { width: window.innerWidth, height: window.innerHeight }
  afterEach(() => {
    setViewport(original.width, original.height)
    document.querySelectorAll('[data-tour="placed"]').forEach((element) => element.remove())
  })

  const placedStep = (placement: TourStep['placement']): TourStep[] => [
    { target: '[data-tour="placed"]', eyebrow: '미션', title: '배치', body: '설명', placement },
  ]

  it('모바일에서 옆에도 위아래에도 자리가 없으면 화면 아래 가운데에 둔다', () => {
    // 390px 화면에서 폭을 다 쓰고 세로로 길게 차지한 미션 목록 (390x844 실측과 같은 크기)
    setViewport(390, 844)
    mountTarget({ top: 146, left: 24, width: 342, height: 626 })
    render(<OnboardingTour steps={placedStep('right')} run onClose={vi.fn()} />)

    const card = screen.getByRole('dialog')
    expect(card.style.bottom).toBe('16px')
    expect(card.style.top).toBe('')
    // 카드 폭 340px 를 390px 화면 가운데에
    expect(card.style.width).toBe('340px')
    expect(card.style.left).toBe('25px')
  })

  it('원하는 방향에 자리가 없고 아래에 자리가 있으면 대상 아래에 둔다', () => {
    setViewport(390, 844)
    mountTarget({ top: 68, left: 24, width: 342, height: 54 })
    render(<OnboardingTour steps={placedStep('left')} run onClose={vi.fn()} />)

    const card = screen.getByRole('dialog')
    // 스포트라이트 여백(8px)을 더한 대상 아래쪽 + 간격 16px
    expect(card.style.top).toBe(`${68 + 54 + 8 + 16}px`)
  })

  it('데스크톱에서 자리가 있으면 원하는 방향을 지킨다', () => {
    setViewport(1366, 768)
    mountTarget({ top: 120, left: 40, width: 380, height: 600 })
    render(<OnboardingTour steps={placedStep('right')} run onClose={vi.fn()} />)

    const card = screen.getByRole('dialog')
    // 스포트라이트 여백(8px)을 더한 대상 오른쪽 + 간격 16px
    expect(card.style.left).toBe(`${40 + 380 + 8 + 16}px`)
  })
})
