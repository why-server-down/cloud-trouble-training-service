import React, { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import './Feedback.css'

interface SheetProps {
  /** 제목 요소의 id. 스크린리더가 시트 이름으로 읽는다. */
  labelledBy: string
  describedBy?: string
  /** center = 가운데 확인 시트, side = 오른쪽 드로어(모바일에서는 전체 시트). */
  variant?: 'center' | 'side'
  className?: string
  /** 처음 focus 를 받을 요소. 없으면 시트 자체가 받는다. */
  initialFocusRef?: React.RefObject<HTMLElement>
  onClose: () => void
  children: React.ReactNode
}

/** Tab 순환에 참여하는 요소. */
const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * 모달 시트 (FE-25). 확인 시트·프로필·시작/디브리프 시트가 함께 쓴다.
 *
 * - scrim 으로 뒤를 누르고 focus 를 안에 가둔다. 가두지 않으면 Tab 이 뒤의 터미널로
 *   빠져나가 스크린리더 사용자는 시트가 떠 있는 줄 모른다 (FE-17).
 * - Esc 로 닫고, 닫히면 연 요소로 focus 를 돌려준다.
 * - body 로 portal 한다. 부모에 transform·backdrop-filter 가 있으면 fixed 가 그 안에 갇힌다.
 */
const Sheet: React.FC<SheetProps> = ({
  labelledBy,
  describedBy,
  variant = 'center',
  className = '',
  initialFocusRef,
  onClose,
  children,
}) => {
  const sheetRef = useRef<HTMLElement | null>(null)
  const openerRef = useRef<Element | null>(null)
  // 부모가 렌더마다 새 onClose 를 넘겨도 key 처리기를 다시 걸지 않는다.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    openerRef.current = document.activeElement
    ;(initialFocusRef?.current ?? sheetRef.current)?.focus()

    return () => {
      const opener = openerRef.current
      if (opener instanceof HTMLElement && document.contains(opener)) opener.focus()
    }
    // 처음 열릴 때 한 번만 정한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onCloseRef.current()
        return
      }

      if (event.key !== 'Tab') return

      const sheet = sheetRef.current
      if (!sheet) return

      const focusable = Array.from(sheet.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (focusable.length === 0) {
        event.preventDefault()
        sheet.focus()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement

      if (event.shiftKey && (active === first || active === sheet || !sheet.contains(active))) {
        event.preventDefault()
        last.focus()
        return
      }

      if (!event.shiftKey && (active === last || !sheet.contains(active))) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown, true)
    return () => document.removeEventListener('keydown', handleKeyDown, true)
  }, [])

  return createPortal(
    <div
      className={`modal-backdrop sheet-backdrop-${variant}`}
      role="presentation"
      onMouseDown={() => onCloseRef.current()}
    >
      <section
        ref={sheetRef}
        className={`sheet sheet-${variant} material-sheet ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        {children}
      </section>
    </div>,
    document.body,
  )
}

export default Sheet
