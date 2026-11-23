import React, { useRef } from 'react'
import Sheet from './Sheet'

interface ConfirmModalProps {
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}

const ConfirmModal: React.FC<ConfirmModalProps> = ({
  title,
  message,
  confirmLabel = '확인',
  danger = false,
  onConfirm,
  onCancel,
}) => {
  const confirmRef = useRef<HTMLButtonElement | null>(null)
  const cancelRef = useRef<HTMLButtonElement | null>(null)

  /*
   * 기본 focus. 일반 확인은 확인 버튼에 두어 키보드로 바로 결정하게 하고,
   * 위험한 확정(포기·명령 실행)은 취소에 둔다 — Enter 한 번으로 되돌릴 수 없는
   * 동작이 실행되면 안 된다 (설계 문서 8).
   */
  return (
    <Sheet
      className="confirm-modal"
      labelledBy="confirm-modal-title"
      describedBy="confirm-modal-message"
      initialFocusRef={danger ? cancelRef : confirmRef}
      onClose={onCancel}
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
    </Sheet>
  )
}

export default ConfirmModal
