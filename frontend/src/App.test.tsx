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

/*
 * 백엔드 `availability()` 는 구현된 환경에 capability 5개를 모두 실어 보낸다
 * (2026-09-02 실측). `available` + 빈 배열은 실제로 오지 않는 조합이다 —
 * FE-22 로 capabilities 가 화면 분기의 근거가 된 뒤로는 픽스처가 이 형태여야
 * 다른 테스트가 엉뚱한 이유로 깨지지 않는다. capability 게이팅 자체는 아래
 * "capabilities 기반 기능 게이팅 (FE-22)" describe 에서 값을 바꿔 확인한다.
 */
const ALL_CAPABILITIES = ['static_mission', 'ai_scenario', 'terminal', 'tutor', 'observability']

const K8S: EnvironmentItem = { id: 'kubernetes', status: 'available', capabilities: ALL_CAPABILITIES }
const DOCKER_AVAILABLE: EnvironmentItem = { id: 'docker', status: 'available', capabilities: ALL_CAPABILITIES }
const DOCKER_PREPARING: EnvironmentItem = { id: 'docker', status: 'preparing', capabilities: [] }
const LINUX_PREPARING: EnvironmentItem = { id: 'linux', status: 'preparing', capabilities: [] }
const LINUX_AVAILABLE: EnvironmentItem = { id: 'linux', status: 'available', capabilities: ALL_CAPABILITIES }

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
      { id: 'kubernetes', status: 'degraded', capabilities: ALL_CAPABILITIES },
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

describe('환경별 관측 패널 (FE-08)', () => {
  /** Prometheus probe 를 가로챈다. 성공 응답이면 readiness 가 바로 통과한다. */
  const stubPrometheus = () => {
    const probe = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'success', data: { result: [{ value: [0, '1'] }] } }),
    })) as unknown as typeof fetch
    vi.stubGlobal('fetch', probe)
    return vi.mocked(probe)
  }

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('Kubernetes 미션에서는 해당 환경 대시보드를 열고 title 로 환경을 드러낸다', async () => {
    const probe = stubPrometheus()
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    render(<App />)

    const frame = await screen.findByTitle('Kubernetes Grafana dashboard')
    expect(frame.getAttribute('src')).toContain('/d/k8s-survival-overview/')
    expect(screen.getByText('OBSERVABILITY / KUBERNETES')).toBeTruthy()
    await waitFor(() => expect(probe).toHaveBeenCalled())
    expect(vi.mocked(probe).mock.calls[0][0]).toContain('/api/v1/query?query=')
  })

  it('대시보드가 없는 Docker 미션에서는 iframe 대신 안내를 띄운다', async () => {
    stubPrometheus()
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('docker'))
    render(<App />)

    expect(await screen.findByText(/Docker 환경은 관측 대시보드가 아직 없습니다/)).toBeTruthy()
    // K8s 대시보드로 대체하지 않는다 — 남의 환경 지표를 자기 것으로 읽게 된다.
    expect(screen.queryByTitle(/Grafana dashboard/)).toBeNull()
    expect(screen.getByText('OBSERVABILITY / DOCKER')).toBeTruthy()
    expect(screen.queryByRole('link', { name: '새 창' })).toBeNull()
  })

  it('대시보드가 없는 환경에서는 readiness polling 을 시작하지 않는다', async () => {
    const probe = stubPrometheus()
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('docker'))
    render(<App />)

    await screen.findByText(/Docker 환경은 관측 대시보드가 아직 없습니다/)
    expect(probe).not.toHaveBeenCalled()
  })

  it('활성 미션이 없으면 학습 대시보드를 띄우고 probe 를 돌리지 않는다', async () => {
    const probe = stubPrometheus()
    mocked.getEnvironments.mockResolvedValue([K8S])
    render(<App />)

    await screen.findByRole('tablist')
    expect(screen.getByText('PROFILE / LEARNING DASHBOARD')).toBeTruthy()
    expect(probe).not.toHaveBeenCalled()
  })
})

