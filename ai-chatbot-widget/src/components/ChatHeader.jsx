import './ChatHeader.css'

const ChatHeader = ({ hintLevel, hintsUsed }) => {
  const hintLevelNames = {
    0: '일반 방향',
    1: '구체적 조사',
    2: '정확한 명령어',
    3: '완전한 해결책'
  }

  return (
    <div className="chat-header">
      <div className="header-left">
        <div className="bot-avatar">🤖</div>
        <div className="header-info">
          <h3>AI Tutor</h3>
          <span className="status">온라인</span>
        </div>
      </div>
      
      <div className="header-right">
        <div className="hint-info">
          <span className="hint-level">
            Level {hintLevel}: {hintLevelNames[hintLevel]}
          </span>
          <span className="hints-used">
            힌트 사용: {hintsUsed}회
          </span>
        </div>
      </div>
    </div>
  )
}

export default ChatHeader
