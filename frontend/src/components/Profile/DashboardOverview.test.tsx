import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardOverview from './DashboardOverview'
import * as api from '../../services/api'

vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof api>()
  return {
    ...actual,
    getDashboardStats: vi.fn(),
    getLearningCurve: vi.fn(),
    getLeaderboard: vi.fn(),
    getAchievements: vi.fn(),
  }
})

const mocked = vi.mocked(api)

const tier: api.DashboardStatsResponse['current_tier'] = {
  name: 'Bronze',
  min_score: 0,
  max_score: 200,
  color: '#cd7f32',
  progress: 10,
  next_tier: 'Silver',
}

const envEntry = (overrides: Partial<api.EnvironmentStatEntry> = {}): api.EnvironmentStatEntry => ({
  completed: 2,
  average_score: 80,
  average_mttr: 120,
  hints_used: 1,
  competency: 70,
  ...overrides,
})

const stats = (overrides: Partial<api.DashboardStatsResponse> = {}): api.DashboardStatsResponse => ({
  username: 'tester',
  total_score: 300,
  missions_completed: 3,
  total_time_spent: 360,
  hints_used: 4,
  current_tier: tier,
  skill_scores: { troubleshooting: 60, resource: 40, network: 20, ops: 10 },
  environment: null,
  environment_stats: {
    kubernetes: envEntry(),
    docker: envEntry({ competency: 40 }),
    linux: envEntry({ completed: 0, competency: null }),
  },
  ...overrides,
})

