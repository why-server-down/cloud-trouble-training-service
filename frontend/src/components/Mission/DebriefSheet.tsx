import React, { useRef } from 'react'
import Sheet from '../Feedback/Sheet'
import { AlertIcon, CheckIcon } from './Icons'

export type DebriefOutcome = 'completed' | 'failed' | 'abandoned'

export interface Debrief {
  outcome: DebriefOutcome
  missionTitle: string
  environmentLabel: string
  /** 서버가 확정한 최종 점수. 모르면 null — 프론트에서 계산하지 않는다. */
  finalScore: number | null
  baseScore: number | null
  /** 서버 시각(시작·종료)으로 잰 걸린 시간. */
  durationSeconds: number | null
  hintsUsed: number
  /** 무엇이 문제였나. 모르면 null. */
  cause: string | null
  /** 이번 시도에서 터미널에 보낸 명령 (최근 것이 마지막). */
  commands: string[]
  /** 시도 중간에 화면을 새로 열어 그 전에 보낸 명령은 기록에 없다. */
  commandsPartial: boolean
}

interface DebriefSheetProps {
  debrief: Debrief
  /** 다음 동작. 완료면 "다음 미션 고르기", 아니면 "다시 도전". 없으면 닫기만 둔다. */
  primaryLabel?: string
  onPrimary?: () => void
  onClose: () => void
  returnFocus?: () => HTMLElement | null
}

const OUTCOME_LABELS: Record<DebriefOutcome, string> = {
  completed: '복구 완료',
  failed: '시간 초과',
  abandoned: '미션 포기',
}

/** 디브리프에 보여 줄 최근 명령 수. 길면 시트가 명령 로그가 된다. */
const MAX_COMMANDS = 8

const formatDuration = (seconds: number) => {
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return minutes > 0 ? `${minutes}분 ${rest}초` : `${rest}초`
}

/** `백틱`으로 감싼 부분을 명령으로 그린다. */
const renderInline = (text: string) =>
  text.split(/(`[^`]+`)/g).map((part, index) =>
    part.startsWith('`') && part.endsWith('`') ? (
      <code key={index}>{part.slice(1, -1)}</code>
    ) : (
      <React.Fragment key={index}>{part}</React.Fragment>
    ),
  )

/**
 * 미션 결과 시트 (FE-27). 완료·시간 초과·포기 모두 같은 시트를 쓴다.
 *
 * 예전에는 셋 다 3.5초 토스트였고, 시간 초과는 아무 말 없이 끝났다. 점수표보다
 * "무엇이 문제였고 내가 무엇을 쳤는지"가 다음 훈련에 쓸모 있으므로 둘을 함께 둔다.
 */
const DebriefSheet: React.FC<DebriefSheetProps> = ({ debrief, primaryLabel, onPrimary, onClose, returnFocus }) => {
  // 처음 focus 는 제목. 버튼에 두면 스크린리더가 결과를 건너뛰고 행동부터 읽는다.
  const titleRef = useRef<HTMLHeadingElement | null>(null)
  const commands = debrief.commands.slice(-MAX_COMMANDS)
  const skipped = debrief.commands.length - commands.length

  return (
    <Sheet
      className={`debrief-sheet outcome-${debrief.outcome}`}
      labelledBy="debrief-title"
      describedBy="debrief-outcome"
      initialFocusRef={titleRef}
      returnFocus={returnFocus}
      onClose={onClose}
    >
      <p id="debrief-outcome" className="debrief-outcome">
        {debrief.outcome === 'completed' ? <CheckIcon /> : <AlertIcon />}
        {OUTCOME_LABELS[debrief.outcome]}
      </p>
      <h2 id="debrief-title" className="sheet-title" ref={titleRef} tabIndex={-1}>{debrief.missionTitle}</h2>
      <div className="sheet-chips">
        <span className="ui-chip">{debrief.environmentLabel}</span>
      </div>

      <dl className="debrief-stats">
        <div>
          <dt>최종 점수</dt>
          <dd>
            {debrief.finalScore ?? '—'}
            {debrief.finalScore !== null && <span className="debrief-unit">점</span>}
            {debrief.baseScore !== null && debrief.finalScore !== null && (
              <span className="debrief-sub">기본 {debrief.baseScore}점</span>
            )}
          </dd>
        </div>
        <div>
          <dt>걸린 시간</dt>
          <dd>{debrief.durationSeconds !== null ? formatDuration(debrief.durationSeconds) : '—'}</dd>
        </div>
        <div>
          <dt>사용한 힌트</dt>
          <dd>
            {debrief.hintsUsed}
            <span className="debrief-unit">회</span>
          </dd>
        </div>
      </dl>

      {debrief.cause && (
        <section className="debrief-section" aria-labelledby="debrief-cause-title">
          <h3 id="debrief-cause-title">무엇이 문제였나</h3>
          <p>{renderInline(debrief.cause)}</p>
        </section>
      )}

      <section className="debrief-section" aria-labelledby="debrief-commands-title">
        <h3 id="debrief-commands-title">내가 실행한 명령</h3>
        {debrief.commandsPartial && (
          <p className="debrief-note">시도 중간에 화면을 새로 열어, 그 전에 보낸 명령은 기록되지 않았습니다.</p>
        )}
        {commands.length > 0 ? (
          <>
            {skipped > 0 && <p className="debrief-note">앞의 {skipped}개는 생략했습니다.</p>}
            <ol className="debrief-commands" start={skipped + 1}>
              {commands.map((command, index) => (
                <li key={`${index}-${command}`}>
                  <code>{command}</code>
                </li>
              ))}
            </ol>
          </>
        ) : (
          !debrief.commandsPartial && <p className="debrief-note">이번 시도에서 터미널에 보낸 명령이 없습니다.</p>
        )}
      </section>

      <div className="sheet-actions">
        <button className="ui-button plain" type="button" onClick={onClose}>
          닫기
        </button>
        {onPrimary && primaryLabel && (
          <button className="ui-button primary" type="button" onClick={onPrimary}>
            {primaryLabel}
          </button>
        )}
      </div>
    </Sheet>
  )
}

export default DebriefSheet
