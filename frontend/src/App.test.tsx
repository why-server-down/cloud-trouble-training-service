import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import * as api from './services/api'
import { EnvironmentItem, MissionStatusResponse } from './types/training'

// 터미널은 xterm + WebSocket 을 잡으므로 렌더 확인 범위에서 제외한다.
vi.mock('./components/Terminal/Terminal', () => ({
  default: () => <div data-testid="terminal-stub" />,
}))

vi.mock('./services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof api>()
  return {
    ...actual,
    createTerminalSession: vi.fn(),
    getProfile: vi.fn(),
    getEnvironments: vi.fn(),
    listMissions: vi.fn(),
    getMissionStatus: vi.fn(),
    getScenarioStatus: vi.fn(),
    getUnlockStatus: vi.fn(),
    getDashboardStats: vi.fn(),
    getLearningCurve: vi.fn(),
    getLeaderboard: vi.fn(),
    getAchievements: vi.fn(),
  }
})

const mocked = vi.mocked(api)

const K8S: EnvironmentItem = { id: 'kubernetes', status: 'available', capabilities: ['terminal'] }
const DOCKER_AVAILABLE: EnvironmentItem = { id: 'docker', status: 'available', capabilities: [] }
const DOCKER_PREPARING: EnvironmentItem = { id: 'docker', status: 'preparing', capabilities: [] }
const LINUX_PREPARING: EnvironmentItem = { id: 'linux', status: 'preparing', capabilities: [] }

const activeMissionStatus = (environment: 'kubernetes' | 'docker'): MissionStatusResponse => ({
  attempt: {
    id: 'attempt-1',
    user_id: 'user-1',
    mission_id: 'mission-1',
    attempt_type: 'static_mission',
    scenario_id: null,
    environment,
    status: 'in_progress',
    start_time: '2026-08-28T00:00:00Z',
    end_time: null,
    final_score: null,
    hints_used: 0,
  },
  elapsed_seconds: 5,
  remaining_seconds: 1195,
  current_score: 100,
})

const notFound = () => Promise.reject(new api.ApiError('없음', 404))

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('token', 'test-token')
  // jsdom 에는 scrollIntoView 가 없다. TutorChat 이 마운트되면 그대로 터진다.
  window.HTMLElement.prototype.scrollIntoView = vi.fn()

  mocked.createTerminalSession.mockResolvedValue({
    id: 'session-1',
    namespace: 'user-abc',
    environment: 'kubernetes',
    created_at: '2026-08-28T00:00:00Z',
    is_active: true,
  })
  mocked.getProfile.mockResolvedValue({
    id: 'user-1',
    username: 'tester',
    created_at: '2026-08-28T00:00:00Z',
    missions_completed: 0,
    total_score: 0,
  })
  mocked.listMissions.mockResolvedValue([])
  mocked.getMissionStatus.mockImplementation(notFound)
  mocked.getScenarioStatus.mockImplementation(notFound)
  mocked.getUnlockStatus.mockResolvedValue({ unlocked: false, completed_static: 0, total_static: 4 })
  mocked.getDashboardStats.mockImplementation(() => new Promise(() => {}))
  mocked.getLearningCurve.mockResolvedValue([])
  mocked.getLeaderboard.mockResolvedValue([])
  mocked.getAchievements.mockResolvedValue({ unlocked: 0, total: 0, progress: 0, items: [] })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const tab = (label: string) => screen.getByRole('tab', { name: new RegExp(label) })

