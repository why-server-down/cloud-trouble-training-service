import React, { useEffect, useRef } from 'react'
import './Feedback.css'

interface ConfirmModalProps {
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** Tab 순환에 참여하는 요소. 모달 안에는 버튼만 있으므로 이 정도로 충분하다. */
const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'

const ConfirmModal: React.FC<ConfirmModalProps> = ({
  title,
  message,
  confirmLabel = '확인',
  danger = false,
  onConfirm,
  onCancel,
}) => {
  const dialogRef = useRef<HTMLElement | null>(null)
  const confirmRef = useRef<HTMLButtonElement | null>(null)
  const cancelRef = useRef<HTMLButtonElement | null>(null)
  /** 모달을 연 요소. 닫힌 뒤 focus 를 돌려주기 위해 기억한다 (FE-17). */
  const openerRef = useRef<Element | null>(null)

  useEffect(() => {
    openerRef.current = document.activeElement
    /*
     * 기본 focus. 일반 확인은 확인 버튼에 두어 키보드로 바로 결정하게 하고,
     * 위험한 확정(포기·명령 실행)은 취소에 둔다 — Enter 한 번으로 되돌릴 수 없는
     * 동작이 실행되면 안 된다 (설계 문서 8).
     */
    const initialFocus = danger ? cancelRef.current : confirmRef.current
    initialFocus?.focus()

    return () => {
      const opener = openerRef.current
      if (opener instanceof HTMLElement && document.contains(opener)) opener.focus()
    }
    // 처음 열릴 때 한 번만 정한다. 열린 뒤 danger 가 바뀌어도 focus 를 옮기지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /*
   * focus trap (FE-17).
   *
   * trap 이 없으면 Tab 이 모달 뒤의 터미널·미션 버튼으로 빠져나간다. 스크린리더
   * 사용자는 모달이 떠 있는 줄 모른 채 뒤 화면을 조작하게 된다.
   */
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onCancel()
        return
      }

      if (event.key !== 'Tab') return

      const dialog = dialogRef.current
      if (!dialog) return

      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement

      if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault()
        last.focus()
        return
      }

      if (!event.shiftKey && (active === last || !dialog.contains(active))) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown, true)
    return () => document.removeEventListener('keydown', handleKeyDown, true)
  }, [onCancel])

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onCancel}>
      <section
        ref={dialogRef}
        className="confirm-modal material-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        aria-describedby="confirm-modal-message"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h3 id="confirm-modal-title">{title}</h3>
        <p id="confirm-modal-message">{message}</p>
        <div className="confirm-modal-actions">
          <button ref={cancelRef} className="modal-button secondary ui-button plain" type="button" onClick={onCancel}>
            취소
          </button>
          <button
            ref={confirmRef}
            className={`modal-button ui-button ${danger ? 'danger filled' : 'primary'}`}
            type="button"
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  )
}

export default ConfirmModal
