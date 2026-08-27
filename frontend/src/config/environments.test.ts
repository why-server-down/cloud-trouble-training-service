import { describe, expect, it } from 'vitest'

import {
  ENVIRONMENT_IDS,
  ENVIRONMENT_STATUSES,
  isAttemptType,
  isEnvironmentId,
  isEnvironmentStatus,
} from '../types/training'
import {
  ENVIRONMENT_META,
  ENVIRONMENT_ORDER,
  ENVIRONMENT_ROADMAP,
  isSelectableStatus,
  statusNote,
} from './environments'

describe('환경 표시 설정', () => {
  it('모든 EnvironmentId 에 표시 메타가 있다', () => {
    for (const id of ENVIRONMENT_IDS) {
      expect(ENVIRONMENT_META[id]?.label, `${id} label 누락`).toBeTruthy()
      expect(ENVIRONMENT_META[id]?.subtitle, `${id} subtitle 누락`).toBeTruthy()
    }
  })

  it('표시 메타에 계약 밖의 환경이 섞여 있지 않다', () => {
    expect(Object.keys(ENVIRONMENT_META).sort()).toEqual([...ENVIRONMENT_IDS].sort())
  })

  it('탭 노출 순서가 백엔드 SUPPORTED_ENVIRONMENTS 순서와 같다', () => {
    expect(ENVIRONMENT_ORDER).toEqual(ENVIRONMENT_IDS)
  })
})

describe('isEnvironmentId', () => {
  it('계약에 있는 값만 통과시킨다', () => {
    for (const id of ENVIRONMENT_IDS) {
      expect(isEnvironmentId(id)).toBe(true)
    }
  })

  it('스코프 밖 문자열과 비문자열을 거절한다', () => {
    const rejected: unknown[] = [
      'application',
      'Kubernetes',
      'kubernetes ',
      '',
      null,
      undefined,
      0,
      {},
      ['kubernetes'],
    ]

    for (const value of rejected) {
      expect(isEnvironmentId(value), `${JSON.stringify(value)} 를 통과시켰다`).toBe(false)
    }
  })
})

describe('부가 type guard', () => {
  it('환경 상태는 UI 가 다루는 4개 값만 인정한다', () => {
    // 백엔드는 현재 available / preparing 만 내보내고, degraded / disabled 는
    // FE-03 요구사항에 따라 화면 처리만 먼저 갖춘 상태다.
    expect(isEnvironmentStatus('available')).toBe(true)
    expect(isEnvironmentStatus('preparing')).toBe(true)
    expect(isEnvironmentStatus('degraded')).toBe(true)
    expect(isEnvironmentStatus('disabled')).toBe(true)
    expect(isEnvironmentStatus('exploded')).toBe(false)
    expect(isEnvironmentStatus(null)).toBe(false)
  })

  it('시도 종류는 DB check 제약과 같은 두 값만 인정한다', () => {
    expect(isAttemptType('static_mission')).toBe(true)
    expect(isAttemptType('ai_scenario')).toBe(true)
    expect(isAttemptType('ai-scenario')).toBe(false)
    expect(isAttemptType(undefined)).toBe(false)
  })
})

describe('환경 상태 해석 (FE-03)', () => {
  it('available 과 degraded 만 선택 가능하다', () => {
    expect(isSelectableStatus('available')).toBe(true)
    expect(isSelectableStatus('degraded')).toBe(true)
    expect(isSelectableStatus('preparing')).toBe(false)
    expect(isSelectableStatus('disabled')).toBe(false)
  })

  it('모르는 status 는 선택 불가로 처리하고 문구로 드러낸다', () => {
    expect(isSelectableStatus('exploded')).toBe(false)
    expect(statusNote('exploded')).toBe('상태 확인 불가')
  })

  it('상태마다 사용자에게 보여줄 문구가 있다', () => {
    for (const status of ENVIRONMENT_STATUSES) {
      expect(statusNote(status).length, `${status} 문구 누락`).toBeGreaterThan(0)
    }
  })

  it('모든 EnvironmentId 에 로드맵 항목 키가 있다', () => {
    expect(Object.keys(ENVIRONMENT_ROADMAP).sort()).toEqual([...ENVIRONMENT_IDS].sort())
    // 아직 열리지 않은 환경은 무엇이 열릴지 보여줄 항목이 있어야 한다.
    expect(ENVIRONMENT_ROADMAP.docker.length).toBeGreaterThan(0)
    expect(ENVIRONMENT_ROADMAP.linux.length).toBeGreaterThan(0)
  })
})
