import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ConfirmModal from './ConfirmModal'
import Toast from './Toast'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ConfirmModal 접근성 (FE-17)', () => {
  const renderModal = (overrides: Partial<React.ComponentProps<typeof ConfirmModal>> = {}) => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    const view = render(
      <ConfirmModal
        title="미션 포기"
        message="진행 중인 미션을 포기하시겠습니까?"
        confirmLabel="포기"
        onConfirm={onConfirm}
        onCancel={onCancel}
        {...overrides}
      />,
    )
    return { onConfirm, onCancel, view }
  }

  it('dialog 로 표시되고 제목·본문이 연결된다', () => {
    renderModal()
    const dialog = screen.getByRole('dialog')

    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(dialog.getAttribute('aria-labelledby')).toBe('confirm-modal-title')
    expect(dialog.getAttribute('aria-describedby')).toBe('confirm-modal-message')
    expect(screen.getByText('미션 포기')).toBeTruthy()
  })

  it('열리면 확인 버튼에 focus 가 간다', () => {
    renderModal()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '포기' }))
  })

  it('Escape 로 닫힌다', () => {
    const { onCancel } = renderModal()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('Tab 이 모달 밖으로 나가지 않는다 (focus trap)', () => {
    // 모달 뒤에 있어야 할 요소. trap 이 없으면 여기로 focus 가 빠진다.
    const outside = document.createElement('button')
    outside.textContent = '뒤에 있는 버튼'
    document.body.appendChild(outside)

    renderModal()
    const confirm = screen.getByRole('button', { name: '포기' })
    const cancel = screen.getByRole('button', { name: '취소' })

    // 마지막 요소(확인)에서 Tab → 첫 요소(취소)로 돌아온다.
    expect(document.activeElement).toBe(confirm)
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(cancel)

    // 첫 요소에서 Shift+Tab → 마지막 요소로 돌아온다.
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(confirm)
    expect(document.activeElement).not.toBe(outside)

    document.body.removeChild(outside)
  })

  it('닫힌 뒤 원래 버튼으로 focus 가 돌아온다', () => {
    const opener = document.createElement('button')
    opener.textContent = '미션 포기'
    document.body.appendChild(opener)
    opener.focus()
    expect(document.activeElement).toBe(opener)

    const { view } = renderModal()
    expect(document.activeElement).not.toBe(opener)

    view.unmount()
    expect(document.activeElement).toBe(opener)

    document.body.removeChild(opener)
  })

  it('backdrop 을 눌러도 닫히고, 모달 본문 클릭은 닫지 않는다', () => {
    const { onCancel } = renderModal()

    fireEvent.mouseDown(screen.getByRole('dialog'))
    expect(onCancel).not.toHaveBeenCalled()

    const backdrop = document.querySelector('.modal-backdrop') as HTMLElement
    fireEvent.mouseDown(backdrop)
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})

describe('Toast live region (FE-17)', () => {
  it('오류는 alert 으로 즉시 읽힌다', () => {
    render(<Toast kind="error" text="미션 확인에 실패했습니다." onClose={vi.fn()} />)
    const toast = screen.getByRole('alert')

    expect(toast.getAttribute('aria-live')).toBe('assertive')
    expect(toast.textContent).toContain('미션 확인에 실패했습니다.')
  })

  it('성공·정보는 status 로 부드럽게 읽힌다', () => {
    const { rerender } = render(<Toast kind="success" text="완료" onClose={vi.fn()} />)
    expect(screen.getByRole('status').getAttribute('aria-live')).toBe('polite')

    rerender(<Toast kind="info" text="안내" onClose={vi.fn()} />)
    expect(screen.getByRole('status').getAttribute('aria-live')).toBe('polite')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('닫기 버튼에 접근 가능한 이름이 있다', () => {
    const onClose = vi.fn()
    render(<Toast kind="info" text="안내" onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: '알림 닫기' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
