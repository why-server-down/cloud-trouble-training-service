import { AchievementItem, LearningCurveEntry } from '../services/api'

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

type AchievementText = Pick<AchievementItem, 'name' | 'description'>

/**
 * 업적 표시 문구 (FE-28). 서버는 영어 이름을 보내므로 id 로 한국어 문구를 고른다.
 * 모르는 id 는 서버 문구를 그대로 쓴다 — 새 업적이 생겨도 빈칸이 되지 않는다.
 */
const ACHIEVEMENT_TEXT: Record<string, AchievementText> = {
  'first-recovery': { name: '첫 복구', description: '미션을 처음으로 완료' },
  environmentalist: { name: '힌트 없이 해결', description: '힌트를 쓰지 않고 미션 완료' },
  'speed-runner': { name: '5분 안에 복구', description: '미션을 5분 안에 완료' },
  'persistent-resolver': {
    name: '끈질긴 해결사',
    description: '같은 미션을 10번 이상 시도한 끝에 완료',
  },
}

/** 숨은 업적은 달성 전까지 서버도 내용을 감춘다. 위 표가 그 내용을 새어 나가게 하면 안 된다. */
const HIDDEN_ACHIEVEMENT: AchievementText = {
  name: '숨은 업적',
  description: '계속 조사하면 드러납니다',
}

export const achievementText = (item: AchievementItem): AchievementText => {
  if (item.is_hidden && !item.unlocked) return HIDDEN_ACHIEVEMENT
  return ACHIEVEMENT_TEXT[item.id] ?? { name: item.name, description: item.description }
}
