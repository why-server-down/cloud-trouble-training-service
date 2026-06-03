import React, { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { askTutor } from '../../services/api'

interface TutorChatProps {
  token: string
  missionId: string
  hintsUsed: number
  disabled?: boolean
  floating?: boolean
  floatingOpen?: boolean
  onToggleFloating?: () => void
}

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
}

const initialMessages: ChatMessage[] = [
  { role: 'assistant', text: '막힌 지점을 질문해 주세요. 정답보다 다음 확인 순서를 먼저 제안합니다.' },
]
const FLOATING_TUTOR_QUERY = '(max-width: 980px), (max-height: 760px)'

const TutorChat: React.FC<TutorChatProps> = ({
  token,
  missionId,
  hintsUsed,
  disabled,
  floating = false,
  floatingOpen = true,
  onToggleFloating,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isFloatingViewport, setIsFloatingViewport] = useState(() =>
    typeof window === 'undefined' || !window.matchMedia ? false : window.matchMedia(FLOATING_TUTOR_QUERY).matches,
  )
  const hintLevel = Math.min(hintsUsed, 3)
  const isChatDisabled = loading || !missionId || disabled
  const panelClassName = [
    'tutor-panel',
    floating ? 'tutor-floating' : '',
    floating && !floatingOpen ? 'tutor-collapsed' : '',
  ].filter(Boolean).join(' ')

  useEffect(() => {
    setMessages(initialMessages)
    setInput('')
    setError(null)
  }, [missionId])

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined

    const mediaQuery = window.matchMedia(FLOATING_TUTOR_QUERY)
    const handleViewportChange = () => setIsFloatingViewport(mediaQuery.matches)

    handleViewportChange()
    mediaQuery.addEventListener('change', handleViewportChange)

    return () => mediaQuery.removeEventListener('change', handleViewportChange)
  }, [])

  const submitQuestion = async (event: React.FormEvent) => {
    event.preventDefault()
    const question = input.trim()
    if (!question || isChatDisabled) return

    setInput('')
    setLoading(true)
    setError(null)
    setMessages((current) => [...current, { role: 'user', text: question }])

    try {
      const response = await askTutor(token, question, hintLevel)
      setMessages((current) => [...current, { role: 'assistant', text: response.response }])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 튜터 응답을 받지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const tutorChat = (
    <>
      {floating && !floatingOpen && (
        <button className="tutor-floating-launcher" type="button" onClick={onToggleFloating}>
          AI 튜터
        </button>
      )}
      <section className={panelClassName}>
        <div className="tutor-header">
          <div className="tutor-title-group">
            <span>AI 튜터</span>
            <span className="tutor-hint-level">힌트 단계 {hintLevel}</span>
          </div>
          {floating && (
            <button className="tutor-floating-close" type="button" onClick={onToggleFloating}>
              닫기
            </button>
          )}
        </div>
        <div className="chat-messages" aria-live="polite">
          {messages.map((message, index) => <div key={`${message.role}-${index}`} className={`chat-message ${message.role}`}>{message.text}</div>)}
          {loading && <div className="chat-message assistant">답변을 준비하고 있습니다...</div>}
        </div>
        {error && <div className="chat-error">{error}</div>}
        <form className="chat-form" onSubmit={submitQuestion}>
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={isChatDisabled ? '질문할 수 없는 상태입니다.' : '어떤 명령으로 원인을 찾아야 하나요?'}
            disabled={isChatDisabled}
          />
          <button type="submit" disabled={isChatDisabled || !input.trim()}>질문</button>
        </form>
      </section>
    </>
  )

  if (floating && isFloatingViewport && typeof document !== 'undefined') {
    return createPortal(tutorChat, document.body)
  }

  return tutorChat
}

export default TutorChat
