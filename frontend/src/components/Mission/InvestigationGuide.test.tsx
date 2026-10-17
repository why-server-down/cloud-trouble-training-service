import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import InvestigationGuide from './InvestigationGuide'
import { insertTerminalCommand, TERMINAL_INSERT_EVENT } from '../../utils/terminal'

afterEach(() => cleanup())

describe('조사 가이드 (FE-26)', () => {
  it('미션 중에는 조사 명령을 눌러 입력줄에 넣는다 — 실행하지 않는다', () => {
    const onInsert = vi.fn()
    render(<InvestigationGuide environment="kubernetes" active onInsertCommand={onInsert} />)

    fireEvent.click(screen.getByRole('button', { name: /kubectl get pods — 터미널 입력줄에 넣기/ }))
    expect(onInsert).toHaveBeenCalledWith('kubectl get pods')
    // 첫 단계(미션 선택)는 끝난 것으로 읽힌다.
    expect(screen.getByText('(완료)')).toBeTruthy()
  })

  it('미션 전에는 명령을 보여주기만 하고 버튼을 두지 않는다', () => {
    render(<InvestigationGuide environment="docker" />)

    expect(screen.getByText((_, node) => node?.tagName === 'CODE' && node.textContent === 'docker ps -a')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.queryByText('(완료)')).toBeNull()
  })

  it('명령은 띄어쓰기에서만 줄이 바뀌도록 단어를 묶는다', () => {
    render(<InvestigationGuide environment="kubernetes" />)

    // 하이픈이 든 옵션도 한 덩어리다. '--sort-' 에서 끊기지 않는다.
    const word = screen.getByText('--sort-by=.metadata.creationTimestamp')
    expect(word.className).toBe('command-word')
    expect(word.closest('code')?.textContent).toBe('kubectl get events --sort-by=.metadata.creationTimestamp')
  })

  it('터미널 입력 신호는 명령을 그대로 실어 보낸다', () => {
    const received: unknown[] = []
    const listener = (event: Event) => received.push((event as CustomEvent).detail)
    window.addEventListener(TERMINAL_INSERT_EVENT, listener)

    insertTerminalCommand('kubectl get events')
    window.removeEventListener(TERMINAL_INSERT_EVENT, listener)

    expect(received).toEqual(['kubectl get events'])
  })
})
