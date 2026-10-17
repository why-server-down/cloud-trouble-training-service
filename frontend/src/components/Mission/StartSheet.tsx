import React, { useRef } from 'react'
import Sheet from '../Feedback/Sheet'
import { AlertIcon } from './Icons'
import { HINT_LEVELS } from './missionCopy'

/*
 * 채점 규칙 표시용 상수. 계산은 하지 않고 안내만 한다 — 원본은 백엔드
 * `backend/app/services/scoring_service.py` (TIME_PENALTY_PER_MINUTE, MIN_SCORE)다.
 * 백엔드 값이 바뀌면 여기 문구도 함께 고친다.
 */
// 서버는 int(경과 분 × 2) 만큼 깎는다 = 30초마다 1점.
const SECONDS_PER_PENALTY_POINT = 30
const MIN_COMPLETION_SCORE = 20

interface StartSheetProps {
  /** 정적 미션 = 미션 시작, AI = 새 장애 생성. 문구와 규칙 표시가 다르다. */
  kind: 'mission' | 'scenario'
  title: string
  environmentLabel: string
  /** 레벨이나 난이도. */
  tierLabel?: string
  description: string
  timeLimitSeconds?: number
  baseScore?: number
  hintPenalty?: number
  /** 처음 미션을 시작하는 사용자에게 작업 화면 구성을 미리 알려 준다 (투어 대신). */
  showFirstRunGuide: boolean
  busy: boolean
  error: string | null
  onConfirm: () => void
  onCancel: () => void
}

/**
 * 미션 시작 시트 (FE-27).
 *
 * 예전 확인창은 "선택한 미션을 시작하시겠습니까?" 한 줄뿐이었다. 시작하면 장애가 주입되고
 * 타이머가 바로 돌기 때문에, 무엇이 걸려 있는지(시간·점수 규칙)를 누르기 전에 보여 준다.
 * 시작 요청이 끝날 때까지 시트를 닫지 않고 진행 상태와 실패 이유를 여기서 말한다.
 */
const StartSheet: React.FC<StartSheetProps> = ({
  kind,
  title,
  environmentLabel,
  tierLabel,
  description,
  timeLimitSeconds,
  baseScore,
  hintPenalty,
  showFirstRunGuide,
  busy,
  error,
  onConfirm,
  onCancel,
}) => {
  // 처음 focus 는 제목에 둔다. 확정 버튼에 두면 긴 시트에서 위쪽 규칙·경고가 화면 밖으로 밀린다.
  const titleRef = useRef<HTMLHeadingElement | null>(null)
  const isScenario = kind === 'scenario'

  return (
    <Sheet
      className="start-sheet"
      labelledBy="start-sheet-title"
      describedBy="start-sheet-description"
      initialFocusRef={titleRef}
      onClose={() => {
        // 주입 중에 닫으면 결과를 알릴 곳이 사라진다. 요청이 끝날 때까지 닫지 않는다.
        if (!busy) onCancel()
      }}
    >
      <div className="sheet-chips">
        <span className="ui-chip">{environmentLabel}</span>
        {tierLabel && <span className="ui-chip">{tierLabel}</span>}
      </div>
      <h2 id="start-sheet-title" className="sheet-title" ref={titleRef} tabIndex={-1}>{title}</h2>
      <p id="start-sheet-description" className="sheet-lead">{description}</p>

      <dl className="start-rules">
        {isScenario ? (
          <div className="start-rule wide">
            <dt>시간과 점수</dt>
            <dd>생성된 문제에 따라 정해집니다</dd>
          </div>
        ) : (
          <>
            <div className="start-rule">
              <dt>제한 시간</dt>
              <dd>{timeLimitSeconds ? `${Math.floor(timeLimitSeconds / 60)}분` : '—'}</dd>
            </div>
            <div className="start-rule">
              <dt>기본 점수</dt>
              <dd>{baseScore ?? '—'}점</dd>
            </div>
            <div className="start-rule">
              <dt>힌트 한 단계</dt>
              <dd>{hintPenalty ? `−${hintPenalty}점` : '—'}</dd>
            </div>
          </>
        )}
      </dl>
      <p className="start-rules-note">
        시작부터 {SECONDS_PER_PENALTY_POINT}초마다 1점씩 깎이고, 완료하면 최소 {MIN_COMPLETION_SCORE}점을 받습니다.
        포기하면 0점입니다. 튜터에게 질문하는 것은 감점이 없고, 힌트를 쓸 때마다 튜터의 답이 한 단계씩
        구체적으로 바뀝니다({HINT_LEVELS.map((level) => level.name).join(' → ')}).
      </p>

      <p className="start-notice">
        <AlertIcon />
        <span>
          {isScenario
            ? 'AI가 새 장애를 만들어 내 네임스페이스에 주입합니다. 생성에 몇 초 걸릴 수 있고, 주입이 끝나면 타이머가 시작됩니다.'
            : '시작하면 내 네임스페이스에 장애가 주입되고 타이머가 바로 시작됩니다.'}
        </span>
      </p>

      {showFirstRunGuide && (
        <section className="start-guide" aria-labelledby="start-guide-title">
          <h3 id="start-guide-title">처음이라면 — 작업 화면은 이렇게 생겼습니다</h3>
          <ol>
            <li>
              <strong>위쪽 진행 바</strong>
              <span>남은 시간·점수와 완료 확인 버튼이 있습니다.</span>
            </li>
            <li>
              <strong>터미널</strong>
              <span>명령으로 상태를 조사하고 원인을 고칩니다.</span>
            </li>
            <li>
              <strong>오른쪽 패널</strong>
              <span>브리핑·튜터·관측을 전환합니다. 모바일에서는 아래 탭으로 바꿉니다.</span>
            </li>
          </ol>
        </section>
      )}

      {error && (
        <p className="sheet-error" role="alert">
          {error}
        </p>
      )}

      <div className="sheet-actions">
        <button className="ui-button plain" type="button" onClick={onCancel} disabled={busy}>
          취소
        </button>
        <button className="ui-button primary" type="button" onClick={onConfirm} disabled={busy}>
          {busy
            ? isScenario
              ? 'AI가 장애를 만드는 중...'
              : '장애를 주입하는 중...'
            : isScenario
              ? '장애 생성하고 시작'
              : '장애 주입하고 시작'}
        </button>
      </div>
    </Sheet>
  )
}

export default StartSheet
