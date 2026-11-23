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
  /**
   * 연 요소가 사라졌을 때 focus 를 줄 곳 (FE-27). 예: 완료 확인 버튼은 미션이 끝나면
   * 인시던트 바와 함께 사라진다. 없으면 focus 가 문서 처음으로 떨어진다.
   */
  returnFocus?: () => HTMLElement | null
  onClose: () => void
  children: React.ReactNode
}

/** Tab 순환에 참여하는 요소. 숨겼거나 tabIndex=-1 인 것은 실제 Tab 대상이 아니므로 뺀다. */
const FOCUSABLE = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]',
].map((selector) => `${selector}:not([tabindex="-1"])`).join(', ')

const isTabbable = (element: HTMLElement) => !element.closest('[hidden], [inert]')

/**
 * 열려 있는 시트들. 위에 뜬 시트만 키보드를 처리한다 (프로필 위에 확인 시트가 뜨는 경우).
 * 같은 document 에 건 처리기는 stopPropagation 으로 서로 막지 못한다.
 */
const openSheets: HTMLElement[] = []

/** 시트가 하나라도 열려 있으면 앱 본문을 inert 로 만들어 뒤 화면 조작과 focus 를 막는다. */
const syncBackgroundInert = () => {
  const root = document.getElementById('root')
  if (!root) return
  if (openSheets.length > 0) root.setAttribute('inert', '')
  else root.removeAttribute('inert')
}

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
  returnFocus,
  onClose,
  children,
}) => {
  const sheetRef = useRef<HTMLElement | null>(null)
  const openerRef = useRef<Element | null>(null)
  // 부모가 렌더마다 새 onClose 를 넘겨도 key 처리기를 다시 걸지 않는다.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    const sheet = sheetRef.current
    if (sheet) openSheets.push(sheet)
    syncBackgroundInert()

    openerRef.current = document.activeElement
    ;(initialFocusRef?.current ?? sheet)?.focus()

    return () => {
      const index = sheet ? openSheets.indexOf(sheet) : -1
      if (index >= 0) openSheets.splice(index, 1)
      syncBackgroundInert()

      /*
       * 연 요소로 돌려준다. 그 버튼이 시트와 같은 순간 사라졌으면 opener 가 body 로 잡힌다
       * (완료 확인 → 인시던트 바가 사라짐). 그때는 정해 둔 자리로 보낸다.
       */
      const opener = openerRef.current
      const canReturn = opener instanceof HTMLElement && opener !== document.body && opener.isConnected
      if (canReturn) opener.focus()
      if (!canReturn || document.activeElement !== opener) returnFocus?.()?.focus()
    }
    // 처음 열릴 때 한 번만 정한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const sheet = sheetRef.current
      if (!sheet || openSheets[openSheets.length - 1] !== sheet) return

      if (event.key === 'Escape') {
        event.stopPropagation()
        onCloseRef.current()
        return
      }

      if (event.key !== 'Tab') return

      const focusable = Array.from(sheet.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(isTabbable)
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
