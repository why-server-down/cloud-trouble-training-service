import { LearningCurveEntry } from '../services/api'

/** 초를 사람이 읽는 분/초로 (FE-13 인수 조건). */
export const formatDuration = (seconds: number): string => {
  const safe = Number.isFinite(seconds) && seconds > 0 ? Math.round(seconds) : 0
  const minutes = Math.floor(safe / 60)
  return minutes > 0 ? `${minutes}분 ${safe % 60}초` : `${safe}초`
}

/**
 * 레이더 좌표 (FE-14).
 *
 * 축 개수를 받아 일반화했다. 3축(환경 역량)과 4축(스킬)을 같은 함수로 그린다.
 * 값이 유한하지 않으면 0 으로 접는다 — NaN 좌표가 하나라도 들어간 polygon 은
 * 브라우저가 조용히 통째로 렌더하지 않는다.
 */
export const radarPoint = (
  index: number,
  value: number | null | undefined,
  axisCount: number,
  radius = 72,
): string => {
  const safeAxes = axisCount > 0 ? axisCount : 1
  const safeValue = Number.isFinite(value) ? Math.max(0, Math.min(100, Number(value))) : 0
  const angle = -Math.PI / 2 + index * ((Math.PI * 2) / safeAxes)
  const distance = radius * (safeValue / 100)
  return `${100 + Math.cos(angle) * distance},${100 + Math.sin(angle) * distance}`
}

export const radarPolygon = (
  values: readonly (number | null | undefined)[],
  radius?: number,
): string => values.map((value, index) => radarPoint(index, value, values.length, radius)).join(' ')

/** 학습 곡선 좌표. 항목이 0개면 빈 문자열, 1개면 왼쪽 끝에 고정한다 (FE-14). */
export const curvePolyline = (entries: readonly LearningCurveEntry[]): string => {
  if (entries.length === 0) return ''

  const times = entries.map((entry) =>
    Number.isFinite(entry.completion_time) ? entry.completion_time : 0,
  )
  const maxTime = Math.max(...times, 1)

  return entries
    .map((_, index) => {
      const x = entries.length === 1 ? 10 : 10 + (index / (entries.length - 1)) * 280
      const y = 95 - (times[index] / maxTime) * 75
      return `${x},${y}`
    })
    .join(' ')
}

/**
 * 평균값. 완료가 0건이면 null 이다 (FE-13).
 * 0 으로 위조하면 "아직 안 했다"와 "0점을 받았다"가 구분되지 않는다.
 */
export const average = (total: number, count: number): number | null =>
  count > 0 ? Math.round(total / count) : null
