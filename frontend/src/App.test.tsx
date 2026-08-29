import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import * as api from './services/api'
import { EnvironmentId, EnvironmentItem, MissionStatusResponse, SessionResponse } from './types/training'

// 터미널은 xterm + WebSocket 을 잡으므로 렌더 확인 범위에서 제외한다.
// 다만 어떤 세션으로 열렸는지는 FE-04 의 판정 대상이라 그대로 드러낸다.
vi.mock('./components/Terminal/Terminal', () => ({
  default: ({ sessionId }: { sessionId?: string }) => (
    <div data-testid="terminal-stub" data-session-id={sessionId} />
  ),
}))

vi.mock('./services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof api>()
  return {
    ...actual,
    createTerminalSession: vi.fn(),
    deleteTerminalSession: vi.fn(),
    logoutUser: vi.fn(),
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

const sessionFor = (environment: EnvironmentId): SessionResponse => ({
  id: `session-${environment}`,
  namespace: 'user-abc',
  environment,
  created_at: '2026-08-28T00:00:00Z',
  is_active: true,
})

const notFound = () => Promise.reject(new api.ApiError('없음', 404))

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('token', 'test-token')
  // jsdom 에는 scrollIntoView 가 없다. TutorChat 이 마운트되면 그대로 터진다.
  window.HTMLElement.prototype.scrollIntoView = vi.fn()

  mocked.createTerminalSession.mockImplementation(async (_token, environment) =>
    sessionFor(environment),
  )
  mocked.deleteTerminalSession.mockResolvedValue(true)
  mocked.logoutUser.mockResolvedValue(undefined)
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

describe('환경별 터미널 세션 지연 생성 (FE-04)', () => {
  const workspaceTab = (label: string) => screen.getByRole('button', { name: label })

  it('로그인하고 미션 화면에 있는 동안에는 세션을 만들지 않는다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    render(<App />)

    await screen.findByRole('tablist')
    expect(mocked.createTerminalSession).not.toHaveBeenCalled()
  })

  it('터미널 화면을 열면 그때 현재 환경 세션을 만든다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S])
    render(<App />)

    await screen.findByRole('tablist')
    fireEvent.click(workspaceTab('터미널'))

    await waitFor(() =>
      expect(mocked.createTerminalSession).toHaveBeenCalledWith('test-token', 'kubernetes'),
    )
  })

  it('환경을 오가도 환경마다 한 번씩만 만든다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    render(<App />)

    await screen.findByRole('tablist')
    fireEvent.click(workspaceTab('터미널'))
    await waitFor(() =>
      expect(mocked.createTerminalSession).toHaveBeenCalledWith('test-token', 'kubernetes'),
    )

    fireEvent.click(tab('Docker'))
    await waitFor(() =>
      expect(mocked.createTerminalSession).toHaveBeenCalledWith('test-token', 'docker'),
    )

    fireEvent.click(tab('Kubernetes'))
    await waitFor(() => expect(tab('Kubernetes').getAttribute('aria-selected')).toBe('true'))
    expect(mocked.createTerminalSession).toHaveBeenCalledTimes(2)
  })

  it('세션이 준비되는 동안에는 로딩을 보여주고 터미널을 띄우지 않는다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    mocked.createTerminalSession.mockImplementation(() => new Promise(() => {}))
    render(<App />)

    expect(await screen.findByText(/터미널 세션을 준비하는 중/)).toBeTruthy()
    expect(screen.queryByTestId('terminal-stub')).toBeNull()
  })

  it('활성 미션 세션이 준비되면 터미널을 띄운다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    render(<App />)

    expect(await screen.findByTestId('terminal-stub')).toBeTruthy()
  })

  it('세션 생성이 실패하면 이유와 재시도 버튼이 보이고, 재시도가 실제 호출로 이어진다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    mocked.createTerminalSession.mockRejectedValueOnce(new Error('샌드박스를 준비하지 못했습니다'))
    render(<App />)

    expect(await screen.findByText('샌드박스를 준비하지 못했습니다')).toBeTruthy()
    expect(screen.queryByTestId('terminal-stub')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }))

    expect(await screen.findByTestId('terminal-stub')).toBeTruthy()
    expect(mocked.createTerminalSession).toHaveBeenCalledTimes(2)
  })

  it('요청한 환경과 다른 세션이 오면 터미널을 띄우지 않는다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    mocked.createTerminalSession.mockResolvedValue(sessionFor('docker'))
    render(<App />)

    expect(await screen.findByText(/다른 세션\(docker\)/)).toBeTruthy()
    expect(screen.queryByTestId('terminal-stub')).toBeNull()
  })

  it('로그아웃하면 만들어 둔 세션을 정리하고 즉시 로그인 화면으로 돌아간다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S])
    render(<App />)

    await screen.findByRole('tablist')
    fireEvent.click(workspaceTab('터미널'))
    await waitFor(() => expect(mocked.createTerminalSession).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }))

    expect(await screen.findByRole('button', { name: '로그인' })).toBeTruthy()
    expect(localStorage.getItem('token')).toBeNull()
    await waitFor(() =>
      expect(mocked.deleteTerminalSession).toHaveBeenCalledWith('test-token', 'session-kubernetes'),
    )
  })
})

