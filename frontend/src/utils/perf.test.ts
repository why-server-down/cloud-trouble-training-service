import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { markStart, measureSince, nextFrame, PERF } from './perf'

beforeEach(() => {
  performance.clearMarks()
  performance.clearMeasures()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('성능 측정 (FE-20)', () => {
  it('시작점을 찍고 경과를 measure 로 남긴다', () => {
    markStart(PERF.TUTOR_RESPONSE)
    const elapsed = measureSince(PERF.TUTOR_RESPONSE)

    expect(elapsed).not.toBeNull()
    expect(elapsed as number).toBeGreaterThanOrEqual(0)
    // DevTools 와 Playwright 가 읽는 경로. 이름이 바뀌면 검증이 조용히 끊긴다.
    expect(performance.getEntriesByName(PERF.TUTOR_RESPONSE, 'measure').length).toBe(1)
  })

  it('시작점이 없으면 null 이고 measure 를 만들지 않는다', () => {
    expect(measureSince(PERF.MISSION_CHECK_API)).toBeNull()
    expect(performance.getEntriesByName(PERF.MISSION_CHECK_API, 'measure').length).toBe(0)
  })

  it('측정이 끝나면 시작 mark 를 지워 두 번 재지 않는다', () => {
    markStart(PERF.MISSION_CHECK_API)
    expect(measureSince(PERF.MISSION_CHECK_API)).not.toBeNull()
    expect(measureSince(PERF.MISSION_CHECK_API)).toBeNull()
  })

  it('같은 이름으로 다시 시작하면 이전 시작점을 덮는다', () => {
    markStart(PERF.TUTOR_RESPONSE)
    markStart(PERF.TUTOR_RESPONSE)

    expect(performance.getEntriesByName(`${PERF.TUTOR_RESPONSE}:start`, 'mark').length).toBe(1)
  })

  it('API 시간과 화면 반영 시간을 따로 잰다', () => {
    markStart(PERF.MISSION_CHECK_API)
    markStart(PERF.MISSION_CHECK_COMMIT)

    expect(measureSince(PERF.MISSION_CHECK_API)).not.toBeNull()
    // commit 은 아직 진행 중이므로 따로 남아 있어야 한다.
    expect(measureSince(PERF.MISSION_CHECK_COMMIT)).not.toBeNull()
    expect(performance.getEntriesByName(PERF.MISSION_CHECK_API, 'measure').length).toBe(1)
    expect(performance.getEntriesByName(PERF.MISSION_CHECK_COMMIT, 'measure').length).toBe(1)
  })

  it('performance 가 던져도 기능을 막지 않는다', () => {
    vi.spyOn(performance, 'mark').mockImplementation(() => {
      throw new Error('blocked')
    })

    expect(() => markStart(PERF.TUTOR_RESPONSE)).not.toThrow()
    expect(measureSince(PERF.TUTOR_RESPONSE)).toBeNull()
  })

  it('nextFrame 은 requestAnimationFrame 이 없어도 resolve 된다', async () => {
    const original = globalThis.requestAnimationFrame
    // @ts-expect-error 없는 환경을 흉내낸다.
    globalThis.requestAnimationFrame = undefined

    await expect(nextFrame()).resolves.toBeUndefined()

    globalThis.requestAnimationFrame = original
  })
})
