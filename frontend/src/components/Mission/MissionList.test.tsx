import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import MissionList from './MissionList'
import * as api from '../../services/api'
import {
  EnvironmentId,
  MissionAttemptResponse,
  MissionResponse,
  ScenarioStatusResponse,
} from '../../types/training'

vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof api>()
  return {
    ...actual,
    listMissions: vi.fn(),
    getMissionStatus: vi.fn(),
    getScenarioStatus: vi.fn(),
    getUnlockStatus: vi.fn(),
    abandonMission: vi.fn(),
  }
})

const mocked = vi.mocked(api)
const STORAGE_KEY = 'activeAttemptType:user-1'

const mission: MissionResponse = {
  id: 'mission-1',
  name: 'pod_failure',
  level: 1,
  description: '설명',
  chaos_type: 'pod_failure',
  environment: 'kubernetes',
  base_score: 100,
  time_limit: 1200,
  hint_penalty: 5,
  is_unlocked: true,
}

const attempt: MissionAttemptResponse = {
  id: 'attempt-1',
  user_id: 'user-1',
  mission_id: 'mission-1',
  attempt_type: 'static_mission',
  scenario_id: null,
  environment: 'kubernetes',
  status: 'in_progress',
  start_time: '2026-08-28T00:00:00Z',
  end_time: null,
  final_score: null,
  hints_used: 0,
}

const scenarioStatus: ScenarioStatusResponse = {
  scenario_id: 'scenario-1',
  attempt_id: 'attempt-2',
  title: '서버가 계속 재시작됩니다',
  difficulty: 'beginner',
  environment: 'kubernetes',
  student_brief: '조사해 보세요',
  elapsed_seconds: 10,
  remaining_seconds: 890,
  current_score: 80,
  hints_used: 0,
  status: 'in_progress',
}

const notFound = () => Promise.reject(new api.ApiError('없음', 404))

const renderList = (environment: EnvironmentId = 'kubernetes') => {
  const onActiveAttemptChange = vi.fn()
  const view = render(
    <MissionList
      token="test-token"
      storageScope="user-1"
      environment={environment}
      onActiveAttemptChange={onActiveAttemptChange}
    />,
  )
  const switchTo = (next: EnvironmentId) =>
    view.rerender(
      <MissionList
        token="test-token"
        storageScope="user-1"
        environment={next}
        onActiveAttemptChange={onActiveAttemptChange}
      />,
    )
  return { onActiveAttemptChange, switchTo }
}

