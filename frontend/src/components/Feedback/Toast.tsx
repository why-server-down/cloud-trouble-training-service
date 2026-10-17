import React, { useEffect, useRef } from 'react'
import './Feedback.css'

export type ToastKind = 'success' | 'info' | 'error'

export interface ToastMessage {
  kind: ToastKind
  text: string
  /**
   * 알림마다 새 값. 같은 문구를 다시 알려도 타이머와 낭독이 처음부터 시작되게
   * 부모가 이 값을 key 로 쓴다.
   */
  id?: number
}

interface ToastProps extends ToastMessage {
  onClose: () => void
}

/** 성공·안내 토스트가 머무는 시간. 오류는 자동으로 닫지 않는다 (설계 문서 5.5). */
export const TOAST_AUTO_DISMISS_MS = 4000

/* 색만으로 종류를 말하지 않도록 아이콘 모양과 글자를 함께 둔다. */
const LABELS: Record<ToastKind, string> = {
  success: '완료',
  info: '안내',
  error: '오류',
}

const ICONS: Record<ToastKind, React.ReactNode> = {
  success: <path d="m5.4 8.2 1.8 1.8 3.4-3.6" />,
  info: <path d="M8 7.25v3.75M8 4.9v.15" />,
  error: <path d="M8 4.75v3.75M8 11.1v.15" />,
}

const Toast: React.FC<ToastProps> = ({ kind, text, onClose }) => {
  /*
   * 부모가 렌더할 때마다 새 onClose 를 넘겨도 타이머가 다시 시작되지 않게 ref 로 든다.
   * deps 에 onClose 를 넣으면 폴링으로 부모가 다시 그려질 때마다 4초가 처음부터 다시 센다.
   */
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (kind === 'error') return
    const timeout = window.setTimeout(() => onCloseRef.current(), TOAST_AUTO_DISMISS_MS)
    return () => window.clearTimeout(timeout)
  }, [kind, text])

  /*
   * 오류는 `alert`, 성공·정보는 `status` live region 을 쓴다 (FE-17).
   * 전부 status 로 두면 스크린리더가 오류를 "나중에 읽어도 되는 알림"으로 취급해
   * 사용자가 실패를 놓친다.
   */
  return (
    <div
      className={`toast material-popover ${kind}`}
      role={kind === 'error' ? 'alert' : 'status'}
      aria-live={kind === 'error' ? 'assertive' : 'polite'}
    >
      <svg className="toast-icon" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="8" cy="8" r="6.25" />
        {ICONS[kind]}
      </svg>
      <p className="toast-text">
        <strong>{LABELS[kind]}</strong> {text}
      </p>
      <button className="ui-button plain small toast-close" type="button" onClick={onClose} aria-label="알림 닫기">
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="m4.5 4.5 7 7M11.5 4.5l-7 7" />
        </svg>
      </button>
    </div>
  )
}

export default Toast
