import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useEnvironmentSessions } from './useEnvironmentSessions'
import * as api from '../services/api'
import { EnvironmentId, SessionResponse } from '../types/training'

vi.mock('../services/api', () => ({
  createTerminalSession: vi.fn(),
  deleteTerminalSession: vi.fn(),
}))

const mocked = vi.mocked(api)

const sessionFor = (environment: EnvironmentId, id = `session-${environment}`): SessionResponse => ({
  id,
  namespace: 'user-abc',
  environment,
  created_at: '2026-08-29T00:00:00Z',
  is_active: true,
})

/** 해소 시점을 테스트가 직접 잡는 Promise. in-flight 중복 방지를 보려면 필요하다. */
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

beforeEach(() => {
  mocked.createTerminalSession.mockImplementation(async (_token, environment) =>
    sessionFor(environment),
  )
  mocked.deleteTerminalSession.mockResolvedValue(true)
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('useEnvironmentSessions (FE-04)', () => {
  it('선택 전에는 아무 세션도 만들지 않는다', () => {
    const { result } = renderHook(() => useEnvironmentSessions('token'))

    expect(result.current.stateOf('kubernetes')).toEqual({ status: 'idle' })
    expect(mocked.createTerminalSession).not.toHaveBeenCalled()
  })

  it('토큰이 없으면 호출하지 않는다', () => {
    const { result } = renderHook(() => useEnvironmentSessions(null))

    act(() => result.current.ensure('kubernetes'))

    expect(mocked.createTerminalSession).not.toHaveBeenCalled()
    expect(result.current.stateOf('kubernetes')).toEqual({ status: 'idle' })
  })

  it('ensure 하면 loading 을 거쳐 ready 가 되고 세션을 돌려준다', async () => {
    const { result } = renderHook(() => useEnvironmentSessions('token'))

    act(() => result.current.ensure('kubernetes'))
    expect(result.current.stateOf('kubernetes').status).toBe('loading')
    expect(result.current.sessionOf('kubernetes')).toBeNull()

    await waitFor(() => expect(result.current.stateOf('kubernetes').status).toBe('ready'))
    expect(result.current.sessionOf('kubernetes')?.id).toBe('session-kubernetes')
    expect(mocked.createTerminalSession).toHaveBeenCalledWith('token', 'kubernetes')
  })

  it('같은 환경을 진행 중에 다시 ensure 해도 한 번만 만든다', async () => {
    const gate = deferred<SessionResponse>()
    mocked.createTerminalSession.mockReturnValueOnce(gate.promise)
    const { result } = renderHook(() => useEnvironmentSessions('token'))

    act(() => {
      result.current.ensure('kubernetes')
      result.current.ensure('kubernetes')
    })
    act(() => result.current.ensure('kubernetes'))

    expect(mocked.createTerminalSession).toHaveBeenCalledTimes(1)

    await act(async () => {
      gate.resolve(sessionFor('kubernetes'))
      await gate.promise
    })
    await waitFor(() => expect(result.current.stateOf('kubernetes').status).toBe('ready'))

    act(() => result.current.ensure('kubernetes'))
    expect(mocked.createTerminalSession).toHaveBeenCalledTimes(1)
  })

  it('kubernetes → docker → kubernetes 전환에도 각 환경은 한 번만 만들어진다', async () => {
    const { result } = renderHook(() => useEnvironmentSessions('token'))

    act(() => result.current.ensure('kubernetes'))
    await waitFor(() => expect(result.current.stateOf('kubernetes').status).toBe('ready'))

    act(() => result.current.ensure('docker'))
    await waitFor(() => expect(result.current.stateOf('docker').status).toBe('ready'))

    act(() => result.current.ensure('kubernetes'))
    await waitFor(() => expect(result.current.stateOf('kubernetes').status).toBe('ready'))

    expect(mocked.createTerminalSession).toHaveBeenCalledTimes(2)
    expect(result.current.sessionOf('kubernetes')?.environment).toBe('kubernetes')
    expect(result.current.sessionOf('docker')?.environment).toBe('docker')
  })

  it('요청 환경과 다른 세션이 오면 error 로 두고 캐시하지 않는다', async () => {
    mocked.createTerminalSession.mockResolvedValueOnce(sessionFor('docker'))
    const { result } = renderHook(() => useEnvironmentSessions('token'))

    act(() => result.current.ensure('kubernetes'))

    await waitFor(() => expect(result.current.stateOf('kubernetes').status).toBe('error'))
    expect(result.current.sessionOf('kubernetes')).toBeNull()

    // 캐시되지 않았으므로 재시도가 실제 호출로 이어진다.
    act(() => result.current.retry('kubernetes'))
    await waitFor(() => expect(result.current.stateOf('kubernetes').status).toBe('ready'))
    expect(mocked.createTerminalSession).toHaveBeenCalledTimes(2)
  })

  it('실패하면 메시지를 남기고 retry 로 다시 시도할 수 있다', async () => {
    mocked.createTerminalSession.mockRejectedValueOnce(new Error('샌드박스를 준비하지 못했습니다'))
    const { result } = renderHook(() => useEnvironmentSessions('token'))

    act(() => result.current.ensure('kubernetes'))
    await waitFor(() => {
      const state = result.current.stateOf('kubernetes')
      expect(state.status === 'error' && state.message).toBe('샌드박스를 준비하지 못했습니다')
    })

    act(() => result.current.retry('kubernetes'))
    await waitFor(() => expect(result.current.stateOf('kubernetes').status).toBe('ready'))
    expect(mocked.createTerminalSession).toHaveBeenCalledTimes(2)
  })

  it('토큰이 바뀌면 상태를 비우고 이전 요청 응답을 반영하지 않는다', async () => {
    const gate = deferred<SessionResponse>()
    mocked.createTerminalSession.mockReturnValueOnce(gate.promise)
    const { result, rerender } = renderHook(({ token }) => useEnvironmentSessions(token), {
      initialProps: { token: 'token-a' as string | null },
    })

    act(() => result.current.ensure('kubernetes'))
    expect(result.current.stateOf('kubernetes').status).toBe('loading')

    rerender({ token: null })
    expect(result.current.stateOf('kubernetes')).toEqual({ status: 'idle' })

    await act(async () => {
      gate.resolve(sessionFor('kubernetes'))
      await gate.promise
    })

    // 늦게 도착한 응답이 로그아웃된 상태를 되살리면 안 된다.
    expect(result.current.stateOf('kubernetes')).toEqual({ status: 'idle' })
    expect(result.current.sessionOf('kubernetes')).toBeNull()
  })

  it('closeAll 은 만들어 둔 세션을 모두 정리하고 상태를 비운다', async () => {
    const { result } = renderHook(() => useEnvironmentSessions('token'))

    act(() => result.current.ensure('kubernetes'))
    await waitFor(() => expect(result.current.stateOf('kubernetes').status).toBe('ready'))
    act(() => result.current.ensure('docker'))
    await waitFor(() => expect(result.current.stateOf('docker').status).toBe('ready'))

    await act(async () => {
      await result.current.closeAll()
    })

    expect(mocked.deleteTerminalSession).toHaveBeenCalledTimes(2)
    expect(mocked.deleteTerminalSession).toHaveBeenCalledWith('token', 'session-kubernetes')
    expect(mocked.deleteTerminalSession).toHaveBeenCalledWith('token', 'session-docker')
    expect(result.current.stateOf('kubernetes')).toEqual({ status: 'idle' })
    expect(result.current.stateOf('docker')).toEqual({ status: 'idle' })
  })

  it('세션 종료가 실패해도 closeAll 은 예외를 올리지 않는다', async () => {
    mocked.deleteTerminalSession.mockRejectedValue(new Error('offline'))
    const { result } = renderHook(() => useEnvironmentSessions('token'))

    act(() => result.current.ensure('kubernetes'))
    await waitFor(() => expect(result.current.stateOf('kubernetes').status).toBe('ready'))

    await act(async () => {
      await expect(result.current.closeAll()).resolves.toBeUndefined()
    })
  })

  it('만든 세션이 없으면 종료 API 를 부르지 않는다', async () => {
    const { result } = renderHook(() => useEnvironmentSessions('token'))

    await act(async () => {
      await result.current.closeAll()
    })

    expect(mocked.deleteTerminalSession).not.toHaveBeenCalled()
  })
})