beforeEach(() => {
  localStorage.clear()
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
  mocked.listMissions.mockResolvedValue([mission])
  mocked.getMissionStatus.mockImplementation(notFound)
  mocked.getScenarioStatus.mockImplementation(notFound)
  mocked.getUnlockStatus.mockResolvedValue({ unlocked: false, completed_static: 0, total_static: 4 })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('활성 시도 요약 (FE-05)', () => {
  it('서버에 활성 attempt 가 없으면 stale localStorage 값을 지우고 null 을 올린다', async () => {
    localStorage.setItem(STORAGE_KEY, 'ai_scenario')
    const { onActiveAttemptChange } = renderList()

    await waitFor(() => expect(onActiveAttemptChange).toHaveBeenCalledWith(null))
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('localStorage 힌트가 없어도 서버 status 로 활성 미션을 복원한다', async () => {
    mocked.getMissionStatus.mockResolvedValue({
      attempt,
      elapsed_seconds: 10,
      remaining_seconds: 1190,
      current_score: 100,
    })
    const { onActiveAttemptChange } = renderList()

    await waitFor(() =>
      expect(onActiveAttemptChange).toHaveBeenCalledWith({
        attemptId: 'attempt-1',
        attemptType: 'static_mission',
        environment: 'kubernetes',
        status: 'in_progress',
      }),
    )
    // 복원된 종류를 다음 조회 순서 힌트로 다시 저장한다.
    expect(localStorage.getItem(STORAGE_KEY)).toBe('static_mission')
  })

  it('힌트가 ai_scenario 면 시나리오를 먼저 조회하고 미션 상태는 건너뛴다', async () => {
    localStorage.setItem(STORAGE_KEY, 'ai_scenario')
    mocked.getScenarioStatus.mockResolvedValue(scenarioStatus)
    const { onActiveAttemptChange } = renderList()

    await waitFor(() =>
      expect(onActiveAttemptChange).toHaveBeenCalledWith({
        attemptId: 'attempt-2',
        attemptType: 'ai_scenario',
        environment: 'kubernetes',
        status: 'in_progress',
      }),
    )
    expect(mocked.getMissionStatus).not.toHaveBeenCalled()
  })

  it('미션을 포기하면 즉시 null 을 올려 탭 잠금을 해제한다', async () => {
    mocked.getMissionStatus.mockResolvedValue({
      attempt,
      elapsed_seconds: 10,
      remaining_seconds: 1190,
      current_score: 100,
    })
    // 포기 후에는 서버에 활성 attempt 가 남지 않는다.
    mocked.abandonMission.mockImplementation(async () => {
      mocked.getMissionStatus.mockImplementation(notFound)
      return { ...attempt, status: 'abandoned' }
    })

    const { onActiveAttemptChange } = renderList()
    await waitFor(() => expect(onActiveAttemptChange).toHaveBeenCalled())

    fireEvent.click(await screen.findByRole('button', { name: '미션 포기' }))
    fireEvent.click(await screen.findByRole('button', { name: '포기' }))

    await waitFor(() => expect(onActiveAttemptChange).toHaveBeenLastCalledWith(null))
    expect(mocked.abandonMission).toHaveBeenCalledTimes(1)
  })
})

const dockerMission: MissionResponse = {
  ...mission,
  id: 'mission-docker-1',
  name: '컨테이너가 계속 죽습니다',
  chaos_type: 'container_crash',
  environment: 'docker',
}

describe('환경별 미션 (FE-06)', () => {
  it('선택한 환경을 그대로 조회에 넘긴다', async () => {
    renderList('docker')

    await waitFor(() =>
      expect(mocked.listMissions).toHaveBeenCalledWith(
        'test-token',
        'docker',
        expect.any(AbortSignal),
      ),
    )
  })

  it('환경이 바뀌면 이전 미션 조회를 실제로 취소한다 (FE-18)', async () => {
    const { switchTo } = renderList('kubernetes')

    await waitFor(() => expect(mocked.listMissions).toHaveBeenCalledTimes(1))
    const firstSignal = mocked.listMissions.mock.calls[0][2] as AbortSignal
    expect(firstSignal.aborted).toBe(false)

    switchTo('docker')

    // signal 을 넘기는 것만으로는 부족하다. 실제로 끊겨야 늦게 온 응답이 버려진다.
    await waitFor(() => expect(firstSignal.aborted).toBe(true))
    await waitFor(() =>
      expect(mocked.listMissions).toHaveBeenCalledWith(
        'test-token',
        'docker',
        expect.any(AbortSignal),
      ),
    )
  })

  it('카드에 환경을 글자로 표시한다', async () => {
    mocked.listMissions.mockResolvedValue([dockerMission])
    renderList('docker')

    expect(await screen.findByText('Docker')).toBeTruthy()
  })

  it('늦게 도착한 이전 환경 응답이 현재 환경 화면을 덮지 않는다', async () => {
    let resolveKubernetes!: (value: MissionResponse[]) => void
    mocked.listMissions.mockReturnValueOnce(
      new Promise<MissionResponse[]>((resolve) => {
        resolveKubernetes = resolve
      }),
    )
    const { switchTo } = renderList('kubernetes')

    mocked.listMissions.mockResolvedValue([dockerMission])
    switchTo('docker')
    expect(await screen.findByText('컨테이너가 계속 죽습니다')).toBeTruthy()

    // 끊긴 Kubernetes 요청이 뒤늦게 응답해도 Docker 목록을 밀어내면 안 된다.
    await act(async () => {
      resolveKubernetes([mission])
    })

    expect(screen.getByText('컨테이너가 계속 죽습니다')).toBeTruthy()
    expect(screen.queryByText('사라진 애플리케이션')).toBeNull()
  })

  it('환경을 바꾸면 이전 목록을 즉시 비운다', async () => {
    const { switchTo } = renderList('kubernetes')
    expect(await screen.findByText('사라진 애플리케이션')).toBeTruthy()

    mocked.listMissions.mockReturnValue(new Promise<MissionResponse[]>(() => {}))
    switchTo('docker')

    expect(screen.queryByText('사라진 애플리케이션')).toBeNull()
    expect(screen.getByText('미션을 불러오는 중...')).toBeTruthy()
  })

  it('미션이 0건이면 조회 실패가 아니라 준비 중으로 알린다', async () => {
    mocked.listMissions.mockResolvedValue([])
    renderList('docker')

    expect(await screen.findByText(/Docker 미션은 아직 준비 중입니다/)).toBeTruthy()
  })

  it('조회에 실패하면 준비 중과 구분되는 문구를 보여준다', async () => {
    mocked.listMissions.mockRejectedValue(new Error('네트워크 오류'))
    renderList('docker')

    expect(await screen.findByText(/미션 목록을 불러오지 못했습니다/)).toBeTruthy()
    expect(screen.queryByText(/준비 중입니다/)).toBeNull()
  })

  it('다른 환경 미션이 섞여 온 계약 오류는 원인을 그대로 보여준다', async () => {
    mocked.listMissions.mockRejectedValue(
      new api.ApiError('미션 목록 응답에 요청한 환경(docker)이 아닌 kubernetes 미션이 섞여 있습니다', 502),
    )
    renderList('docker')

    expect(await screen.findByText(/kubernetes 미션이 섞여 있습니다/)).toBeTruthy()
  })

  it('AI 잠금 안내가 계정 단위임을 밝힌다', async () => {
    renderList('kubernetes')

    expect(await screen.findByText(/계정 단위로 열립니다/)).toBeTruthy()
  })
})
