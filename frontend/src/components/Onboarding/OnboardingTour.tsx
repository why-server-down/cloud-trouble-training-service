import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import './OnboardingTour.css'

export type TourStep = {
  target: string
  eyebrow: string
  title: string
  body: string
  placement?: 'top' | 'right' | 'bottom' | 'left'
}

interface OnboardingTourProps {
  steps: TourStep[]
  run: boolean
  onClose: () => void
  onStepChange?: (step: TourStep, index: number) => void
}

type TargetRect = {
  top: number
  left: number
  width: number
  height: number
}

const SPOTLIGHT_PADDING = 8
const TOOLTIP_WIDTH = 340
const TOOLTIP_GAP = 16
const EDGE_GUTTER = 16

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)

const getVisibleRect = (selector: string): TargetRect | null => {
  const element = document.querySelector(selector)
  if (!element) return null

  const rect = element.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return null
  if (rect.bottom < 0 || rect.right < 0 || rect.top > window.innerHeight || rect.left > window.innerWidth) return null

  return {
    top: rect.top,
    left: rect.left,
    width: rect.width,
    height: rect.height,
  }
}

/** 카드 높이 어림값. 문구가 세 줄일 때 약 230px 이라 넉넉히 잡는다. */
const CARD_HEIGHT_ESTIMATE = 260

type Placement = NonNullable<TourStep['placement']>

/**
 * 카드 위치. 원하는 방향에 자리가 없으면 아래 → 위 순서로 옮기고, 그래도 없으면
 * 화면 아래 가운데에 둔다 (FE-28). 모바일에서는 대상이 화면 폭을 다 쓰므로 left/right 가
 * 들어갈 수 없다 — 예전에는 그 좌표를 화면 안으로 끌어와 카드가 대상 한가운데를 덮었다.
 */
const getTooltipPosition = (rect: TargetRect | null, placement: TourStep['placement']) => {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const width = Math.min(TOOLTIP_WIDTH, vw - EDGE_GUTTER * 2)
  const centeredLeft = (vw - width) / 2

  if (!rect) {
    return { width, left: centeredLeft, top: Math.max(EDGE_GUTTER, vh * 0.22) }
  }

  const right = rect.left + rect.width
  const bottom = rect.top + rect.height
  const fits: Record<Placement, boolean> = {
    right: right + TOOLTIP_GAP + width <= vw - EDGE_GUTTER,
    left: rect.left - TOOLTIP_GAP - width >= EDGE_GUTTER,
    bottom: bottom + TOOLTIP_GAP + CARD_HEIGHT_ESTIMATE <= vh - EDGE_GUTTER,
    top: rect.top - TOOLTIP_GAP - CARD_HEIGHT_ESTIMATE >= EDGE_GUTTER,
  }
  const chosen = ([placement ?? 'bottom', 'bottom', 'top'] as Placement[]).find((p) => fits[p])

  const alignedLeft = clamp(rect.left + rect.width / 2 - width / 2, EDGE_GUTTER, vw - width - EDGE_GUTTER)
  const sideTop = clamp(rect.top + rect.height / 2 - 120, EDGE_GUTTER, vh - CARD_HEIGHT_ESTIMATE - EDGE_GUTTER)

  switch (chosen) {
    case 'right':
      return { width, left: right + TOOLTIP_GAP, top: sideTop }
    case 'left':
      return { width, left: rect.left - width - TOOLTIP_GAP, top: sideTop }
    case 'bottom':
      return { width, left: alignedLeft, top: bottom + TOOLTIP_GAP }
    case 'top':
      return { width, left: alignedLeft, bottom: vh - rect.top + TOOLTIP_GAP }
    default:
      return { width, left: centeredLeft, bottom: EDGE_GUTTER }
  }
}

