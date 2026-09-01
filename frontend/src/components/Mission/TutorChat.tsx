import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { askTutor, TutorSource } from '../../services/api'
import { getEnvironmentMeta } from '../../config/environments'
import { getSafeSourceHref } from '../../utils/tutorSources'
import { EnvironmentId } from '../../types/training'

interface TutorChatProps {
  token: string
  missionId: string
  /**
   * 이 대화가 속한 훈련 환경 (FE-11).
   * `ChatResponse` 는 environment 를 내보내지 않으므로 활성 attempt 의 값을 받는다.
   */
  environment: EnvironmentId
  hintsUsed: number
  disabled?: boolean
  floating?: boolean
  floatingOpen?: boolean
  onToggleFloating?: () => void
}

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  /** 어시스턴트 답변의 근거. 없을 수 있고, 없어도 레이아웃이 바뀌지 않는다 (FE-11). */
  sources?: TutorSource[]
  /** 답변에 쓰인 관측값 이름. */
  observations?: string[]
  /** 프로바이더 실패로 받은 대체 응답인가. */
  fallback?: boolean
}

const initialMessages: ChatMessage[] = [
  { role: 'assistant', text: '막힌 지점을 질문해 주세요. 정답보다 다음 확인 순서를 먼저 제안합니다.' },
]
const FLOATING_TUTOR_QUERY = '(max-width: 980px), (max-height: 760px)'
/** 이 시간이 지나면 "무엇을 하고 있는지" 보조 문구를 띄운다 (FE-12). */
const SLOW_RESPONSE_HINT_MS = 1500
/** 이 시간이 지나면 취소 버튼을 준다. 자동 실패 처리는 하지 않는다 (FE-12). */
const CANCELLABLE_AFTER_MS = 15000


