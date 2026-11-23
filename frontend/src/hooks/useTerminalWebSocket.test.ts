import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useTerminalWebSocket } from './useTerminalWebSocket'
import { AUTH_EXPIRED_EVENT } from '../services/api'
import { EnvironmentId } from '../types/training'

/**
 * xterm 대신 쓰는 최소 터미널. 이 훅은 write 만 부른다.
 * 실제 xterm 은 canvas 를 잡아 jsdom 에서 켜기 어렵다.
 */
const fakeTerminal = () => {
  const written: string[] = []
  return {
    written,
    terminal: { write: (data: string) => written.push(data) } as never,
  }
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static readonly OPEN = 1
  static readonly CONNECTING = 0

  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  readyState = FakeWebSocket.CONNECTING
  sent: string[] = []
  closed = false

  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
  }

  send(payload: string) {
    this.sent.push(payload)
  }

  close() {
    this.closed = true
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  serverClose(code = 1006) {
    this.readyState = 3
    this.onclose?.({ code })
  }
}

const renderSocket = (environment: EnvironmentId = 'kubernetes', sessionId = 'session-1') => {
  const { terminal, written } = fakeTerminal()
  const view = renderHook(
    (props: { environment: EnvironmentId; sessionId: string }) =>
      useTerminalWebSocket({
        environment: props.environment,
        sessionId: props.sessionId,
        token: 'test-token',
        terminal,
        namespace: 'user-abc',
      }),
    { initialProps: { environment, sessionId } },
  )
  return { ...view, written }
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useTerminalWebSocket 환경 전환 (FE-07)', () => {
  it('세션이 바뀌면 이전 소켓을 닫고 새로 연결한다', () => {
    const { rerender } = renderSocket('kubernetes', 'session-kubernetes')
    expect(FakeWebSocket.instances).toHaveLength(1)

    rerender({ environment: 'docker', sessionId: 'session-docker' })

    expect(FakeWebSocket.instances[0].closed).toBe(true)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(FakeWebSocket.instances[1].url).toContain('session-docker')
  })

  it('연결되지 않은 상태에서는 명령을 보내지 않는다', () => {
    const { result } = renderSocket()

    act(() => {
      expect(result.current.sendCommand('kubectl get pods')).toBe(false)
    })

    expect(FakeWebSocket.instances[0].sent).toHaveLength(0)
  })

  it('연결되면 명령을 그대로 보낸다', () => {
    const { result } = renderSocket()

    act(() => FakeWebSocket.instances[0].open())
    expect(result.current.isConnected).toBe(true)

    act(() => {
      result.current.sendCommand('docker ps')
    })

    expect(JSON.parse(FakeWebSocket.instances[0].sent[0])).toEqual({
      type: 'command',
      command: 'docker ps',
    })
  })

  it('출력 프롬프트에 현재 환경이 드러난다', () => {
    const { written } = renderSocket('docker', 'session-docker')

    act(() => {
      FakeWebSocket.instances[0].open()
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({ type: 'output', data: 'CONTAINER ID' }),
      })
    })

    expect(written.join('')).toContain('[docker:user-abc]$ ')
  })
})

describe('재연결 상한 (FE-07 회귀)', () => {
  /** 서버가 끊고 재연결 타이머가 만료되는 한 사이클. */
  const failOnce = () => {
    act(() => {
      FakeWebSocket.instances[FakeWebSocket.instances.length - 1].serverClose()
    })
    act(() => {
      vi.advanceTimersByTime(2000)
    })
  }

  it('3회까지만 재연결하고 그 뒤에는 새 소켓을 만들지 않는다', () => {
    const { result } = renderSocket()
    expect(FakeWebSocket.instances).toHaveLength(1)

    failOnce()
    failOnce()
    failOnce()
    expect(FakeWebSocket.instances).toHaveLength(4)

    // 4번째 끊김은 재시도하지 않는다. 여기서 카운터가 초기화되면 무한 재연결이 된다.
    failOnce()
    expect(FakeWebSocket.instances).toHaveLength(4)
    expect(result.current.error).toContain('재연결에 실패')
  })

  it('연결에 성공하면 재시도 횟수가 다시 채워진다', () => {
    renderSocket()

    failOnce()
    failOnce()
    act(() => FakeWebSocket.instances[FakeWebSocket.instances.length - 1].open())

    failOnce()
    failOnce()
    failOnce()
    // 성공 후 3회를 다시 쓸 수 있어야 한다.
    expect(FakeWebSocket.instances).toHaveLength(6)
  })

  it('환경을 바꾸면 재시도 횟수가 새로 시작된다', () => {
    const { rerender } = renderSocket('kubernetes', 'session-kubernetes')

    failOnce()
    failOnce()
    failOnce()
    failOnce()
    const exhausted = FakeWebSocket.instances.length

    rerender({ environment: 'docker', sessionId: 'session-docker' })
    expect(FakeWebSocket.instances).toHaveLength(exhausted + 1)

    failOnce()
    expect(FakeWebSocket.instances).toHaveLength(exhausted + 2)
  })

  it('인증 만료(4001)는 재연결하지 않고 만료 이벤트를 올린다', () => {
    const onExpired = vi.fn()
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired)
    const { result } = renderSocket()

    act(() => FakeWebSocket.instances[0].serverClose(4001))
    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(onExpired).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(result.current.error).toContain('인증이 만료')
    window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired)
  })
})
