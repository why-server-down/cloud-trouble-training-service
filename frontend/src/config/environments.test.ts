import { describe, expect, it } from 'vitest'

import {
  ENVIRONMENT_CAPABILITIES,
  ENVIRONMENT_IDS,
  ENVIRONMENT_STATUSES,
  EnvironmentItem,
  isAttemptType,
  isEnvironmentId,
  isEnvironmentStatus,
} from '../types/training'
import {
  capabilityList,
  ENVIRONMENT_META,
  ENVIRONMENT_OBSERVABILITY,
  ENVIRONMENT_ORDER,
  ENVIRONMENT_ROADMAP,
  escapePrometheusLabelValue,
  getGrafanaDataProbeUrl,
  getGrafanaUrl,
  hasCapability,
  hasObservabilityDashboard,
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

describe('환경별 관측 설정 (FE-08)', () => {
  it('모든 EnvironmentId 에 관측 설정 키가 있다', () => {
    expect(Object.keys(ENVIRONMENT_OBSERVABILITY).sort()).toEqual([...ENVIRONMENT_IDS].sort())
  })

  it('Kubernetes 대시보드 URL 에 환경의 scope 변수가 실린다', () => {
    const url = getGrafanaUrl('kubernetes', 'afterfail-abc')
    expect(url).toContain('/d/k8s-survival-overview/')
    expect(url).toContain('var-namespace=afterfail-abc')
    expect(url).toContain('kiosk')
  })

  it('namespace 가 없으면 전체를 뜻하는 matcher 로 대체한다', () => {
    expect(getGrafanaUrl('kubernetes', null)).toContain(`var-namespace=${encodeURIComponent('.*')}`)
  })

  it('대시보드가 없는 환경은 URL 대신 null 을 준다 — 다른 환경 대시보드로 대체하지 않는다', () => {
    expect(getGrafanaUrl('docker', 'afterfail-abc')).toBeNull()
    expect(getGrafanaUrl('linux', 'afterfail-abc')).toBeNull()
    expect(hasObservabilityDashboard('docker')).toBe(false)
    expect(hasObservabilityDashboard('linux')).toBe(false)
    expect(hasObservabilityDashboard('kubernetes')).toBe(true)
    expect(hasObservabilityDashboard(null)).toBe(false)
  })

  it('대시보드가 없는 환경은 probe URL 도 없다 — polling 을 시작할 근거가 사라진다', () => {
    expect(getGrafanaDataProbeUrl('docker', 'afterfail-abc')).toBeNull()
    expect(getGrafanaDataProbeUrl('linux', 'afterfail-abc')).toBeNull()
    expect(getGrafanaDataProbeUrl('kubernetes', 'afterfail-abc')).toContain('/api/v1/query?query=')
  })

  it('probe 쿼리에 scope 가 escape 되어 들어간다', () => {
    const url = getGrafanaDataProbeUrl('kubernetes', 'ns"injected') as string
    const query = decodeURIComponent(url.split('query=')[1])
    expect(query).toBe('sum(kube_pod_status_phase{namespace=~"ns\\"injected"})')
  })

  it('escape 는 백슬래시와 큰따옴표만 다룬다', () => {
    expect(escapePrometheusLabelValue('a"b')).toBe('a\\"b')
    expect(escapePrometheusLabelValue('a\\b')).toBe('a\\\\b')
    expect(escapePrometheusLabelValue('afterfail-abc')).toBe('afterfail-abc')
  })
})

describe('기능 광고(capabilities) 판정 (FE-22)', () => {
  const item = (capabilities?: string[]): EnvironmentItem =>
    ({ id: 'kubernetes', status: 'available', capabilities }) as EnvironmentItem

  it('계약에 있는 capability 만 남기고 모르는 문자열은 버린다', () => {
    expect(capabilityList(item(['tutor', 'quantum_debugger', 'terminal']))).toEqual([
      'tutor',
      'terminal',
    ])
  })

  it('응답에 capabilities 가 없으면 null 이다 — 빈 배열과 구분한다', () => {
    // 이 구분이 판정의 전부다. 섞으면 계약이 안 맞는 배포에서 화면이 통째로 사라진다.
    expect(capabilityList(item(undefined))).toBeNull()
    expect(capabilityList(null)).toBeNull()
    expect(capabilityList(item([]))).toEqual([])
  })

  it('배열이 아닌 값이 와도 던지지 않고 null 로 본다', () => {
    expect(capabilityList({ id: 'kubernetes', status: 'available', capabilities: 'tutor' } as unknown as EnvironmentItem)).toBeNull()
  })

  it('판정 근거가 없으면(null) 아무것도 막지 않는다', () => {
    for (const capability of ENVIRONMENT_CAPABILITIES) {
      expect(hasCapability(null, capability), capability).toBe(true)
    }
  })

  it('빈 배열이면 전부 막는다 — 서버가 명시적으로 없다고 말한 것이다', () => {
    for (const capability of ENVIRONMENT_CAPABILITIES) {
      expect(hasCapability([], capability), capability).toBe(false)
    }
  })

  it('목록에 있는 것만 통과시킨다', () => {
    expect(hasCapability(['tutor'], 'tutor')).toBe(true)
    expect(hasCapability(['tutor'], 'observability')).toBe(false)
  })

  it('observability capability 는 Grafana 대시보드 유무와 다른 사실이다', () => {
    /*
     * 백엔드는 세 환경 모두 observability 를 광고하지만 대시보드는 k8s 것 하나뿐이다.
     * capability 로 갈음하면 Docker/Linux 에서 Grafana 404 를 보여준다.
     */
    expect(hasCapability(['observability'], 'observability')).toBe(true)
    expect(hasObservabilityDashboard('docker')).toBe(false)
    expect(hasObservabilityDashboard('linux')).toBe(false)
    expect(hasObservabilityDashboard('kubernetes')).toBe(true)
  })
})
