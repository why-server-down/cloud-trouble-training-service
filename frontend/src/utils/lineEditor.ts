/**
 * 터미널 입력줄 편집 (FE-28).
 *
 * 서버는 한 줄 명령만 받으므로 입력줄은 브라우저가 편집한다. 예전에는 끝에 붙이기와
 * 지우기만 돼서 ←로 오타를 고칠 수 없었다(교차 리뷰 P1). 여기서는 키 하나를 받아
 * 새 줄·커서와 xterm 에 쓸 출력을 돌려주는 순수 함수만 둔다 — 화면 없이 테스트한다.
 *
 * 왼쪽 이동은 커서 이동(CSI D) 대신 `\b` 를 쓴다. 긴 명령이 줄바꿈된 상태에서 CSI D 는
 * 윗줄로 넘어가지 못하지만, reverse wraparound(DECSET 45)를 켠 `\b` 는 넘어간다.
 * 오른쪽 이동은 커서 아래 글자를 다시 써서 자연스럽게 줄을 넘긴다.
 *
 * 알려진 제한: 두 칸짜리 글자(한글)가 줄 끝 한 칸에 들어가지 못해 다음 줄로 넘어간 경우,
 * 그 빈 칸을 세지 않아 지운 뒤 커서가 한 칸 어긋날 수 있다. 명령은 대부분 ASCII 라 두었다.
 */

export interface LineState {
  line: string
  cursor: number
}

export interface EditResult extends LineState {
  /** xterm 에 쓸 문자열. 비어 있으면 아무것도 쓰지 않는다. */
  output: string
}

/** 한글·한자처럼 터미널에서 두 칸을 차지하는 글자. xterm 의 기본 폭 규칙과 맞춘다. */
const isWide = (char: string) => {
  const code = char.codePointAt(0) ?? 0
  return (
    (code >= 0x1100 && code <= 0x115f)
    || (code >= 0x2e80 && code <= 0xa4cf)
    || (code >= 0xac00 && code <= 0xd7a3)
    || (code >= 0xf900 && code <= 0xfaff)
    || (code >= 0xfe30 && code <= 0xfe4f)
    || (code >= 0xff00 && code <= 0xff60)
    || (code >= 0xffe0 && code <= 0xffe6)
  )
}

export const textWidth = (text: string) => Array.from(text).reduce((sum, char) => sum + (isWide(char) ? 2 : 1), 0)

const back = (columns: number) => '\b'.repeat(columns)

/** 커서 위치에 글자를 넣는다. 뒤에 있던 글자는 다시 그리고 커서를 제자리로 돌린다. */
export const insertText = ({ line, cursor }: LineState, text: string): EditResult => {
  const rest = line.slice(cursor)
  return {
    line: line.slice(0, cursor) + text + rest,
    cursor: cursor + text.length,
    output: text + rest + back(textWidth(rest)),
  }
}

/** 커서 앞 글자 하나를 지운다 (Backspace). */
export const deleteBackward = ({ line, cursor }: LineState): EditResult => {
  if (cursor === 0) return { line, cursor, output: '' }
  const removed = line.slice(cursor - 1, cursor)
  const rest = line.slice(cursor)
  const width = textWidth(removed)
  return {
    line: line.slice(0, cursor - 1) + rest,
    cursor: cursor - 1,
    output: back(width) + rest + ' '.repeat(width) + back(textWidth(rest) + width),
  }
}

/** 커서 위치의 글자를 지운다 (Delete). */
export const deleteForward = ({ line, cursor }: LineState): EditResult => {
  if (cursor >= line.length) return { line, cursor, output: '' }
  const removed = line.slice(cursor, cursor + 1)
  const rest = line.slice(cursor + 1)
  const width = textWidth(removed)
  return {
    line: line.slice(0, cursor) + rest,
    cursor,
    output: rest + ' '.repeat(width) + back(textWidth(rest) + width),
  }
}

export const moveLeft = ({ line, cursor }: LineState): EditResult =>
  cursor === 0
    ? { line, cursor, output: '' }
    : { line, cursor: cursor - 1, output: back(textWidth(line.slice(cursor - 1, cursor))) }

export const moveRight = ({ line, cursor }: LineState): EditResult =>
  cursor >= line.length
    ? { line, cursor, output: '' }
    : { line, cursor: cursor + 1, output: line.slice(cursor, cursor + 1) }

/** 줄 처음으로 (Home, Ctrl+A). */
export const moveHome = ({ line, cursor }: LineState): EditResult => ({
  line,
  cursor: 0,
  output: back(textWidth(line.slice(0, cursor))),
})

/** 줄 끝으로 (End, Ctrl+E). */
export const moveEnd = ({ line, cursor }: LineState): EditResult => ({
  line,
  cursor: line.length,
  output: line.slice(cursor),
})

/** 커서 앞을 지운다 (Ctrl+U). */
export const deleteToStart = ({ line, cursor }: LineState): EditResult => {
  if (cursor === 0) return { line, cursor, output: '' }
  const removedWidth = textWidth(line.slice(0, cursor))
  const rest = line.slice(cursor)
  return {
    line: rest,
    cursor: 0,
    output: back(removedWidth) + rest + ' '.repeat(removedWidth) + back(textWidth(rest) + removedWidth),
  }
}

/** 커서 앞 단어 하나를 지운다 (Ctrl+W). 앞쪽 공백과 단어를 함께 지운다. */
export const deleteWordBackward = ({ line, cursor }: LineState): EditResult => {
  const before = line.slice(0, cursor)
  const start = before.replace(/\S+\s*$/, '').length
  if (start === cursor) {
    // 커서 앞이 공백뿐이면 그 공백과 앞 단어를 지운다.
    const trimmed = before.replace(/\s+$/, '')
    const wordStart = trimmed.replace(/\S+$/, '').length
    if (wordStart === cursor) return { line, cursor, output: '' }
    return removeRange({ line, cursor }, wordStart)
  }
  return removeRange({ line, cursor }, start)
}

const removeRange = ({ line, cursor }: LineState, start: number): EditResult => {
  const removedWidth = textWidth(line.slice(start, cursor))
  const rest = line.slice(cursor)
  return {
    line: line.slice(0, start) + rest,
    cursor: start,
    output: back(removedWidth) + rest + ' '.repeat(removedWidth) + back(textWidth(rest) + removedWidth),
  }
}

/** 지금 줄을 화면에서 지우고 다른 줄로 바꾼다 (명령 이력 ↑/↓). */
export const replaceLine = ({ line, cursor }: LineState, next: string): EditResult => {
  const toEnd = line.slice(cursor)
  const width = textWidth(line)
  return {
    line: next,
    cursor: next.length,
    output: toEnd + back(width) + ' '.repeat(width) + back(width) + next,
  }
}
