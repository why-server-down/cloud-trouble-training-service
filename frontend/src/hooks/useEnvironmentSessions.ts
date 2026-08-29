import { useCallback, useEffect, useRef, useState } from 'react'

import { createTerminalSession, deleteTerminalSession } from '../services/api'
import { EnvironmentId, SessionResponse } from '../types/training'

/**
 * 환경별 터미널 세션 상태.
 *
 * `idle` 은 "아직 필요하지 않았다"는 뜻이다 — 로그인했다는 이유만으로
 * 세션을 만들지 않기 때문에, 선택되지 않은 환경은 계속 idle 로 남는다.
 */
export type EnvironmentSessionState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; session: SessionResponse }
  | { status: 'error'; message: string }

const IDLE: EnvironmentSessionState = { status: 'idle' }

type SessionStates = Partial<Record<EnvironmentId, EnvironmentSessionState>>
type SessionCache = Partial<Record<EnvironmentId, SessionResponse>>
type InFlight = Partial<Record<EnvironmentId, Promise<SessionResponse>>>

export interface UseEnvironmentSessions {
  /** ready 상태일 때만 세션을 돌려준다. 그 외에는 null 이다. */
  sessionOf: (environment: EnvironmentId | null) => SessionResponse | null
  stateOf: (environment: EnvironmentId | null) => EnvironmentSessionState
  /** 해당 환경 세션을 준비한다. 이미 있거나 만드는 중이면 아무것도 하지 않는다. */
  ensure: (environment: EnvironmentId) => void
  /** 실패한 환경을 다시 시도한다. */
  retry: (environment: EnvironmentId) => void
  /** 만들어 둔 세션을 서버에서 정리한다. 실패해도 예외를 올리지 않는다. */
  closeAll: () => Promise<void>
}

/**
 * 환경별 터미널 세션을 **지연 생성**하고 메모리에 캐시한다 (FE-04).
 *
 * 왜 훅으로 빼는가:
 * - 세션 생성은 백엔드에서 샌드박스 Pod readiness 를 기다리는 느린 호출이다.
 *   같은 환경에 대해 두 번 부르면 그 대기가 그대로 두 배가 된다.
 *   그래서 캐시(완료분)와 in-flight Promise(진행분)를 둘 다 들고 막는다.
 * - 토큰이 바뀌면(로그아웃·재로그인·만료) 이전 사용자의 세션이 남아 있으면 안 된다.
 *   generation 을 올려서, 이미 날아간 요청의 응답이 뒤늦게 도착해도 반영되지 않게 한다.
 */
export const useEnvironmentSessions = (token: string | null): UseEnvironmentSessions => {
  const [states, setStates] = useState<SessionStates>({})
  const cacheRef = useRef<SessionCache>({})
  const inFlightRef = useRef<InFlight>({})
  const generationRef = useRef(0)
  const tokenRef = useRef(token)

  const reset = useCallback(() => {
    generationRef.current += 1
    cacheRef.current = {}
    inFlightRef.current = {}
    setStates({})
  }, [])

  // 토큰이 실제로 바뀐 경우에만 비운다. 마운트나 StrictMode 재실행으로 비우면
  // 막 시작한 세션 생성이 버려지고 같은 환경을 두 번 만들게 된다.
  useEffect(() => {
    if (tokenRef.current === token) return
    tokenRef.current = token
    reset()
  }, [reset, token])

  const ensure = useCallback(
    (environment: EnvironmentId) => {
      if (!token) return
      if (cacheRef.current[environment] || inFlightRef.current[environment]) return

      const generation = generationRef.current
      const isStale = () => generation !== generationRef.current

      setStates((current) => ({ ...current, [environment]: { status: 'loading' } }))

      const pending = createTerminalSession(token, environment)
      inFlightRef.current[environment] = pending

      void pending
        .then((session) => {
          if (isStale()) return
          if (session.environment !== environment) {
            // 요청한 환경과 다른 세션은 캐시하지 않는다. 이 세션으로 터미널을 열면
            // 사용자가 보고 있는 환경과 다른 곳에 명령이 나간다.
            throw new Error(
              `요청한 환경(${environment})과 다른 세션(${session.environment})이 반환됐습니다`,
            )
          }
          cacheRef.current[environment] = session
          setStates((current) => ({ ...current, [environment]: { status: 'ready', session } }))
        })
        .catch((error: unknown) => {
          if (isStale()) return
          const message = error instanceof Error ? error.message : '터미널 세션 생성에 실패했습니다'
          setStates((current) => ({ ...current, [environment]: { status: 'error', message } }))
        })
        .finally(() => {
          if (isStale()) return
          delete inFlightRef.current[environment]
        })
    },
    [token],
  )

  const retry = useCallback(
    (environment: EnvironmentId) => {
      if (inFlightRef.current[environment]) return
      delete cacheRef.current[environment]
      setStates((current) => ({ ...current, [environment]: IDLE }))
      ensure(environment)
    },
    [ensure],
  )

  const closeAll = useCallback(async () => {
    const activeToken = tokenRef.current
    const sessions = Object.values(cacheRef.current).filter(
      (session): session is SessionResponse => Boolean(session),
    )

    reset()

    if (!activeToken || sessions.length === 0) return
    await Promise.allSettled(
      sessions.map((session) => deleteTerminalSession(activeToken, session.id)),
    )
  }, [reset])

  const stateOf = useCallback(
    (environment: EnvironmentId | null): EnvironmentSessionState =>
      environment ? states[environment] ?? IDLE : IDLE,
    [states],
  )

  const sessionOf = useCallback(
    (environment: EnvironmentId | null): SessionResponse | null => {
      const state = stateOf(environment)
      return state.status === 'ready' ? state.session : null
    },
    [stateOf],
  )

  return { sessionOf, stateOf, ensure, retry, closeAll }
}
