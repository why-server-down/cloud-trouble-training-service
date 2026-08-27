import { describe, expect, it } from 'vitest'

import {
  isAttemptType,
  isEnvironmentId,
  isEnvironmentStatus,
  ENVIRONMENT_IDS,
} from '../types/training'
import { ENVIRONMENT_META, ENVIRONMENT_ORDER } from './environments'

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
  it('환경 상태는 백엔드가 실제로 내보내는 값만 인정한다', () => {
    expect(isEnvironmentStatus('available')).toBe(true)
    expect(isEnvironmentStatus('preparing')).toBe(true)
    // 아직 백엔드 계약에 없는 값 — FE-03 에서 백엔드와 함께 추가한다.
    expect(isEnvironmentStatus('degraded')).toBe(false)
    expect(isEnvironmentStatus(null)).toBe(false)
  })

  it('시도 종류는 DB check 제약과 같은 두 값만 인정한다', () => {
    expect(isAttemptType('static_mission')).toBe(true)
    expect(isAttemptType('ai_scenario')).toBe(true)
    expect(isAttemptType('ai-scenario')).toBe(false)
    expect(isAttemptType(undefined)).toBe(false)
  })
})
