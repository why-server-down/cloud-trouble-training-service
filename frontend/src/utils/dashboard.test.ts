import { describe, expect, it } from 'vitest'

import { average, curvePolyline, formatDuration, radarPoint, radarPolygon } from './dashboard'
import { LearningCurveEntry } from '../services/api'

const entry = (overrides: Partial<LearningCurveEntry> = {}): LearningCurveEntry => ({
  attempt_id: 'a',
  mission_id: 'm',
  mission_name: '미션',
  attempt_number: 1,
  completion_time: 100,
  score: 90,
  hints_used: 0,
  completed_at: '2026-09-01T00:00:00Z',
  ...overrides,
})

/** 좌표 문자열을 숫자쌍으로 되돌린다. NaN 검사를 위해 필요하다. */
const coords = (points: string) =>
  points
    .split(' ')
    .filter(Boolean)
    .flatMap((pair) => pair.split(',').map(Number))

describe('MTTR 표시 (FE-13)', () => {
  it('초를 분/초로 읽어준다', () => {
    expect(formatDuration(0)).toBe('0초')
    expect(formatDuration(45)).toBe('45초')
    expect(formatDuration(60)).toBe('1분 0초')
    expect(formatDuration(185)).toBe('3분 5초')
  })

  it('음수와 NaN 은 0초로 접는다 — 화면에 NaN 을 내보내지 않는다', () => {
    expect(formatDuration(-10)).toBe('0초')
    expect(formatDuration(Number.NaN)).toBe('0초')
    expect(formatDuration(Number.POSITIVE_INFINITY)).toBe('0초')
  })
})

describe('평균 계산 (FE-13)', () => {
  it('완료가 0건이면 null 이다 — 0 으로 위조하지 않는다', () => {
    expect(average(0, 0)).toBeNull()
    expect(average(500, 0)).toBeNull()
  })

  it('완료가 있으면 반올림한 평균을 준다', () => {
    expect(average(300, 3)).toBe(100)
    expect(average(100, 3)).toBe(33)
  })
})

describe('레이더 좌표 (FE-14)', () => {
  it('3축과 4축을 같은 함수로 그린다', () => {
    expect(radarPolygon([50, 50, 50]).split(' ')).toHaveLength(3)
    expect(radarPolygon([50, 50, 50, 50]).split(' ')).toHaveLength(4)
  })

  it('4축은 기존 90도 배치를 유지한다', () => {
    // index 0 은 위쪽 꼭짓점: x = 100, y = 100 - radius * (value/100)
    const [x, y] = coords(radarPoint(0, 100, 4))
    expect(Math.round(x)).toBe(100)
    expect(Math.round(y)).toBe(28)
  })

  it('데이터가 0, 1, 3개여도 NaN 좌표가 생기지 않는다', () => {
    for (const values of [[], [50], [10, 20, 30]]) {
      for (const value of coords(radarPolygon(values))) {
        expect(Number.isNaN(value), `${values.length}축`).toBe(false)
      }
    }
  })

  it('null / undefined / NaN 값은 0 으로 접는다', () => {
    for (const value of coords(radarPolygon([null, undefined, Number.NaN]))) {
      expect(Number.isNaN(value)).toBe(false)
    }
    // 값이 0 이면 세 점 모두 중심이다.
    expect(radarPolygon([null, null, null])).toBe('100,100 100,100 100,100')
  })

  it('100 을 넘는 값은 100 으로 잘라 레이더 밖으로 나가지 않게 한다', () => {
    expect(radarPoint(0, 400, 4)).toBe(radarPoint(0, 100, 4))
  })

  it('축이 0개여도 나눗셈이 깨지지 않는다', () => {
    expect(() => radarPoint(0, 50, 0)).not.toThrow()
    expect(coords(radarPoint(0, 50, 0)).every((value) => !Number.isNaN(value))).toBe(true)
  })
})

describe('학습 곡선 좌표 (FE-14)', () => {
  it('항목이 없으면 빈 문자열이다', () => {
    expect(curvePolyline([])).toBe('')
  })

  it('항목이 1개면 왼쪽 끝에 고정하고 NaN 을 만들지 않는다', () => {
    const points = curvePolyline([entry()])
    expect(points.startsWith('10,')).toBe(true)
    expect(coords(points).every((value) => !Number.isNaN(value))).toBe(true)
  })

  it('완료 시간이 전부 0 이어도 NaN 이 되지 않는다', () => {
    const points = curvePolyline([
      entry({ attempt_id: '1', completion_time: 0 }),
      entry({ attempt_id: '2', completion_time: 0 }),
      entry({ attempt_id: '3', completion_time: 0 }),
    ])
    expect(coords(points).every((value) => !Number.isNaN(value))).toBe(true)
  })

  it('유효하지 않은 완료 시간은 0 으로 접는다', () => {
    const points = curvePolyline([
      entry({ attempt_id: '1', completion_time: Number.NaN }),
      entry({ attempt_id: '2', completion_time: 120 }),
    ])
    expect(coords(points).every((value) => !Number.isNaN(value))).toBe(true)
  })

  it('항목 수만큼 좌표를 만든다', () => {
    const points = curvePolyline([entry({ attempt_id: '1' }), entry({ attempt_id: '2' })])
    expect(points.split(' ')).toHaveLength(2)
  })
})
