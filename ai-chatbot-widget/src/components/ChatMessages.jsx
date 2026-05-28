import './ChatMessages.css'

const ChatMessages = ({ messages, isLoading, messagesEndRef }) => {
  const formatTime = (date) => {
    return new Date(date).toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getHintLevelBadge = (level) => {
    const badges = {
      0: { text: 'L0', color: '#10b981' },
      1: { text: 'L1', color: '#3b82f6' },
      2: { text: 'L2', color: '#f59e0b' },
      3: { text: 'L3', color: '#ef4444' }
    }
    return badges[level] || badges[0]
  }

  return (
    <div className="chat-messages">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`message ${message.role} ${message.isError ? 'error' : ''}`}
        >
          <div className="message-content">
            {message.role === 'assistant' && message.hintLevel !== undefined && (
              <span 
                className="hint-badge"
                style={{ backgroundColor: getHintLevelBadge(message.hintLevel).color }}
              >
                {getHintLevelBadge(message.hintLevel).text}
              </span>
            )}
            
            <div className="message-text">
              {message.content.split('\n').map((line, i) => (
                <p key={i}>{line || '\u00A0'}</p>
              ))}
            </div>
            
            <span className="message-time">{formatTime(message.timestamp)}</span>
          </div>
        </div>
      ))}
      
      {isLoading && (
        <div className="message assistant">
          <div className="message-content">
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      )}
      
      <div ref={messagesEndRef} />
    </div>
  )
}

export default ChatMessages