function OnboardingTour({ steps, run, onClose, onStepChange }: OnboardingTourProps) {
  const [stepIndex, setStepIndex] = useState(0)
  const [targetRect, setTargetRect] = useState<TargetRect | null>(null)
  const cardRef = useRef<HTMLElement | null>(null)
  const currentStep = steps[stepIndex]
  const isLastStep = stepIndex === steps.length - 1

  const paddedRect = useMemo(() => {
    if (!targetRect) return null
    return {
      top: Math.max(EDGE_GUTTER, targetRect.top - SPOTLIGHT_PADDING),
      left: Math.max(EDGE_GUTTER, targetRect.left - SPOTLIGHT_PADDING),
      width: Math.min(window.innerWidth - EDGE_GUTTER * 2, targetRect.width + SPOTLIGHT_PADDING * 2),
      height: Math.min(window.innerHeight - EDGE_GUTTER * 2, targetRect.height + SPOTLIGHT_PADDING * 2),
    }
  }, [targetRect])

  const tooltipPosition = useMemo(
    () => getTooltipPosition(paddedRect, currentStep?.placement),
    [currentStep?.placement, paddedRect],
  )

  useEffect(() => {
    if (run) setStepIndex(0)
  }, [run, steps])

  /* 투어를 연 요소. 닫힌 뒤 focus 를 돌려준다. */
  useEffect(() => {
    if (!run) return
    const opener = document.activeElement
    return () => {
      if (opener instanceof HTMLElement && document.contains(opener)) opener.focus()
    }
  }, [run])

  /* 열릴 때와 단계가 바뀔 때 카드로 focus 를 옮긴다 (설계 문서 8). */
  useEffect(() => {
    if (run) cardRef.current?.focus({ preventScroll: true })
  }, [run, stepIndex])

  useEffect(() => {
    if (!run || !currentStep) return

    const handleKeyDown = (event: KeyboardEvent) => {
      const card = cardRef.current
      if (event.key === 'Escape') {
        onClose()
        return
      }
      /*
       * Enter 는 focus 된 버튼이 처리한다. 전역에서 Enter 를 '다음'으로 가로채면
       * 건너뛰기 버튼에서 Enter 를 눌러도 다음 단계로 넘어간다.
       * 카드 자체에 focus 가 있을 때만 '다음'으로 쓴다.
       */
      if (event.key === 'Enter' && event.target === card) {
        event.preventDefault()
        if (stepIndex >= steps.length - 1) onClose()
        else setStepIndex(stepIndex + 1)
        return
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault()
        setStepIndex((index) => (index >= steps.length - 1 ? index : index + 1))
      }
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setStepIndex((index) => Math.max(0, index - 1))
      }
      /* focus trap: Tab 이 투어 뒤의 화면으로 빠져나가지 않게 카드 버튼 안에서 돈다. */
      if (event.key === 'Tab' && card) {
        const buttons = Array.from(card.querySelectorAll<HTMLElement>('button:not([disabled])'))
        if (buttons.length === 0) return
        const first = buttons[0]
        const last = buttons[buttons.length - 1]
        const active = document.activeElement
        if (event.shiftKey && (active === first || active === card || !card.contains(active))) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && (active === last || !card.contains(active))) {
          event.preventDefault()
          first.focus()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [currentStep, onClose, run, stepIndex, steps.length])

  useLayoutEffect(() => {
    if (!run || !currentStep) return

    onStepChange?.(currentStep, stepIndex)

    const updateTarget = () => setTargetRect(getVisibleRect(currentStep.target))
    const target = document.querySelector(currentStep.target)
    target?.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' })

    const timer = window.setTimeout(updateTarget, 120)
    updateTarget()

    window.addEventListener('resize', updateTarget)
    window.addEventListener('scroll', updateTarget, true)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('resize', updateTarget)
      window.removeEventListener('scroll', updateTarget, true)
    }
  }, [currentStep, onStepChange, run, stepIndex])

  if (!run || !currentStep) return null

  const goNext = () => {
    if (isLastStep) {
      onClose()
      return
    }
    setStepIndex((index) => index + 1)
  }

  return (
    <div className="onboarding-tour">
      {paddedRect ? (
        <>
          {/* 투어 중에는 뒤 화면을 누르지 못하게 막는다. 어둡게 하는 건 스포트라이트의 그림자다. */}
          <div className="tour-scrim tour-scrim-top" style={{ height: paddedRect.top }} />
          <div
            className="tour-scrim tour-scrim-left"
            style={{ top: paddedRect.top, width: paddedRect.left, height: paddedRect.height }}
          />
          <div
            className="tour-scrim tour-scrim-right"
            style={{
              top: paddedRect.top,
              left: paddedRect.left + paddedRect.width,
              right: 0,
              height: paddedRect.height,
            }}
          />
          <div
            className="tour-scrim tour-scrim-bottom"
            style={{ top: paddedRect.top + paddedRect.height }}
          />
          <div className="tour-spotlight" style={paddedRect} />
        </>
      ) : (
        <div className="tour-scrim tour-scrim-full" />
      )}

      <section
        ref={cardRef}
        className="tour-card material-popover"
        style={tooltipPosition}
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-tour-title"
        aria-describedby="onboarding-tour-step onboarding-tour-body"
        tabIndex={-1}
      >
        <div className="tour-card-header">
          <span>{currentStep.eyebrow}</span>
          {/* 화면에는 짧게, 스크린리더에는 한국어 문장으로 단계를 알린다. */}
          <span className="tour-count" aria-hidden="true">
            {stepIndex + 1} / {steps.length}
          </span>
          <span id="onboarding-tour-step" className="sr-only">
            {steps.length}단계 중 {stepIndex + 1}단계
          </span>
        </div>
        <h2 id="onboarding-tour-title">{currentStep.title}</h2>
        <p id="onboarding-tour-body">{currentStep.body}</p>
        <div className="tour-actions">
          <button className="ui-button plain small" type="button" onClick={onClose}>
            건너뛰기
          </button>
          <div>
            {stepIndex > 0 && (
              <button
                className="ui-button plain small"
                type="button"
                onClick={() => setStepIndex((index) => Math.max(0, index - 1))}
              >
                이전
              </button>
            )}
            <button className="ui-button primary small" type="button" onClick={goNext}>
              {isLastStep ? '완료' : '다음'}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}

export default OnboardingTour
