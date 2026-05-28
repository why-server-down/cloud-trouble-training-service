import { useRef, useEffect } from 'react'
import './ChatInput.css'

const ChatInput = ({ value, onChange, onSend, onKeyPress, disabled }) => {
  const textareaRef = useRef(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`
    }
  }, [value])

  const handleChange = (e) => {
    onChange(e.target.value)
  }

  return (
    <div className="chat-input">
      <div className="input-container">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyPress={onKeyPress}
          placeholder="메시지를 입력하세요... (Shift+Enter로 줄바꿈)"
          disabled={disabled}
          rows={1}
        />
        
        <button
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="send-button"
          aria-label="메시지 전송"
        >
          {disabled ? (
            <span className="loading-spinner">⏳</span>
          ) : (
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          )}
        </button>
      </div>
      
      <div className="input-hint">
        💡 Tip: Shift+Enter로 줄바꿈, Enter로 전송
      </div>
    </div>
  )
}

export default ChatInput