describe('환경 가용성 화면 (FE-03)', () => {
  it('로딩 중에는 로딩 안내가 보이고 탭은 아직 없다', async () => {
    mocked.getEnvironments.mockImplementation(() => new Promise(() => {}))
    render(<App />)

    expect(await screen.findByText(/훈련 환경 목록을 불러오는 중/)).toBeTruthy()
    expect(screen.queryByRole('tablist')).toBeNull()
  })

  it('성공하면 서버가 준 환경만 탭으로 그리고 available 을 선택한다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_PREPARING, LINUX_PREPARING])
    render(<App />)

    await screen.findByRole('tablist')
    expect(screen.getAllByRole('tab')).toHaveLength(3)
    expect(tab('Kubernetes').getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('tabpanel')).toBeTruthy()
    // Application 은 탭이 아니라 후속 연구 영역으로 내려갔다.
    expect(screen.queryByRole('tab', { name: /Application/ })).toBeNull()
    expect(screen.getByText(/후속 연구/)).toBeTruthy()
  })

  it('degraded 환경을 선택하면 경고를 띄우되 진입은 허용한다', async () => {
    mocked.getEnvironments.mockResolvedValue([
      { id: 'kubernetes', status: 'degraded', capabilities: ['terminal'] },
      DOCKER_PREPARING,
    ])
    render(<App />)

    await screen.findByRole('tablist')
    expect(tab('Kubernetes').getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('alert').textContent).toContain('일부 기능이 불안정')
    expect(screen.getByRole('tabpanel')).toBeTruthy()
  })

  it('전체 실패면 오류와 재시도 버튼을 보여주고 다시 호출한다', async () => {
    mocked.getEnvironments.mockRejectedValue(new Error('환경 목록을 불러오지 못했습니다'))
    render(<App />)

    // 제목과 서버 메시지가 같은 문장일 수 있으므로 alert 영역 전체로 확인한다.
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('환경 목록을 불러오지 못했습니다')
    expect(screen.queryByRole('tablist')).toBeNull()

    mocked.getEnvironments.mockResolvedValue([K8S])
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }))

    await screen.findByRole('tablist')
    expect(mocked.getEnvironments).toHaveBeenCalledTimes(2)
  })

  it('선택 가능한 환경이 하나도 없으면 안내와 준비 상황을 보여준다', async () => {
    mocked.getEnvironments.mockResolvedValue([
      { id: 'kubernetes', status: 'preparing', capabilities: [] },
      DOCKER_PREPARING,
    ])
    render(<App />)

    await screen.findByRole('tablist')
    expect(screen.getByText(/지금 선택할 수 있는 훈련 환경이 없습니다/)).toBeTruthy()
    expect(screen.getByText(/준비 중 환경/)).toBeTruthy()
    expect(screen.getAllByRole('tab').every((node) => node.getAttribute('aria-disabled') === 'true')).toBe(true)
  })

  it('사용자별 마지막 환경을 저장하고 복원한다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    localStorage.setItem('afterfail:environment:v1:user-1', 'docker')
    render(<App />)

    await screen.findByRole('tablist')
    await waitFor(() => expect(tab('Docker').getAttribute('aria-selected')).toBe('true'))

    fireEvent.click(tab('Kubernetes'))
    await waitFor(() =>
      expect(localStorage.getItem('afterfail:environment:v1:user-1')).toBe('kubernetes'),
    )
  })

  it('저장된 환경이 선택 불가면 kubernetes 로 돌아간다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_PREPARING])
    localStorage.setItem('afterfail:environment:v1:user-1', 'docker')
    render(<App />)

    await screen.findByRole('tablist')
    await waitFor(() => expect(tab('Kubernetes').getAttribute('aria-selected')).toBe('true'))
    expect(tab('Docker').getAttribute('aria-selected')).toBe('false')
  })
})

describe('활성 attempt 환경 잠금 (FE-05)', () => {
  it('활성 미션이 있으면 다른 환경 탭이 잠기고 이유가 보인다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    render(<App />)

    await screen.findByRole('tablist')
    await waitFor(() => expect(tab('Docker').getAttribute('aria-disabled')).toBe('true'))
    expect(screen.getByText(/다른 환경으로 전환할 수 없습니다/)).toBeTruthy()

    fireEvent.click(tab('Docker'))
    expect(tab('Kubernetes').getAttribute('aria-selected')).toBe('true')
  })

  it('서버 status 의 environment 로 활성 환경을 복원한다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    // 저장값은 kubernetes 인데 서버에는 docker attempt 가 살아 있다 → 서버가 우선이다.
    localStorage.setItem('afterfail:environment:v1:user-1', 'kubernetes')
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('docker'))
    render(<App />)

    await screen.findByRole('tablist')
    await waitFor(() => expect(tab('Docker').getAttribute('aria-selected')).toBe('true'))
    expect(tab('Kubernetes').getAttribute('aria-disabled')).toBe('true')
  })
})
