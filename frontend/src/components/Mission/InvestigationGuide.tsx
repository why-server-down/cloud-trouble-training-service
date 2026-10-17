import React from 'react'
import { getEnvironmentMeta, getEnvironmentTerminal } from '../../config/environments'
import { EnvironmentId } from '../../types/training'
import { CheckIcon } from './Icons'

interface InvestigationGuideProps {
  environment: EnvironmentId
  /**
   * 미션 중인가. 미션 중에는 첫 단계(미션 선택)를 끝난 것으로 표시하고,
   * 조사 명령을 눌러 터미널 입력줄에 넣을 수 있다.
   */
  active?: boolean
  onInsertCommand?: (command: string) => void
}

/**
 * 조사 순서와 조사 시작 명령 (FE-09, FE-26).
 *
 * 미션 전 시작 가이드와 미션 중 브리핑이 같이 쓴다. 예전에는 미션을 시작하면 이 안내가
 * 사라져 학생이 조사 명령을 기억해서 쳐야 했다 (기준선 진단 "기억보다 인식").
 * 단계 번호 01 → 02 → 03 은 실제 순서라 장식이 아니다.
 */
const InvestigationGuide: React.FC<InvestigationGuideProps> = ({ environment, active = false, onInsertCommand }) => {
  const { investigationStarters, investigationClues } = getEnvironmentTerminal(environment)
  const { investigationHint } = getEnvironmentMeta(environment)
  const steps = [
    {
      title: '미션 선택',
      body: active ? '장애가 주입된 미션을 진행하고 있습니다.' : '잠금 해제된 미션을 고르고 시작합니다.',
      done: active,
    },
    { title: '상태 조사', body: investigationHint, done: false },
    {
      title: '복구 및 검증',
      body: active
        ? '원인을 고친 뒤 위쪽의 완료 확인을 누릅니다.'
        : '원인을 수정한 뒤 완료 확인을 실행합니다.',
      done: false,
    },
  ]

  return (
    <div className="investigation-guide">
      <ol className="tutorial-steps">
        {steps.map((step, index) => (
          <li key={step.title} className={step.done ? 'is-done' : undefined}>
            <span className="tutorial-step-index" aria-hidden="true">
              {step.done ? <CheckIcon /> : String(index + 1).padStart(2, '0')}
            </span>
            <strong>
              {step.title}
              {step.done && <span className="sr-only"> (완료)</span>}
            </strong>
            <span>{step.body}</span>
          </li>
        ))}
      </ol>
      <div className="tutorial-commands">
        <span className="panel-label">조사 시작 명령</span>
        {onInsertCommand ? (
          <>
            {investigationStarters.map((command) => (
              <div key={command} className="guide-command-row">
                <button
                  className="guide-command"
                  type="button"
                  onClick={() => onInsertCommand(command)}
                  aria-label={`${command.trim()} — 터미널 입력줄에 넣기`}
                >
                  <code>{command}</code>
                  <span className="guide-command-action" aria-hidden="true">입력</span>
                </button>
                {investigationClues[command] && <p className="guide-command-clue">볼 곳: {investigationClues[command]}</p>}
              </div>
            ))}
            <p className="guide-command-note">누르면 실행하지 않고 입력줄에만 넣습니다. 확인한 뒤 Enter를 누르세요.</p>
          </>
        ) : (
          investigationStarters.map((command) => (
            <div key={command} className="guide-command-row">
              <code>{command}</code>
              {investigationClues[command] && <p className="guide-command-clue">볼 곳: {investigationClues[command]}</p>}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default InvestigationGuide
