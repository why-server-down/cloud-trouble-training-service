import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ApiError,
  createTerminalSession,
  deleteTerminalSession,
  getEnvironments,
  getMissionStatus,
  listMissions,
  startRandomScenario,
} from './api'

const TOKEN = 'test-token'

/** fetch 를 한 번만 응답하도록 세워두고, 호출 인자를 되돌려준다. */
const stubFetchOnce = (payload: unknown, init: { ok?: boolean; status?: number } = {}) => {
  const fetchMock = vi.fn(async () => ({
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => payload,
  }))

  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const requestBodyOf = (fetchMock: ReturnType<typeof stubFetchOnce>) => {
  const [, requestInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
  return JSON.parse(String(requestInit.body))
}

const scenarioPayload = (environment: unknown) => ({
  scenario_id: 'scenario-1',
  title: '테스트 시나리오',
  difficulty: 'beginner',
  environment,
  student_brief: '조사해 보세요',
  time_limit_seconds: 600,
  base_score: 100,
  hint_penalty: 10,
  safety_status: 'accepted',
})

const missionPayload = (environment?: unknown) => {
  const mission: Record<string, unknown> = {
    id: 'mission-1',
    name: 'pod_failure',
    level: 1,
    description: '설명',
    chaos_type: 'pod_failure',
    base_score: 100,
    time_limit: 600,
    hint_penalty: 10,
    is_unlocked: true,
  }
  if (environment !== undefined) mission.environment = environment
  return mission
}

const statusPayload = (environment: unknown) => ({
  attempt: {
    id: 'attempt-1',
    user_id: 'user-1',
    mission_id: 'mission-1',
    attempt_type: 'static_mission',
    scenario_id: null,
    environment,
    status: 'in_progress',
    start_time: '2026-08-27T00:00:00Z',
    end_time: null,
    final_score: null,
    hints_used: 0,
  },
  elapsed_seconds: 10,
  remaining_seconds: 590,
  current_score: 100,
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('startRandomScenario', () => {
  it('요청 body 에 선택한 environment 를 담아 보낸다', async () => {
    const fetchMock = stubFetchOnce(scenarioPayload('docker'))

    await startRandomScenario(TOKEN, 'advanced', 'docker', true)

    expect(requestBodyOf(fetchMock)).toEqual({
      difficulty: 'advanced',
      environment: 'docker',
      randomize: true,
      demo_unlock: true,
    })
  })

  it('demoUnlock 을 생략해도 environment 는 그대로 실린다', async () => {
    const fetchMock = stubFetchOnce(scenarioPayload('kubernetes'))

    await startRandomScenario(TOKEN, 'beginner', 'kubernetes')

    expect(requestBodyOf(fetchMock)).toMatchObject({ environment: 'kubernetes', demo_unlock: false })
  })

  it('응답 environment 가 계약 밖 값이면 API 오류로 올린다', async () => {
    stubFetchOnce(scenarioPayload('windows'))

    await expect(startRandomScenario(TOKEN, 'beginner', 'kubernetes')).rejects.toThrowError(ApiError)
    await expect(startRandomScenario(TOKEN, 'beginner', 'kubernetes')).rejects.toThrowError(/windows/)
  })
})

describe('listMissions', () => {
  it('선택한 environment 를 query 로 보낸다', async () => {
    const fetchMock = stubFetchOnce([missionPayload('docker')])

    await listMissions(TOKEN, 'docker')

    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toContain('/api/missions/?environment=docker')
  })

  it('AbortSignal 을 그대로 fetch 에 넘긴다', async () => {
    const fetchMock = stubFetchOnce([missionPayload('kubernetes')])
    const controller = new AbortController()

    await listMissions(TOKEN, 'kubernetes', controller.signal)

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.signal).toBe(controller.signal)
  })

  it('미션마다 environment 를 검증해 그대로 통과시킨다', async () => {
    stubFetchOnce([missionPayload('kubernetes')])

    const missions = await listMissions(TOKEN, 'kubernetes')

    expect(missions[0].environment).toBe('kubernetes')
  })

  it('environment 필드가 없는 구버전 응답은 kubernetes 로 폴백한다', async () => {
    stubFetchOnce([missionPayload()])

    const missions = await listMissions(TOKEN, 'kubernetes')

    expect(missions[0].environment).toBe('kubernetes')
  })

  it('한 건이라도 잘못된 environment 면 오류로 올린다', async () => {
    stubFetchOnce([missionPayload('kubernetes'), missionPayload('k8s')])

    await expect(listMissions(TOKEN, 'kubernetes')).rejects.toThrowError(/k8s/)
  })

  it('요청한 환경이 아닌 미션이 섞여 오면 걸러내지 않고 계약 오류로 올린다', async () => {
    stubFetchOnce([missionPayload('docker'), missionPayload('kubernetes')])

    await expect(listMissions(TOKEN, 'docker')).rejects.toBeInstanceOf(ApiError)
    await expect(listMissions(TOKEN, 'docker')).rejects.toThrowError(/kubernetes/)
  })
})

describe('getMissionStatus', () => {
  it('중첩된 attempt.environment 도 검증한다', async () => {
    stubFetchOnce(statusPayload('kubernetes'))

    const status = await getMissionStatus(TOKEN)

    expect(status.attempt.environment).toBe('kubernetes')
  })

  it('attempt.environment 가 잘못되면 404 가 아닌 오류로 올린다', async () => {
    stubFetchOnce(statusPayload(''))

    // MissionStatus 컴포넌트는 404 만 "미션 종료"로 처리하므로, 계약 위반이
    // 미션 종료로 오해되지 않는지까지 확인한다.
    await expect(getMissionStatus(TOKEN)).rejects.toMatchObject({ status: 502 })
  })
})

describe('getEnvironments', () => {
  it('서버가 준 환경 목록을 그대로 돌려준다', async () => {
    stubFetchOnce({
      items: [
        { id: 'kubernetes', status: 'available', capabilities: ['terminal'] },
        { id: 'docker', status: 'preparing', capabilities: [] },
      ],
    })

    const items = await getEnvironments(TOKEN)

    expect(items.map((item) => item.id)).toEqual(['kubernetes', 'docker'])
    expect(items[0].capabilities).toContain('terminal')
  })

  it('프론트가 모르는 환경은 건너뛰되 나머지는 살린다', async () => {
    stubFetchOnce({
      items: [
        { id: 'kubernetes', status: 'available', capabilities: [] },
        { id: 'windows', status: 'available', capabilities: [] },
      ],
    })

    const items = await getEnvironments(TOKEN)

    // 목록에 모르는 환경이 있어도 이미 열린 환경의 훈련이 멈추면 안 된다.
    expect(items.map((item) => item.id)).toEqual(['kubernetes'])
  })

  it('items 가 배열이 아니면 계약 오류로 올린다', async () => {
    stubFetchOnce({ items: null })

    await expect(getEnvironments(TOKEN)).rejects.toMatchObject({ status: 502 })
  })
})

describe('createTerminalSession', () => {
  const sessionPayload = (environment: unknown) => ({
    id: 'session-1',
    namespace: 'user-abc',
    environment,
    created_at: '2026-08-29T00:00:00Z',
    is_active: true,
  })

  it('요청 body 에 environment 를 담아 보낸다', async () => {
    const fetchMock = stubFetchOnce(sessionPayload('docker'))

    const session = await createTerminalSession(TOKEN, 'docker')

    expect(requestBodyOf(fetchMock)).toEqual({ environment: 'docker' })
    expect(session.environment).toBe('docker')
  })

  it('environment 가 없는 구버전 응답은 kubernetes 로 폴백한다', async () => {
    stubFetchOnce({ id: 'session-1', namespace: 'user-abc', created_at: 'x', is_active: true })

    expect((await createTerminalSession(TOKEN, 'kubernetes')).environment).toBe('kubernetes')
  })

  it('응답 environment 가 계약 밖 값이면 API 오류로 올린다', async () => {
    stubFetchOnce(sessionPayload('windows'))

    await expect(createTerminalSession(TOKEN, 'kubernetes')).rejects.toBeInstanceOf(ApiError)
  })

  it('실패 응답은 오류로 올린다', async () => {
    stubFetchOnce({ detail: '샌드박스를 준비하지 못했습니다' }, { ok: false, status: 503 })

    await expect(createTerminalSession(TOKEN, 'kubernetes')).rejects.toThrow(
      '샌드박스를 준비하지 못했습니다',
    )
  })
})

describe('deleteTerminalSession', () => {
  it('DELETE 로 세션 id 경로를 호출한다', async () => {
    const fetchMock = stubFetchOnce(null, { status: 204 })

    expect(await deleteTerminalSession(TOKEN, 'session-1')).toBe(true)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/api/terminal/sessions/session-1')
    expect(init.method).toBe('DELETE')
  })

  it('서버가 실패해도 예외를 던지지 않는다', async () => {
    stubFetchOnce({ detail: '없음' }, { ok: false, status: 404 })

    expect(await deleteTerminalSession(TOKEN, 'session-1')).toBe(false)
  })

  it('네트워크 오류도 삼킨다 — 로그아웃 흐름을 막지 않는다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))

    expect(await deleteTerminalSession(TOKEN, 'session-1')).toBe(false)
  })
})
