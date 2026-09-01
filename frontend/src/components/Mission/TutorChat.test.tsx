import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import TutorChat from './TutorChat'
import * as api from '../../services/api'
import { getSafeSourceHref } from '../../utils/tutorSources'

vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof api>()
  return { ...actual, askTutor: vi.fn() }
})

const mocked = vi.mocked(api)

const answer = (overrides: Partial<api.ChatResponse> = {}): api.ChatResponse => ({
  response: '먼저 컨테이너 상태를 확인하세요.',
  hint_level: 0,
  mission_name: 'test',
  ...overrides,
})

beforeEach(() => {
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
  mocked.askTutor.mockResolvedValue(answer())
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
})

const renderChat = (props: Partial<React.ComponentProps<typeof TutorChat>> = {}) =>
  render(
    <TutorChat
      token="t"
      missionId="mission-1"
      environment="docker"
      hintsUsed={0}
      {...props}
    />,
  )

const askOnce = async (question = '어디를 봐야 하나요') => {
  fireEvent.change(screen.getByRole('textbox'), { target: { value: question } })
  fireEvent.click(screen.getByRole('button', { name: '질문' }))
}

describe('환경 인지형 튜터 표시 (FE-11)', () => {
  it('활성 attempt 의 환경 배지를 보여준다', () => {
    renderChat({ environment: 'docker' })
    expect(screen.getByText('Docker')).toBeTruthy()
    expect(screen.queryByText('Kubernetes')).toBeNull()
  })

  it('Kubernetes attempt 에 Docker 배지가 붙지 않는다', () => {
    renderChat({ environment: 'kubernetes' })
    expect(screen.getByText('Kubernetes')).toBeTruthy()
    expect(screen.queryByText('Docker')).toBeNull()
  })

  it('답변의 관측 정보와 참고 자료를 접기 영역으로 보여준다', async () => {
    mocked.askTutor.mockResolvedValue(
      answer({
        observations_used: ['container_status', 'restart_count'],
        sources: [{ title: 'Docker 네트워크 진단', path: 'kb/docker/network.md' }],
      }),
    )
    renderChat()
    await askOnce()

    expect(await screen.findByText('사용한 관측 정보 2건')).toBeTruthy()
    expect(screen.getByText('참고 자료 1건')).toBeTruthy()
    expect(screen.getByText('container_status')).toBeTruthy()
  })

  it('sources 가 없어도 접기 영역을 그리지 않고 답변만 보여준다', async () => {
    renderChat()
    await askOnce()

    expect(await screen.findByText(/컨테이너 상태를 확인/)).toBeTruthy()
    expect(screen.queryByText(/참고 자료/)).toBeNull()
    expect(screen.queryByText(/사용한 관측 정보/)).toBeNull()
  })

  it('내부 경로는 링크로 만들지 않는다', async () => {
    mocked.askTutor.mockResolvedValue(
      answer({ sources: [{ title: '내부 문서', path: 'kb/docker/network.md' }] }),
    )
    renderChat()
    await askOnce()

    fireEvent.click(await screen.findByText('참고 자료 1건'))
    expect(screen.queryByRole('link', { name: '내부 문서' })).toBeNull()
    expect(screen.getByText('kb/docker/network.md')).toBeTruthy()
  })

  it('fallback 응답이면 관측이 반영되지 않았음을 알린다', async () => {
    mocked.askTutor.mockResolvedValue(answer({ fallback_used: true }))
    renderChat()
    await askOnce()

    expect(await screen.findByText(/준비된 안내로 대체했습니다/)).toBeTruthy()
  })

  it('환경이 바뀌면 이전 답변이 새 대화에 남지 않는다', async () => {
    const { rerender } = renderChat({ environment: 'docker' })
    await askOnce()
    await screen.findByText(/컨테이너 상태를 확인/)

    rerender(<TutorChat token="t" missionId="mission-1" environment="linux" hintsUsed={0} />)

    expect(screen.queryByText(/컨테이너 상태를 확인/)).toBeNull()
    expect(screen.getByText('Linux')).toBeTruthy()
  })

  it('오류가 나면 질문을 버리지 않고 재전송 버튼을 준다', async () => {
    mocked.askTutor.mockRejectedValue(new Error('서버 오류'))
    renderChat()
    await askOnce('왜 죽었나요')

    const retry = await screen.findByRole('button', { name: '다시 질문' })
    expect(screen.getByText('서버 오류')).toBeTruthy()

    mocked.askTutor.mockResolvedValue(answer())
    fireEvent.click(retry)

    expect(await screen.findByText(/컨테이너 상태를 확인/)).toBeTruthy()
    expect(mocked.askTutor).toHaveBeenCalledTimes(2)
  })

  it('입력에 접근 가능한 label 이 있다', () => {
    renderChat()
    expect(screen.getByLabelText(/훈련 질문/)).toBeTruthy()
  })
})

