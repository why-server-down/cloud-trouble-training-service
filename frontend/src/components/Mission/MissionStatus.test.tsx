import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import MissionStatus from './MissionStatus'
import * as api from '../../services/api'

vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof api>()
  return { ...actual, getMissionStatus: vi.fn() }
})

const mocked = vi.mocked(api)

const statusFor = (
  overrides: Partial<api.MissionStatusResponse> = {},
  attemptStatus: string = 'in_progress',
): api.MissionStatusResponse => ({
  attempt: {
    id: 'attempt-1',
    user_id: 'user-1',
    mission_id: 'mission-1',
    attempt_type: 'static_mission',
    scenario_id: null,
    environment: 'linux',
    status: attemptStatus as api.MissionStatusResponse['attempt']['status'],
    start_time: '2026-09-01T00:00:00Z',
    end_time: null,
    final_score: null,
    hints_used: 1,
  },
  elapsed_seconds: 10,
  remaining_seconds: 600,
  current_score: 95,
  ...overrides,
})

const renderStatus = (overrides: Partial<React.ComponentProps<typeof MissionStatus>> = {}) => {
  const props = {
    token: 't',
    refreshKey: 0,
    pendingAction: null,
    onStatusChange: vi.fn(),
    onMissionEnd: vi.fn(),
    onCheck: vi.fn(),
    onAbandon: vi.fn(),
    onHint: vi.fn(),
    ...overrides,
  }
  return { props, view: render(<MissionStatus {...props} />) }
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  mocked.getMissionStatus.mockResolvedValue(statusFor())
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
})

const advance = async (ms: number) => {
  await act(async () => {
    await Promise.resolve()
    vi.advanceTimersByTime(ms)
    await Promise.resolve()
  })
}

describe('미션 상태 폴링 (FE-16)', () => {
  it('1초가 아니라 5초 간격으로 조회한다', async () => {
    renderStatus()

    await waitFor(() => expect(mocked.getMissionStatus).toHaveBeenCalledTimes(1))

    // 예전에는 1초마다 던졌다. 4초까지는 추가 요청이 없어야 한다.
    await advance(4000)
    expect(mocked.getMissionStatus).toHaveBeenCalledTimes(1)

    await advance(1100)
    expect(mocked.getMissionStatus).toHaveBeenCalledTimes(2)
  })

  it('서버 폴링이 느려도 남은 시간은 1초마다 줄어든다', async () => {
    renderStatus()

    expect(await screen.findByText('10:00')).toBeTruthy()

    // 서버를 다시 부르지 않은 2초 사이에도 표시가 내려간다.
    await advance(2000)
    expect(screen.getByText('9:58')).toBeTruthy()
  })

  it('완료 상태를 받으면 폴링을 멈추고 종료를 알린다', async () => {
    mocked.getMissionStatus.mockResolvedValue(statusFor({}, 'completed'))
    const { props } = renderStatus()

    await waitFor(() => expect(props.onMissionEnd).toHaveBeenCalledTimes(1))

    await advance(30000)
    expect(mocked.getMissionStatus).toHaveBeenCalledTimes(1)
  })

  it('404 는 오류가 아니라 종료 신호로 다루고 멈춘다', async () => {
    mocked.getMissionStatus.mockRejectedValue(new api.ApiError('없음', 404))
    const { props } = renderStatus()

    await waitFor(() => expect(props.onMissionEnd).toHaveBeenCalledTimes(1))

    await advance(30000)
    expect(mocked.getMissionStatus).toHaveBeenCalledTimes(1)
  })

  it('네트워크 실패는 화면을 비우지 않고 낡았음을 알린다', async () => {
    mocked.getMissionStatus.mockResolvedValueOnce(statusFor())
    await act(async () => {
      renderStatus()
      await Promise.resolve()
    })
    await screen.findByText('10:00')

    mocked.getMissionStatus.mockRejectedValue(new Error('offline'))
    await advance(5100)

    expect(await screen.findByText(/상태 조회에 실패했습니다/)).toBeTruthy()
    // 값은 남아 있어야 한다 — 비우면 사용자는 미션이 사라진 줄 안다.
    expect(screen.getByText('현재 점수')).toBeTruthy()
  })

  it('연속 실패는 간격을 늘린다', async () => {
    mocked.getMissionStatus.mockRejectedValue(new Error('offline'))
    renderStatus()

    await waitFor(() => expect(mocked.getMissionStatus).toHaveBeenCalledTimes(1))

    // 1회 실패 → 10초 (5초 * 2)
    await advance(9000)
    expect(mocked.getMissionStatus).toHaveBeenCalledTimes(1)
    await advance(1100)
    expect(mocked.getMissionStatus).toHaveBeenCalledTimes(2)
  })

  it('탭이 숨으면 조회 간격을 늘린다', async () => {
    renderStatus()
    await waitFor(() => expect(mocked.getMissionStatus).toHaveBeenCalledTimes(1))

    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
      await Promise.resolve()
    })

    await advance(14000)
    expect(mocked.getMissionStatus).toHaveBeenCalledTimes(1)
    await advance(1100)
    expect(mocked.getMissionStatus).toHaveBeenCalledTimes(2)
  })

  it('unmount 하면 더 이상 조회하지 않는다', async () => {
    const { view } = renderStatus()
    await waitFor(() => expect(mocked.getMissionStatus).toHaveBeenCalledTimes(1))

    view.unmount()
    await advance(30000)
    expect(mocked.getMissionStatus).toHaveBeenCalledTimes(1)
  })
})

describe('액션별 진행 표시 (FE-16)', () => {
  it('유휴 상태에서는 세 버튼이 모두 눌린다', async () => {
    const { props } = renderStatus()
    await screen.findByText('10:00')

    fireEvent.click(screen.getByRole('button', { name: '완료 확인' }))
    expect(props.onCheck).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: '힌트 사용' }))
    expect(props.onHint).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: '미션 포기' }))
    expect(props.onAbandon).toHaveBeenCalledTimes(1)
  })

  it('진행 중인 액션만 문구가 바뀌고 세 버튼이 모두 잠긴다', async () => {
    renderStatus({ pendingAction: 'hint' })
    await screen.findByText('10:00')

    expect(screen.getByRole('button', { name: '힌트 요청 중...' }).hasAttribute('disabled')).toBe(true)
    // 나머지 버튼은 원래 문구를 유지하되 잠긴다 — 어떤 액션이 도는지 구분된다.
    expect(screen.getByRole('button', { name: '완료 확인' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '미션 포기' }).hasAttribute('disabled')).toBe(true)
  })

  it('진행 중에는 중복 클릭이 콜백을 부르지 않는다', async () => {
    const { props } = renderStatus({ pendingAction: 'check' })
    await screen.findByText('10:00')

    fireEvent.click(screen.getByRole('button', { name: '확인 중...' }))
    fireEvent.click(screen.getByRole('button', { name: '확인 중...' }))
    expect(props.onCheck).not.toHaveBeenCalled()
  })

  it('액션마다 다른 문구를 쓴다', async () => {
    const { view } = renderStatus({ pendingAction: 'check' })
    await screen.findByText('10:00')
    expect(screen.getByText('확인 중...')).toBeTruthy()

    view.unmount()
    renderStatus({ pendingAction: 'abandon' })
    await screen.findByText('10:00')
    expect(screen.getByText('포기 처리 중...')).toBeTruthy()
  })
})