beforeEach(() => {
  mocked.getDashboardStats.mockResolvedValue(stats())
  mocked.getLearningCurve.mockResolvedValue([])
  mocked.getLeaderboard.mockResolvedValue([])
  mocked.getAchievements.mockResolvedValue({ unlocked: 0, total: 0, progress: 0, items: [] })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const filterButton = (label: string) => screen.getByRole('button', { name: label })

describe('환경 필터와 핵심 지표 (FE-13)', () => {
  it('처음에는 전체 합계를 조회한다', async () => {
    render(<DashboardOverview token="t" />)

    await waitFor(() => expect(mocked.getDashboardStats).toHaveBeenCalled())
    expect(mocked.getDashboardStats.mock.calls[0][1]).toBe('all')
    expect(mocked.getLearningCurve.mock.calls[0][1]).toBe('all')
  })

  it('필터를 바꾸면 통계와 곡선을 같은 환경으로 다시 조회한다', async () => {
    render(<DashboardOverview token="t" />)
    await screen.findByText('완료 미션')

    fireEvent.click(filterButton('Docker'))

    await waitFor(() =>
      expect(mocked.getDashboardStats).toHaveBeenCalledWith('t', 'docker', expect.anything()),
    )
    expect(mocked.getLearningCurve).toHaveBeenCalledWith('t', 'docker', expect.anything())
  })

  it('필터를 바꾸면 이전 요청을 취소한다', async () => {
    render(<DashboardOverview token="t" />)
    await screen.findByText('완료 미션')

    const firstSignal = mocked.getDashboardStats.mock.calls[0][2] as AbortSignal
    expect(firstSignal.aborted).toBe(false)

    fireEvent.click(filterButton('Linux'))
    await waitFor(() => expect(firstSignal.aborted).toBe(true))
  })

  it('평균 MTTR 을 사람이 읽는 분/초로 보여준다', async () => {
    // total_time_spent 360 / 3건 = 120초
    render(<DashboardOverview token="t" />)
    expect(await screen.findByText('2분 0초')).toBeTruthy()
  })

  it('완료 0건은 평균을 0 으로 위조하지 않고 데이터 없음으로 표시한다', async () => {
    mocked.getDashboardStats.mockResolvedValue(
      stats({ missions_completed: 0, total_score: 0, total_time_spent: 0 }),
    )
    render(<DashboardOverview token="t" />)

    await screen.findByText('완료 미션')
    expect(screen.getByLabelText('평균 점수 데이터 없음')).toBeTruthy()
    expect(screen.getByLabelText('평균 MTTR 데이터 없음')).toBeTruthy()
    // 0회 완료 자체는 숫자로 보여준다 — 이것은 실패가 아니다.
    expect(screen.getByText('0건')).toBeTruthy()
  })

  it('조회 실패는 0회 완료와 다르게 표시한다', async () => {
    mocked.getDashboardStats.mockRejectedValue(new Error('offline'))
    render(<DashboardOverview token="t" />)

    expect(await screen.findByText(/통계를 불러오지 못했습니다/)).toBeTruthy()
    expect(screen.getByLabelText('완료 미션 데이터 없음')).toBeTruthy()
    expect(screen.getByText(/일부 데이터를 불러오지 못했습니다/)).toBeTruthy()
  })
})

describe('환경 역량 레이더와 성장 곡선 (FE-14)', () => {
  it('전체 보기에서는 3축 환경 역량 레이더를 그린다', async () => {
    render(<DashboardOverview token="t" />)

    const radar = await screen.findByRole('img', { name: /환경 역량 레이더/ })
    expect(radar.getAttribute('aria-label')).toContain('Kubernetes 70')
    expect(radar.getAttribute('aria-label')).toContain('Docker 40')
    // 시도가 없는 환경은 0 이 아니라 데이터 없음이다.
    expect(radar.getAttribute('aria-label')).toContain('Linux 데이터 없음')
    expect(radar.querySelector('.skill-radar-value')?.getAttribute('points')?.split(' ')).toHaveLength(3)
  })

  it('단일 환경 보기에서는 기존 4축 스킬 레이더를 유지한다', async () => {
    render(<DashboardOverview token="t" />)
    await screen.findByText('완료 미션')

    fireEvent.click(filterButton('Docker'))

    const radar = await screen.findByRole('img', { name: /스킬 레이더/ })
    expect(radar.getAttribute('aria-label')).toContain('Troubleshooting 60')
    expect(radar.querySelector('.skill-radar-value')?.getAttribute('points')?.split(' ')).toHaveLength(4)
  })

  it('완료가 0건이면 환경 역량을 0 축으로 그리지 않고 안내를 띄운다', async () => {
    /*
     * 라이브 확인(2026-09-01): 백엔드는 environment=all 조회에서 완료가 0건이어도
     * 세 환경 엔트리를 모두 채워 보내고 competency 만 null 로 둔다.
     * 엔트리 유무로 판정하면 신규 사용자에게 찌그러진 0축 레이더가 보인다.
     */
    mocked.getDashboardStats.mockResolvedValue(
      stats({
        missions_completed: 0,
        environment_stats: {
          kubernetes: envEntry({ completed: 0, average_score: 0, average_mttr: 0, hints_used: 0, competency: null }),
          docker: envEntry({ completed: 0, average_score: 0, average_mttr: 0, hints_used: 0, competency: null }),
          linux: envEntry({ completed: 0, average_score: 0, average_mttr: 0, hints_used: 0, competency: null }),
        },
      }),
    )
    render(<DashboardOverview token="t" />)

    expect(await screen.findByText(/환경 역량을 계산할 수 없습니다/)).toBeTruthy()
    expect(screen.queryByRole('img', { name: /환경 역량 레이더/ })).toBeNull()
  })

  it('environment_stats 가 비어 있어도 안내를 띄운다', async () => {
    mocked.getDashboardStats.mockResolvedValue(stats({ environment_stats: {} }))
    render(<DashboardOverview token="t" />)

    expect(await screen.findByText(/환경 역량을 계산할 수 없습니다/)).toBeTruthy()
  })

  it('한 환경만 완료했으면 레이더를 그리고 나머지는 대체 텍스트로 구분한다', async () => {
    mocked.getDashboardStats.mockResolvedValue(
      stats({
        environment_stats: {
          kubernetes: envEntry({ competency: 70 }),
          docker: envEntry({ completed: 0, competency: null }),
          linux: envEntry({ completed: 0, competency: null }),
        },
      }),
    )
    render(<DashboardOverview token="t" />)

    const radar = await screen.findByRole('img', { name: /환경 역량 레이더/ })
    expect(radar.getAttribute('aria-label')).toContain('Kubernetes 70')
    expect(radar.getAttribute('aria-label')).toContain('Docker 데이터 없음')
  })

  it('학습 곡선에 점수를 함께 표시하고 대체 텍스트로 수치를 읽을 수 있다', async () => {
    mocked.getLearningCurve.mockResolvedValue([
      {
        attempt_id: 'a1',
        mission_id: 'm1',
        mission_name: 'Pod 장애',
        attempt_number: 1,
        completion_time: 90,
        score: 95,
        hints_used: 0,
        completed_at: '2026-09-01T00:00:00Z',
      },
    ])
    render(<DashboardOverview token="t" />)

    const curve = await screen.findByRole('img', { name: /완료 시간 추이/ })
    expect(curve.getAttribute('aria-label')).toContain('Pod 장애 1분 30초 95점')
    expect(screen.getByText('1분 30초 · 95점')).toBeTruthy()
  })

  it('곡선 조회 실패와 완료 0건을 구분한다', async () => {
    mocked.getLearningCurve.mockRejectedValue(new Error('offline'))
    render(<DashboardOverview token="t" />)

    expect(await screen.findByText(/학습 곡선을 불러오지 못했습니다/)).toBeTruthy()
  })
})

describe('미션 종료 후 통계 동기화 (FE-15)', () => {
  it('refreshKey 가 오르면 서버 값을 다시 읽는다', async () => {
    const { rerender } = render(<DashboardOverview token="t" refreshKey={0} />)
    await waitFor(() => expect(mocked.getDashboardStats).toHaveBeenCalledTimes(1))

    rerender(<DashboardOverview token="t" refreshKey={1} />)
    await waitFor(() => expect(mocked.getDashboardStats).toHaveBeenCalledTimes(2))
  })

  it('같은 refreshKey 로 다시 렌더해도 재조회하지 않는다', async () => {
    const { rerender } = render(<DashboardOverview token="t" refreshKey={3} />)
    await waitFor(() => expect(mocked.getDashboardStats).toHaveBeenCalledTimes(1))

    rerender(<DashboardOverview token="t" refreshKey={3} />)
    await waitFor(() => expect(mocked.getDashboardStats).toHaveBeenCalledTimes(1))
  })
})
