import './HintPanel.css'

const HintPanel = ({ hintLevel, onIncreaseHint, onResetHint }) => {
  const hintLevels = [
    {
      level: 0,
      name: '일반 방향',
      description: '문제 해결의 일반적인 방향 제시',
      penalty: 0,
      color: '#10b981'
    },
    {
      level: 1,
      name: '구체적 조사',
      description: '구체적인 조사 방법과 체크포인트',
      penalty: 5,
      color: '#3b82f6'
    },
    {
      level: 2,
      name: '정확한 명령어',
      description: '정확한 kubectl 명령어 제공',
      penalty: 10,
      color: '#f59e0b'
    },
    {
      level: 3,
      name: '완전한 해결책',
      description: '완전한 해결 방법과 설명',
      penalty: 50,
      color: '#ef4444'
    }
  ]

  return (
    <div className="hint-panel">
      <div className="hint-panel-header">
        <h4>💡 힌트 시스템</h4>
        <span className="current-level">현재: Level {hintLevel}</span>
      </div>

      <div className="hint-levels">
        {hintLevels.map((hint) => (
          <div
            key={hint.level}
            className={`hint-level-item ${hintLevel === hint.level ? 'active' : ''} ${hintLevel > hint.level ? 'passed' : ''}`}
            style={{ borderLeftColor: hint.color }}
          >
            <div className="hint-level-header">
              <span className="level-badge" style={{ backgroundColor: hint.color }}>
                L{hint.level}
              </span>
              <span className="level-name">{hint.name}</span>
              {hint.penalty > 0 && (
                <span className="level-penalty">-{hint.penalty}점</span>
              )}
            </div>
            <p className="level-description">{hint.description}</p>
          </div>
        ))}
      </div>

      <div className="hint-actions">
        <button
          onClick={onIncreaseHint}
          disabled={hintLevel >= 3}
          className="hint-button increase"
        >
          {hintLevel >= 3 ? '최대 레벨' : `힌트 레벨 올리기 (${hintLevels[hintLevel + 1]?.penalty || 0}점 차감)`}
        </button>
        
        <button
          onClick={onResetHint}
          disabled={hintLevel === 0}
          className="hint-button reset"
        >
          레벨 초기화
        </button>
      </div>

      <div className="hint-info-box">
        <p>
          <strong>📌 힌트 시스템 안내</strong>
        </p>
        <ul>
          <li>힌트 레벨을 올릴수록 더 구체적인 도움을 받을 수 있습니다</li>
          <li>높은 레벨의 힌트는 점수가 차감됩니다</li>
          <li>스스로 해결할수록 더 많은 점수를 획득합니다</li>
        </ul>
      </div>
    </div>
  )
}

export default HintPanel
