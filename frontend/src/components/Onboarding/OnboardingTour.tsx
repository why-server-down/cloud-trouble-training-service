import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
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
const EDGE_GUTTER = 14

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

const getTooltipPosition = (rect: TargetRect | null, placement: TourStep['placement']) => {
  const width = Math.min(TOOLTIP_WIDTH, window.innerWidth - EDGE_GUTTER * 2)

  if (!rect) {
    return {
      width,
      left: (window.innerWidth - width) / 2,
      top: Math.max(EDGE_GUTTER, window.innerHeight * 0.22),
    }
  }

  const preferredPlacement = placement || 'bottom'
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2
  let left = centerX - width / 2
  let top = rect.top + rect.height + TOOLTIP_GAP

  if (preferredPlacement === 'top') top = rect.top - TOOLTIP_GAP
  if (preferredPlacement === 'left') {
    left = rect.left - width - TOOLTIP_GAP
    top = centerY
  }
  if (preferredPlacement === 'right') {
    left = rect.left + rect.width + TOOLTIP_GAP
    top = centerY
  }

  left = clamp(left, EDGE_GUTTER, window.innerWidth - width - EDGE_GUTTER)

  if (preferredPlacement === 'top') {
    return { width, left, bottom: window.innerHeight - rect.top + TOOLTIP_GAP }
  }

  if (preferredPlacement === 'left' || preferredPlacement === 'right') {
    top = clamp(top - 120, EDGE_GUTTER, window.innerHeight - 260)
  } else {
    top = clamp(top, EDGE_GUTTER, window.innerHeight - 260)
  }

  return { width, left, top }
}

function OnboardingTour({ steps, run, onClose, onStepChange }: OnboardingTourProps) {
  const [stepIndex, setStepIndex] = useState(0)
  const [targetRect, setTargetRect] = useState<TargetRect | null>(null)
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

  useEffect(() => {
    if (!run || !currentStep) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'ArrowRight' || event.key === 'Enter') {
        event.preventDefault()
        setStepIndex((index) => (index >= steps.length - 1 ? index : index + 1))
      }
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setStepIndex((index) => Math.max(0, index - 1))
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [currentStep, onClose, run, steps.length])

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
    <div className="onboarding-tour" role="dialog" aria-modal="true" aria-labelledby="onboarding-tour-title">
      {paddedRect ? (
        <>
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

      <section className="tour-card" style={tooltipPosition}>
        <div className="tour-card-header">
          <span>{currentStep.eyebrow}</span>
          <span>{String(stepIndex + 1).padStart(2, '0')} / {String(steps.length).padStart(2, '0')}</span>
        </div>
        <h2 id="onboarding-tour-title">{currentStep.title}</h2>
        <p>{currentStep.body}</p>
        <div className="tour-progress" aria-hidden="true">
          {steps.map((step) => (
            <span key={step.target + step.title} className={steps.indexOf(step) <= stepIndex ? 'active' : ''} />
          ))}
        </div>
        <div className="tour-actions">
          <button className="tour-button ghost" type="button" onClick={onClose}>SKIP</button>
          <div>
            <button
              className="tour-button ghost"
              type="button"
              onClick={() => setStepIndex((index) => Math.max(0, index - 1))}
              disabled={stepIndex === 0}
            >
              BACK
            </button>
            <button className="tour-button primary" type="button" onClick={goNext}>
              {isLastStep ? 'DONE' : 'NEXT'}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}

export default OnboardingTour