const renderInlineText = (text: string) => {
  const parts = text.split(/(`[^`]+`)/g)

  return parts.map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>
    }

    return <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>
  })
}

const ChatMessageContent: React.FC<{ text: string }> = ({ text }) => {
  const blocks = text
    .replace(/\r\n/g, '\n')
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean)

  return (
    <div className="chat-message-content">
      {blocks.map((block, blockIndex) => {
        const lines = block.split('\n').map((line) => line.trim()).filter(Boolean)
        const isList = lines.length > 1 && lines.every((line) => /^(\d+\.|[-*])\s+/.test(line))

        if (isList) {
          return (
            <ul key={`${block}-${blockIndex}`} className="chat-list">
              {lines.map((line, lineIndex) => (
                <li key={`${line}-${lineIndex}`}>
                  {renderInlineText(line.replace(/^(\d+\.|[-*])\s+/, ''))}
                </li>
              ))}
            </ul>
          )
        }

        return (
          <p key={`${block}-${blockIndex}`}>
            {lines.map((line, lineIndex) => (
              <React.Fragment key={`${line}-${lineIndex}`}>
                {lineIndex > 0 && <br />}
                {renderInlineText(line)}
              </React.Fragment>
            ))}
          </p>
        )
      })}
    </div>
  )
}

/** 접기 영역. sources / observations 가 없으면 아무것도 그리지 않는다 (FE-11). */
const ChatMessageEvidence: React.FC<{ message: ChatMessage }> = ({ message }) => {
  const observations = message.observations ?? []
  const sources = message.sources ?? []
  if (observations.length === 0 && sources.length === 0) return null

  return (
    <div className="chat-evidence">
      {observations.length > 0 && (
        <details className="chat-evidence-group">
          <summary>사용한 관측 정보 {observations.length}건</summary>
          <ul>
            {observations.map((name) => (
              <li key={name}><code>{name}</code></li>
            ))}
          </ul>
        </details>
      )}
      {sources.length > 0 && (
        <details className="chat-evidence-group">
          <summary>참고 자료 {sources.length}건</summary>
          <ul>
            {sources.map((source, index) => {
              const href = getSafeSourceHref(source.path)
              return (
                <li key={`${source.source_id ?? source.title}-${index}`}>
                  {href ? (
                    <a href={href} target="_blank" rel="noreferrer noopener">{source.title}</a>
                  ) : (
                    <span>{source.title}</span>
                  )}
                  {source.path && !href && <code className="chat-source-path">{source.path}</code>}
                </li>
              )
            })}
          </ul>
        </details>
      )}
    </div>
  )
}

const TutorChat: React.FC<TutorChatProps> = ({
  token,
  missionId,
  environment,
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
  /** 실패한 질문. 사용자의 입력을 버리지 않고 재전송 버튼을 준다 (FE-11). */
  const [retryQuestion, setRetryQuestion] = useState<string | null>(null)
  /** 응답이 늦을 때 무엇을 하고 있는지 알린다 (FE-12). */
  const [isSlow, setIsSlow] = useState(false)
  /** 오래 걸리면 취소 버튼을 준다. 자동 실패 처리는 하지 않는다 (FE-12). */
  const [isCancellable, setIsCancellable] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  /** 진행 중인 질문의 controller. unmount·attempt 종료·환경 변경에서 취소한다 (FE-11). */
  const requestRef = useRef<AbortController | null>(null)
  const [isFloatingViewport, setIsFloatingViewport] = useState(() =>
    typeof window === 'undefined' || !window.matchMedia ? false : window.matchMedia(FLOATING_TUTOR_QUERY).matches,
  )
  const hintLevel = Math.min(hintsUsed, 3)
  const isChatDisabled = loading || !missionId || disabled
  const environmentLabel = getEnvironmentMeta(environment).label
  const panelClassName = [
    'tutor-panel',
    floating ? 'tutor-floating' : '',
    floating && !floatingOpen ? 'tutor-collapsed' : '',
  ].filter(Boolean).join(' ')

  /*
   * attempt 나 환경이 바뀌면 대화를 비운다 (FE-11).
   * 진행 중인 질문도 취소한다 — 늦게 도착한 이전 환경의 답변이 새 대화에
   * 붙으면 사용자는 그것을 지금 환경의 근거로 읽는다.
   */
  useEffect(() => {
    requestRef.current?.abort()
    requestRef.current = null
    setMessages(initialMessages)
    setInput('')
    setError(null)
    setRetryQuestion(null)
    setLoading(false)
    setIsSlow(false)
    setIsCancellable(false)
  }, [missionId, environment])

  /** unmount 에서도 진행 중인 질문을 남기지 않는다. */
  useEffect(() => () => requestRef.current?.abort(), [])

  /** 지연 단계 타이머. loading 이 끝나면 함께 사라진다 (FE-12). */
  useEffect(() => {
    if (!loading) {
      setIsSlow(false)
      setIsCancellable(false)
      return undefined
    }

    const slowTimer = window.setTimeout(() => setIsSlow(true), SLOW_RESPONSE_HINT_MS)
    const cancelTimer = window.setTimeout(() => setIsCancellable(true), CANCELLABLE_AFTER_MS)

    return () => {
      window.clearTimeout(slowTimer)
      window.clearTimeout(cancelTimer)
    }
  }, [loading])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, loading])

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined

    const mediaQuery = window.matchMedia(FLOATING_TUTOR_QUERY)
    const handleViewportChange = () => setIsFloatingViewport(mediaQuery.matches)

    handleViewportChange()
    mediaQuery.addEventListener('change', handleViewportChange)

    return () => mediaQuery.removeEventListener('change', handleViewportChange)
  }, [])

  /**
   * 질문 1회 = chat API 1회 (FE-12).
   * `loading` 이 isChatDisabled 에 들어 있어 중복 제출이 막힌다. 진행 중인
   * controller 가 남아 있으면 그것도 방어선으로 쓴다.
   */
  const ask = useCallback(async (question: string) => {
    if (!question || !missionId || disabled || requestRef.current) return

    const controller = new AbortController()
    requestRef.current = controller
    const startedAt = performance.now()

    setLoading(true)
    setError(null)
    setRetryQuestion(null)
    setMessages((current) => [...current, { role: 'user', text: question }])

    try {
      const response = await askTutor(token, question, hintLevel, controller.signal)
      // 취소된 요청의 응답은 목록에 넣지 않는다.
      if (controller.signal.aborted) return

      if (import.meta.env.DEV) {
        console.debug(`[tutor] ${environment} 응답 ${Math.round(performance.now() - startedAt)}ms`)
      }

      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          text: response.response,
          sources: response.sources ?? [],
          observations: response.observations_used ?? [],
          fallback: Boolean(response.fallback_used),
        },
      ])
    } catch (err) {
      // 사용자가 취소한 것은 오류가 아니다.
      if (controller.signal.aborted || (err instanceof Error && err.name === 'AbortError')) return
      setError(err instanceof Error ? err.message : 'AI 튜터 응답을 받지 못했습니다.')
      setRetryQuestion(question)
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null
        setLoading(false)
      }
    }
  }, [disabled, environment, hintLevel, missionId, token])

  const submitQuestion = (event: React.FormEvent) => {
    event.preventDefault()
    const question = input.trim()
    if (!question || isChatDisabled) return

    setInput('')
    void ask(question)
  }

  /** 취소. 진행 중 요청만 끊고 사용자의 질문은 목록에 남긴다 (FE-12). */
  const cancelQuestion = () => {
    requestRef.current?.abort()
    requestRef.current = null
    setLoading(false)
    setError('질문을 취소했습니다. 다시 물어보실 수 있습니다.')
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
            {/* 색만으로 구분하지 않는다 — 환경 이름을 그대로 쓴다 (FE-11). */}
            <span className="tutor-environment-badge" data-environment={environment}>
              {environmentLabel}
            </span>
            <span className="tutor-hint-level">힌트 단계 {hintLevel}</span>
          </div>
          {floating && (
            <button className="tutor-floating-close" type="button" onClick={onToggleFloating}>
              닫기
            </button>
          )}
        </div>
        <div className="chat-messages" aria-live="polite">
          {messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={`chat-message ${message.role}`}>
              <span className="chat-message-role">{message.role === 'user' ? '나' : '튜터'}</span>
              <ChatMessageContent text={message.text} />
              {message.fallback && (
                <p className="chat-fallback-note">
                  AI 응답을 받지 못해 준비된 안내로 대체했습니다. 환경 관측 정보가 반영되지
                  않았을 수 있습니다.
                </p>
              )}
              <ChatMessageEvidence message={message} />
            </div>
          ))}
          {loading && (
            <div className="chat-message assistant chat-message-loading">
              <span className="chat-message-role">튜터</span>
              <span className="typing-indicator" aria-hidden="true"><span /><span /><span /></span>
              <span>
                {isSlow
                  ? `${environmentLabel} 환경 상태와 관련 문서를 분석 중입니다...`
                  : '답변을 준비하고 있습니다...'}
              </span>
              {isCancellable && (
                <button className="chat-cancel-btn" type="button" onClick={cancelQuestion}>
                  취소
                </button>
              )}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
        {error && (
          <div className="chat-error" role="alert">
            <span>{error}</span>
            {retryQuestion && (
              <button
                className="chat-retry-btn"
                type="button"
                disabled={isChatDisabled}
                onClick={() => void ask(retryQuestion)}
              >
                다시 질문
              </button>
            )}
          </div>
        )}
        <form className="chat-form" onSubmit={submitQuestion}>
          {/* label 이 없으면 스크린리더가 이 입력을 읽지 못한다 (FE-11 인수 조건). */}
          <label className="sr-only" htmlFor={`tutor-input-${missionId}`}>
            {environmentLabel} 훈련 질문 (Enter 로 전송)
          </label>
          <input
            id={`tutor-input-${missionId}`}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={isChatDisabled ? '질문할 수 없는 상태입니다' : '어떤 명령으로 원인을 찾아야 하나요?'}
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