describe('capabilities 기반 기능 게이팅 (FE-22)', () => {
  const stubPrometheus = () => {
    const probe = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'success', data: { result: [{ value: [0, '1'] }] } }),
    })) as unknown as typeof fetch
    vi.stubGlobal('fetch', probe)
    return vi.mocked(probe)
  }

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const withCapabilities = (capabilities: string[]): EnvironmentItem => ({
    id: 'kubernetes',
    status: 'available',
    capabilities,
  })

  it('observability 를 광고하지 않으면 대시보드가 있는 환경에서도 iframe 을 열지 않는다', async () => {
    /*
     * Kubernetes 는 유일하게 Grafana 대시보드가 있는 환경이다. 그래도 서버가
     * 관측을 광고하지 않으면 빈 대시보드를 보여주는 셈이라 열지 않는다.
     */
    const probe = stubPrometheus()
    mocked.getEnvironments.mockResolvedValue([
      withCapabilities(['static_mission', 'ai_scenario', 'terminal', 'tutor']),
    ])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    render(<App />)

    // 이유가 "대시보드가 없다"가 아니라 "서버가 관측을 제공하지 않는다"로 나온다.
    expect(await screen.findByText(/Kubernetes 환경은 관측 데이터를 제공하지 않습니다/)).toBeTruthy()
    expect(screen.queryByTitle(/Grafana dashboard/)).toBeNull()
    expect(probe).not.toHaveBeenCalled()
  })

  it('대시보드가 없는 환경의 문구는 그대로 유지된다 — 두 이유를 섞지 않는다', async () => {
    stubPrometheus()
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('docker'))
    render(<App />)

    expect(await screen.findByText(/Docker 환경은 관측 대시보드가 아직 없습니다/)).toBeTruthy()
    expect(screen.queryByText(/관측 데이터를 제공하지 않습니다/)).toBeNull()
  })

  it('terminal 을 광고하지 않으면 세션 로딩 대신 이유를 알린다', async () => {
    mocked.getEnvironments.mockResolvedValue([
      withCapabilities(['static_mission', 'ai_scenario', 'tutor', 'observability']),
    ])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    render(<App />)

    expect(await screen.findByText(/Kubernetes 환경은 터미널을 제공하지 않습니다/)).toBeTruthy()
    // 실패할 세션을 만들지 않는다.
    expect(mocked.createTerminalSession).not.toHaveBeenCalled()
  })

  it('capabilities 가 빈 배열이면 작업 화면 대신 준비 중 안내를 띄운다', async () => {
    // 빈 배열은 서버가 "없다"고 말한 것이다. 화면을 그리면 누르는 것마다 거절당한다.
    mocked.getEnvironments.mockResolvedValue([withCapabilities([])])
    render(<App />)

    await screen.findByRole('tablist')
    expect(screen.getByText(/Kubernetes 환경은 아직 준비 중입니다/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: '미션' })).toBeNull()
  })

  it('계약에 없는 capability 가 섞여 와도 아는 기능은 그대로 동작한다', async () => {
    stubPrometheus()
    mocked.getEnvironments.mockResolvedValue([
      withCapabilities([...ALL_CAPABILITIES, 'quantum_debugger']),
    ])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    render(<App />)

    expect(await screen.findByTitle('Kubernetes Grafana dashboard')).toBeTruthy()
  })

  it('응답에 capabilities 가 아예 없으면 아무것도 숨기지 않는다', async () => {
    /*
     * 판정 근거가 없는 것을 "없다"로 읽으면 계약이 안 맞는 배포에서 화면이 통째로
     * 사라진다. capabilities 는 광고이고 관문은 백엔드 assert_implemented 다.
     */
    stubPrometheus()
    mocked.getEnvironments.mockResolvedValue([
      { id: 'kubernetes', status: 'available' } as EnvironmentItem,
    ])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    render(<App />)

    expect(await screen.findByTitle('Kubernetes Grafana dashboard')).toBeTruthy()
  })
})

describe('환경별 field guide (FE-09)', () => {
  const openTerminalTab = async () => {
    await screen.findByRole('tablist')
    fireEvent.click(screen.getByRole('button', { name: '터미널' }))
  }

  it('Linux 탭에서는 kubectl / docker 가이드가 섞이지 않는다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE, LINUX_AVAILABLE])
    localStorage.setItem('afterfail:environment:v1:user-1', 'linux')
    render(<App />)

    await openTerminalTab()
    const guide = await screen.findByText('INVESTIGATION STARTERS')
    const commands = guide.parentElement as HTMLElement

    expect(commands.textContent).toContain('ps aux')
    expect(commands.textContent).not.toContain('kubectl')
    expect(commands.textContent).not.toContain('docker ')
  })

  it('Docker 탭에서는 docker 조사 명령을 안내한다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    localStorage.setItem('afterfail:environment:v1:user-1', 'docker')
    render(<App />)

    await openTerminalTab()
    const guide = await screen.findByText('INVESTIGATION STARTERS')
    const commands = guide.parentElement as HTMLElement

    expect(commands.textContent).toContain('docker ps -a')
    expect(commands.textContent).not.toContain('kubectl')
  })

  it('Kubernetes 탭은 기존 kubectl 안내를 유지한다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S, DOCKER_AVAILABLE])
    render(<App />)

    await openTerminalTab()
    const guide = await screen.findByText('INVESTIGATION STARTERS')
    const commands = guide.parentElement as HTMLElement

    expect(commands.textContent).toContain('kubectl get pods')
    expect(commands.textContent).not.toContain('docker ')
  })
})

describe('모바일 탭 전환 (FE-17)', () => {
  it('미션/터미널을 오가도 Terminal 을 unmount 하지 않아 연결이 유지된다', async () => {
    mocked.getEnvironments.mockResolvedValue([K8S])
    mocked.getMissionStatus.mockResolvedValue(activeMissionStatus('kubernetes'))
    render(<App />)

    const stub = await screen.findByTestId('terminal-stub')
    const sessionId = stub.getAttribute('data-session-id')

    // 미션 화면으로 전환 — CSS 로 숨기고 unmount 하지 않는다.
    fireEvent.click(screen.getByRole('button', { name: '미션' }))
    const afterMissions = screen.getByTestId('terminal-stub')
    expect(afterMissions.getAttribute('data-session-id')).toBe(sessionId)

    fireEvent.click(screen.getByRole('button', { name: '터미널' }))
    expect(screen.getByTestId('terminal-stub').getAttribute('data-session-id')).toBe(sessionId)

    // 다시 마운트됐다면 세션을 또 만들었을 것이다.
    expect(mocked.createTerminalSession).toHaveBeenCalledTimes(1)
  })
})
