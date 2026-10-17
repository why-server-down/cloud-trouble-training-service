import { describe, expect, it } from 'vitest'

import {
  deleteBackward,
  deleteForward,
  deleteToStart,
  deleteWordBackward,
  insertText,
  moveEnd,
  moveHome,
  moveLeft,
  moveRight,
  replaceLine,
  textWidth,
} from './lineEditor'

/** xterm 대신 한 줄짜리 화면을 흉내 낸다 — 출력이 줄과 커서를 정말 그렇게 그리는지 본다. */
const render = (screen: { cells: string[]; col: number }, output: string) => {
  for (const char of output) {
    if (char === '\b') screen.col = Math.max(0, screen.col - 1)
    else {
      // 한글은 xterm 처럼 두 칸을 차지한다 (뒤 칸은 빈 자리).
      const width = textWidth(char)
      screen.cells[screen.col] = char
      if (width === 2) screen.cells[screen.col + 1] = ''
      screen.col += width
    }
  }
  return screen
}

const apply = (initial: string, ...steps: Array<(state: { line: string; cursor: number }) => { line: string; cursor: number; output: string }>) => {
  let state = { line: initial, cursor: initial.length }
  const screen = render({ cells: [], col: 0 }, initial)
  for (const step of steps) {
    const result = step(state)
    render(screen, result.output)
    state = { line: result.line, cursor: result.cursor }
  }
  return { state, shown: screen.cells.join('').trimEnd(), col: screen.col }
}

describe('터미널 입력줄 편집 (FE-28)', () => {
  it('← 두 번 뒤 글자를 넣으면 줄 끝이 아니라 커서 위치에 들어간다', () => {
    const { state, shown, col } = apply('kubectl get pod', moveLeft, moveLeft, (s) => insertText(s, 'X'))
    expect(state.line).toBe('kubectl get pXod')
    expect(shown).toBe('kubectl get pXod')
    expect(col).toBe(state.cursor)
  })

  it('Backspace 는 커서 앞 글자를 지우고 뒤를 당긴다', () => {
    const { state, shown } = apply('kubectl gett pods', moveHome, ...Array(12).fill(moveRight), deleteBackward)
    expect(state.line).toBe('kubectl get pods')
    expect(shown).toBe('kubectl get pods')
  })

  it('Delete 는 커서 위치 글자를 지운다', () => {
    const { state, shown } = apply('kubectl  get', moveHome, ...Array(7).fill(moveRight), deleteForward)
    expect(state.line).toBe('kubectl get')
    expect(shown).toBe('kubectl get')
  })

  it('Home·End 로 줄 처음과 끝으로 간다', () => {
    const home = apply('docker ps', moveHome)
    expect(home.state.cursor).toBe(0)
    expect(home.col).toBe(0)
    const end = apply('docker ps', moveHome, moveEnd)
    expect(end.col).toBe('docker ps'.length)
  })

  it('Ctrl+U 는 커서 앞을, Ctrl+W 는 앞 단어를 지운다', () => {
    expect(apply('kubectl get pods', deleteWordBackward).state.line).toBe('kubectl get ')
    expect(apply('kubectl get pods', moveLeft, moveLeft, moveLeft, moveLeft, deleteToStart).state.line).toBe('pods')
  })

  it('한글은 두 칸으로 계산해 커서가 어긋나지 않는다', () => {
    expect(textWidth('ps 한글')).toBe(7)
    const { state, col } = apply('ps 한', moveLeft)
    expect(state.cursor).toBe(3)
    // 한 글자 왼쪽 = 두 칸 왼쪽. 커서가 '한'의 앞(3번째 칸)에 선다.
    expect(col).toBe(3)
    const inserted = apply('ps 한', moveLeft, (s) => insertText(s, 'x'))
    expect(inserted.state.line).toBe('ps x한')
    expect(inserted.shown).toBe('ps x한')
  })

  it('명령 이력으로 바꾸면 이전 줄을 지우고 새 줄 끝에 커서를 둔다', () => {
    const { state, shown } = apply('kubectl get services', moveHome, (s) => replaceLine(s, 'docker ps'))
    expect(state).toEqual({ line: 'docker ps', cursor: 9 })
    expect(shown).toBe('docker ps')
  })
})