describe('세션 정리 경로 (FE-04)', () => {
  const openTerminalWorkspace = async () => {
    mocked.getEnvironments.mockResolvedValue([K8S])
    render(<App />)
    await screen.findByRole('tablist')
    fireEvent.click(screen.getByRole('button', { name: '터미널' }))
    await waitFor(() => expect(mocked.createTerminalSession).toHaveBeenCalledTimes(1))
  }

  it('활성 미션 환경의 세션으로만 터미널을 연다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('docker'))
    render(<App />)

    const stub = await screen.findByTestId('terminal-stub')
    expect(stub.getAttribute('data-session-id')).toBe('session-docker')
    expect(mocked.createTerminalSession).toHaveBeenCalledWith('test-token', 'docker')
    expect(mocked.createTerminalSession).not.toHaveBeenCalledWith('test-token', 'kubernetes')
  })

  it('인증이 만료되면 토큰과 화면 상태를 모두 비운다', async () => {
    await openTerminalWorkspace()

    act(() => {
      window.dispatchEvent(new Event(api.AUTH_EXPIRED_EVENT))
    })

    expect(await screen.findByRole('button', { name: '로그인' })).toBeTruthy()
    expect(localStorage.getItem('token')).toBeNull()
    // 죽은 토큰으로 서버 정리를 시도하지 않는다.
    expect(mocked.deleteTerminalSession).not.toHaveBeenCalled()
  })

  it('세션 정리가 실패해도 로그아웃 화면 전환을 막지 않는다', async () => {
    mocked.deleteTerminalSession.mockRejectedValue(new Error('offline'))
    mocked.logoutUser.mockRejectedValue(new Error('offline'))
    await openTerminalWorkspace()

    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }))

    expect(await screen.findByRole('button', { name: '로그인' })).toBeTruthy()
    expect(localStorage.getItem('token')).toBeNull()
  })
})

describe('세션을 만드는 시점 (FE-04 회귀)', () => {
  it('프로필이 오기 전에 터미널을 열면 저장된 환경이 정해질 때까지 기다린다', async () => {
    let resolveProfile!: (value: api.UserProfileResponse) => void
    mocked.getProfile.mockReturnValue(
      new Promise<api.UserProfileResponse>((resolve) => {
        resolveProfile = resolve
      }),
    )
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    localStorage.setItem('afterfail:environment:v1:user-1', 'docker')
    render(<App />)

    await screen.findByRole('tablist')
    fireEvent.click(screen.getByRole('button', { name: '터미널' }))

    // 아직 kubernetes 로 보이지만, 저장값이 반영되기 전이라 세션을 만들면 안 된다.
    expect(mocked.createTerminalSession).not.toHaveBeenCalled()

    await act(async () => {
      resolveProfile({
        id: 'user-1',
        username: 'tester',
        created_at: '2026-08-28T00:00:00Z',
        missions_completed: 0,
        total_score: 0,
      })
    })

    await waitFor(() =>
      expect(mocked.createTerminalSession).toHaveBeenCalledWith('test-token', 'docker'),
    )
    expect(mocked.createTerminalSession).toHaveBeenCalledTimes(1)
  })
})
