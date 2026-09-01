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

  /*
   * 오류는 `alert`, 성공·정보는 `status` live region 을 쓴다 (FE-17).
   * 전부 status 로 두면 스크린리더가 오류를 "나중에 읽어도 되는 알림"으로 취급해
   * 사용자가 실패를 놓친다.
   */
  return (
    <div
      className={`toast ${kind}`}
      role={kind === 'error' ? 'alert' : 'status'}
      aria-live={kind === 'error' ? 'assertive' : 'polite'}
    >
      <span>{text}</span>
      <button type="button" onClick={onClose} aria-label="알림 닫기">
        닫기
      </button>
    </div>
  )
}

export default Toast