describe('AI 응답 시간과 사용자 피드백 (FE-12)', () => {
  it('질문 1회에 chat API 가 정확히 1회 호출된다', async () => {
    let resolveAsk!: (value: api.ChatResponse) => void
    mocked.askTutor.mockReturnValue(
      new Promise<api.ChatResponse>((resolve) => {
        resolveAsk = resolve
      }),
    )
    renderChat()
    await askOnce()

    // 응답 대기 중 재제출 시도 — 버튼이 잠겨 있어야 한다.
    fireEvent.click(screen.getByRole('button', { name: '질문' }))
    expect(mocked.askTutor).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveAsk(answer())
    })
    expect(mocked.askTutor).toHaveBeenCalledTimes(1)
  })

  it('전송 즉시 사용자 메시지와 typing indicator 를 보여준다', async () => {
    mocked.askTutor.mockReturnValue(new Promise(() => {}))
    renderChat()
    await askOnce('디스크가 꽉 찼어요')

    expect(await screen.findByText('디스크가 꽉 찼어요')).toBeTruthy()
    expect(screen.getByText('답변을 준비하고 있습니다...')).toBeTruthy()
  })

  it('1.5초가 지나면 무엇을 하고 있는지 알린다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mocked.askTutor.mockReturnValue(new Promise(() => {}))
    renderChat({ environment: 'linux' })
    await askOnce()

    await act(async () => {
      vi.advanceTimersByTime(1600)
    })
    expect(screen.getByText(/Linux 환경 상태와 관련 문서를 분석 중/)).toBeTruthy()
    // 자동 실패 처리하지 않는다 — 아직 취소 버튼도 없다.
    expect(screen.queryByRole('button', { name: '취소' })).toBeNull()
  })

  it('15초 이후에는 취소 버튼을 주고, 취소한 응답은 목록에 붙지 않는다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let resolveAsk!: (value: api.ChatResponse) => void
    mocked.askTutor.mockImplementation(
      (_token, _message, _hint, signal) =>
        new Promise<api.ChatResponse>((resolve, reject) => {
          resolveAsk = resolve
          signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )
    renderChat()
    await askOnce()

    await act(async () => {
      vi.advanceTimersByTime(15100)
    })
    const cancel = screen.getByRole('button', { name: '취소' })
    fireEvent.click(cancel)

    expect(await screen.findByText(/질문을 취소했습니다/)).toBeTruthy()

    // 취소 뒤 늦게 도착한 응답이 목록에 들어가면 안 된다.
    await act(async () => {
      resolveAsk(answer())
    })
    expect(screen.queryByText(/컨테이너 상태를 확인/)).toBeNull()
  })

  it('취소한 뒤 다시 질문할 수 있다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mocked.askTutor.mockImplementation(
      (_token, _message, _hint, signal) =>
        new Promise<api.ChatResponse>((_resolve, reject) => {
          signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )
    renderChat()
    await askOnce()

    await act(async () => {
      vi.advanceTimersByTime(15100)
    })
    fireEvent.click(screen.getByRole('button', { name: '취소' }))

    mocked.askTutor.mockResolvedValue(answer())
    await waitFor(() => expect(screen.getByRole('textbox')).not.toHaveProperty('disabled', true))
    await askOnce('다시 물어봅니다')

    expect(await screen.findByText(/컨테이너 상태를 확인/)).toBeTruthy()
  })
})

describe('근거 링크 안전성 (FE-11)', () => {
  it('http/https 절대 URL 만 링크로 허용한다', () => {
    expect(getSafeSourceHref('https://docs.docker.com/network/')).toBe(
      'https://docs.docker.com/network/',
    )
    expect(getSafeSourceHref('http://example.com/a')).toBe('http://example.com/a')
  })

  it('내부 경로와 위험한 스킴은 링크로 만들지 않는다', () => {
    expect(getSafeSourceHref('kb/docker/network.md')).toBeNull()
    expect(getSafeSourceHref('/kb/docker/network.md')).toBeNull()
    expect(getSafeSourceHref('javascript:alert(1)')).toBeNull()
    expect(getSafeSourceHref('data:text/plain,hello')).toBeNull()
    expect(getSafeSourceHref(null)).toBeNull()
    expect(getSafeSourceHref(undefined)).toBeNull()
    expect(getSafeSourceHref('')).toBeNull()
  })
})
