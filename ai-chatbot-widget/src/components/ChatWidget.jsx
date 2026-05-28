import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import ChatHeader from './ChatHeader'
import ChatMessages from './ChatMessages'
import ChatInput from './ChatInput'
import HintPanel from './HintPanel'
import './ChatWidget.css'

const ChatWidget = ({ config }) => {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: '안녕하세요! 저는 Kubernetes 트러블슈팅을 도와드리는 AI 튜터입니다. 무엇을 도와드릴까요?',
      timestamp: new Date(),
    }
  ])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [hintLevel, setHintLevel] = useState(0)
  const [hintsUsed, setHintsUsed] = useState(0)
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: inputValue,
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setIsLoading(true)

    try {
      // TODO: Replace with actual API call
      // For now, simulate API response
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      const aiMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: `[Hint Level ${hintLevel}] 이것은 시뮬레이션 응답입니다. Backend API 연동 후 실제 AI 응답으로 대체됩니다.\n\n질문: "${inputValue}"\n\n실제 구현 시 여기에 소크라테스식 튜터링 응답이 표시됩니다.`,
        timestamp: new Date(),
        hintLevel,
      }

      setMessages(prev => [...prev, aiMessage])

      // Notify parent window
      window.parent.postMessage({
        type: 'CHATBOT_MESSAGE_SENT',
        data: { userMessage, aiMessage }
      }, '*')

    } catch (error) {
      console.error('Error sending message:', error)
      
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: '죄송합니다. 메시지 전송 중 오류가 발생했습니다. 다시 시도해주세요.',
        timestamp: new Date(),
        isError: true,
      }
      
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const handleIncreaseHint = () => {
    if (hintLevel < 3) {
      setHintLevel(prev => prev + 1)
      setHintsUsed(prev => prev + 1)
      
      const penalties = { 1: 5, 2: 10, 3: 50 }
      const penalty = penalties[hintLevel + 1] || 0
      
      const hintMessage = {
        id: Date.now(),
        role: 'system',
        content: `힌트 레벨이 ${hintLevel + 1}로 증가했습니다. (점수 -${penalty}점)`,
        timestamp: new Date(),
      }
      
      setMessages(prev => [...prev, hintMessage])
    }
  }

  const handleResetHint = () => {
    setHintLevel(0)
    
    const resetMessage = {
      id: Date.now(),
      role: 'system',
      content: '힌트 레벨이 0으로 초기화되었습니다.',
      timestamp: new Date(),
    }
    
    setMessages(prev => [...prev, resetMessage])
  }

  return (
    <div className="chat-widget">
      <ChatHeader 
        hintLevel={hintLevel}
        hintsUsed={hintsUsed}
      />
      
      <div className="chat-body">
        <ChatMessages 
          messages={messages}
          isLoading={isLoading}
          messagesEndRef={messagesEndRef}
        />
        
        <HintPanel
          hintLevel={hintLevel}
          onIncreaseHint={handleIncreaseHint}
          onResetHint={handleResetHint}
        />
      </div>

      <ChatInput
        value={inputValue}
        onChange={setInputValue}
        onSend={handleSendMessage}
        onKeyPress={handleKeyPress}
        disabled={isLoading}
      />
    </div>
  )
}

export default ChatWidget
