import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import MissionList from './MissionList'
import * as api from '../../services/api'
import { MissionAttemptResponse, MissionResponse, ScenarioStatusResponse } from '../../types/training'

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

const renderList = () => {
  const onActiveAttemptChange = vi.fn()
  render(
    <MissionList
      token="test-token"
      storageScope="user-1"
      environment="kubernetes"
      onActiveAttemptChange={onActiveAttemptChange}
    />,
  )
  return { onActiveAttemptChange }
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
