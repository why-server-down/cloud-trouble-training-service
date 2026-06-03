import React, { useEffect } from 'react'
import './Feedback.css'

export type ToastKind = 'success' | 'info' | 'error'

export interface ToastMessage {
  kind: ToastKind
  text: string
}

interface ToastProps extends ToastMessage {
  onClose: () => void
}

const Toast: React.FC<ToastProps> = ({ kind, text, onClose }) => {
  useEffect(() => {
    const timeout = window.setTimeout(onClose, 3500)
    return () => window.clearTimeout(timeout)
  }, [onClose, text])

  return (
    <div className={`toast ${kind}`} role="status">
      <span>{text}</span>
      <button type="button" onClick={onClose} aria-label="알림 닫기">
        닫기
      </button>
    </div>
  )
}

export default Toast
