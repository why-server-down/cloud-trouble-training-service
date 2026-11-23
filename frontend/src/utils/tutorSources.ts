/**
 * 근거 경로를 링크로 만들어도 되는지 (FE-11).
 *
 * 백엔드 `TutorSource.path` 는 지식 베이스 내부 경로일 수 있고, `javascript:`
 * 같은 스킴이 섞여 들어오면 클릭 한 번에 스크립트가 돈다. 그래서 http/https
 * 절대 URL 만 anchor 로 만들고 나머지는 텍스트로 보여준다 —
 * "임의의 외부 링크로 만들지 않는다"는 계약을 코드로 못 박는다.
 */
export const getSafeSourceHref = (path: string | null | undefined): string | null => {
  if (!path) return null

  try {
    const url = new URL(path)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.toString() : null
  } catch {
    // 절대 URL 이 아니다 → 내부 경로다. 링크로 만들지 않는다.
    return null
  }
}
