import React from 'react'
import './Feedback.css'

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
}) => (
  <div className="modal-backdrop" role="presentation" onMouseDown={onCancel}>
    <section
      className="confirm-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      onMouseDown={(event) => event.stopPropagation()}
    >
      <h3 id="confirm-modal-title">{title}</h3>
      <p>{message}</p>
      <div className="confirm-modal-actions">
        <button className="modal-button secondary" type="button" onClick={onCancel}>
          취소
        </button>
        <button className={`modal-button ${danger ? 'danger' : 'primary'}`} type="button" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </section>
  </div>
)

export default ConfirmModal
