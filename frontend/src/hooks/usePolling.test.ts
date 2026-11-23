import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PollResult, usePolling } from './usePolling'

const setVisibility = (state: 'visible' | 'hidden') => {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

beforeEach(() => {
  vi.useFakeTimers()
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
})

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

/** 대기 중인 마이크로태스크를 비운 뒤 타이머를 진행시킨다. */
const advance = async (ms: number) => {
  await act(async () => {
    await Promise.resolve()
    vi.advanceTimersByTime(ms)
    await Promise.resolve()
  })
}

describe('usePolling (FE-16)', () => {
  it('마운트 즉시 한 번 실행한다', async () => {
    const task = vi.fn<() => Promise<PollResult>>().mockResolvedValue('continue')
    renderHook(() => usePolling(task, { intervalMs: 5000, hiddenIntervalMs: 15000 }))

    await act(async () => {
      await Promise.resolve()
    })
    expect(task).toHaveBeenCalledTimes(1)
  })

  it('보이는 동안에는 intervalMs 간격으로 실행한다', async () => {
    const task = vi.fn<() => Promise<PollResult>>().mockResolvedValue('continue')
    renderHook(() => usePolling(task, { intervalMs: 5000, hiddenIntervalMs: 15000 }))

    await advance(5000)
    expect(task).toHaveBeenCalledTimes(2)
    await advance(5000)
    expect(task).toHaveBeenCalledTimes(3)
  })

  it('탭이 숨으면 hiddenIntervalMs 로 늘린다', async () => {
    const task = vi.fn<() => Promise<PollResult>>().mockResolvedValue('continue')
    renderHook(() => usePolling(task, { intervalMs: 5000, hiddenIntervalMs: 15000 }))

    await advance(5000)
    expect(task).toHaveBeenCalledTimes(2)

    await act(async () => {
      setVisibility('hidden')
      await Promise.resolve()
    })

    // 숨는 즉시 다음 주기가 15초로 다시 잡힌다 — 한 주기 늦게 적용되지 않는다.
    const afterHidden = task.mock.calls.length
    await advance(14999)
    expect(task.mock.calls.length).toBe(afterHidden)
    await advance(2)
    expect(task.mock.calls.length).toBe(afterHidden + 1)
  })

  it('탭으로 돌아오면 다음 주기를 기다리지 않고 즉시 갱신한다', async () => {
    const task = vi.fn<() => Promise<PollResult>>().mockResolvedValue('continue')
    renderHook(() => usePolling(task, { intervalMs: 5000, hiddenIntervalMs: 15000 }))

    await act(async () => {
      await Promise.resolve()
    })
    const before = task.mock.calls.length

    await act(async () => {
      setVisibility('hidden')
      await Promise.resolve()
      setVisibility('visible')
      await Promise.resolve()
    })

    expect(task.mock.calls.length).toBe(before + 1)
  })

  it("'stop' 을 받으면 더 이상 실행하지 않는다", async () => {
    const task = vi.fn<() => Promise<PollResult>>().mockResolvedValue('stop')
    renderHook(() => usePolling(task, { intervalMs: 5000, hiddenIntervalMs: 15000 }))

    await advance(60000)
    expect(task).toHaveBeenCalledTimes(1)
  })

  it('연속 실패는 간격을 두 배씩 늘리고 상한을 넘지 않는다', async () => {
    const task = vi.fn<() => Promise<PollResult>>().mockRejectedValue(new Error('offline'))
    renderHook(() =>
      usePolling(task, { intervalMs: 1000, hiddenIntervalMs: 15000, maxBackoffMs: 4000 }),
    )

    await act(async () => {
      await Promise.resolve()
    })
    expect(task).toHaveBeenCalledTimes(1)

    // 1회 실패 → 2000ms
    await advance(1999)
    expect(task).toHaveBeenCalledTimes(1)
    await advance(2)
    expect(task).toHaveBeenCalledTimes(2)

    // 2회 실패 → 4000ms
    await advance(3999)
    expect(task).toHaveBeenCalledTimes(2)
    await advance(2)
    expect(task).toHaveBeenCalledTimes(3)

    // 3회 실패 → 8000ms 이지만 상한 4000ms 로 잘린다
    await advance(3999)
    expect(task).toHaveBeenCalledTimes(3)
    await advance(2)
    expect(task).toHaveBeenCalledTimes(4)
  })

  it('성공하면 backoff 가 초기화된다', async () => {
    const task = vi
      .fn<() => Promise<PollResult>>()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue('continue')
    renderHook(() => usePolling(task, { intervalMs: 1000, hiddenIntervalMs: 15000 }))

    await act(async () => {
      await Promise.resolve()
    })
    // 실패 후 2000ms
    await advance(2001)
    expect(task).toHaveBeenCalledTimes(2)

    // 성공했으므로 다시 1000ms 간격
    await advance(1001)
    expect(task).toHaveBeenCalledTimes(3)
  })

  it('네트워크가 복구되면 새로고침 없이 조회가 재개된다', async () => {
    let online = false
    const task = vi.fn<() => Promise<PollResult>>().mockImplementation(async () => {
      if (!online) throw new Error('offline')
      return 'continue'
    })
    renderHook(() => usePolling(task, { intervalMs: 1000, hiddenIntervalMs: 15000, maxBackoffMs: 4000 }))

    await advance(20000)
    const duringOutage = task.mock.calls.length
    expect(duringOutage).toBeGreaterThan(1)

    online = true
    await advance(4001)
    expect(task.mock.calls.length).toBeGreaterThan(duringOutage)

    // 복구 후에는 다시 1초 간격으로 돌아온다.
    const afterRecovery = task.mock.calls.length
    await advance(1001)
    expect(task.mock.calls.length).toBe(afterRecovery + 1)
  })

  it('응답이 간격보다 오래 걸려도 호출이 겹치지 않는다', async () => {
    let resolveTask: ((value: PollResult) => void) | null = null
    const task = vi.fn<() => Promise<PollResult>>().mockImplementation(
      () =>
        new Promise<PollResult>((resolve) => {
          resolveTask = resolve
        }),
    )
    renderHook(() => usePolling(task, { intervalMs: 1000, hiddenIntervalMs: 15000 }))

    await act(async () => {
      await Promise.resolve()
    })
    expect(task).toHaveBeenCalledTimes(1)

    // 응답이 오지 않는 동안 시간이 흘러도 두 번째 호출이 나가지 않는다.
    await advance(10000)
    expect(task).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveTask?.('continue')
      await Promise.resolve()
    })
    await advance(1001)
    expect(task).toHaveBeenCalledTimes(2)
  })

  it('이중 시작(StrictMode)에서도 폴링 루프가 계속 돈다', async () => {
    /*
     * 건너뛰기로 막으면 취소된 첫 인스턴스가 실행을 잡고 살아남은 인스턴스가
     * 건너뛰어 아무도 다음 주기를 예약하지 않는다. 라이브에서 대시보드가
     * 영구 로딩 상태가 됐던 회귀다.
     */
    const task = vi.fn<() => Promise<PollResult>>().mockResolvedValue('continue')
    const { rerender } = renderHook(() =>
      usePolling(task, { intervalMs: 1000, hiddenIntervalMs: 15000 }),
    )
    rerender()

    await act(async () => {
      await Promise.resolve()
    })

    // 루프가 죽지 않았는지 — 다음 주기에 반드시 한 번 더 돈다.
    const first = task.mock.calls.length
    await advance(1001)
    expect(task.mock.calls.length).toBeGreaterThan(first)
    await advance(1001)
    expect(task.mock.calls.length).toBeGreaterThan(first + 1)
  })

  it('같은 인스턴스에서 task 가 돌고 있으면 요청을 겹치지 않는다', async () => {
    /*
     * StrictMode 는 마운트 시 effect 를 두 번 실행하고 두 실행이 각각 즉시 1회
     * task 를 호출한다. 라이브 확인에서 대시보드 요청이 마운트마다 2회 나갔다.
     */
    let resolveTask: ((value: PollResult) => void) | null = null
    const task = vi.fn<() => Promise<PollResult>>().mockImplementation(
      () =>
        new Promise<PollResult>((resolve) => {
          resolveTask = resolve
        }),
    )

    const { rerender } = renderHook(() =>
      usePolling(task, { intervalMs: 1000, hiddenIntervalMs: 15000 }),
    )
    await act(async () => {
      await Promise.resolve()
    })
    expect(task).toHaveBeenCalledTimes(1)

    // 진행 중에 visibilitychange 로 즉시 갱신이 시도돼도 겹치지 않는다.
    await act(async () => {
      setVisibility('hidden')
      setVisibility('visible')
      await Promise.resolve()
    })
    expect(task).toHaveBeenCalledTimes(1)

    rerender()
    await act(async () => {
      resolveTask?.('continue')
      await Promise.resolve()
    })
    await advance(1001)
    expect(task).toHaveBeenCalledTimes(2)
  })

  it('enabled 가 false 면 시작하지 않는다', async () => {
    const task = vi.fn<() => Promise<PollResult>>().mockResolvedValue('continue')
    renderHook(() =>
      usePolling(task, { intervalMs: 1000, hiddenIntervalMs: 15000, enabled: false }),
    )

    await advance(10000)
    expect(task).not.toHaveBeenCalled()
  })

  it('unmount 하면 타이머와 listener 를 정리한다', async () => {
    const task = vi.fn<() => Promise<PollResult>>().mockResolvedValue('continue')
    const removeSpy = vi.spyOn(document, 'removeEventListener')
    const { unmount } = renderHook(() => usePolling(task, { intervalMs: 1000, hiddenIntervalMs: 15000 }))

    await advance(1001)
    const before = task.mock.calls.length
    unmount()

    await advance(10000)
    expect(task.mock.calls.length).toBe(before)
    expect(removeSpy).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
  })

  it('task 가 매 렌더 새로 만들어져도 폴링이 재시작되지 않는다', async () => {
    const calls: number[] = []
    const { rerender } = renderHook(
      ({ tag }: { tag: number }) =>
        usePolling(
          async () => {
            calls.push(tag)
            return 'continue'
          },
          { intervalMs: 1000, hiddenIntervalMs: 15000 },
        ),
      { initialProps: { tag: 1 } },
    )

    await act(async () => {
      await Promise.resolve()
    })
    expect(calls).toEqual([1])

    rerender({ tag: 2 })
    await act(async () => {
      await Promise.resolve()
    })
    // 재시작됐다면 여기서 즉시 한 번 더 불렸을 것이다.
    expect(calls).toEqual([1])

    // 다음 주기에는 최신 task 가 쓰인다.
    await advance(1001)
    expect(calls).toEqual([1, 2])
  })
})
