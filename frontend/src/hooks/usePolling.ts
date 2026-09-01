import { useEffect, useRef } from 'react'

/**
 * 폴링 결과 (FE-16).
 * - `continue` : 다음 주기에 다시 호출한다.
 * - `stop`     : 더 이상 호출하지 않는다 (완료·실패·포기·404).
 */
export type PollResult = 'continue' | 'stop'

export interface PollingOptions {
  /** 탭이 보이는 동안의 간격(ms). */
  intervalMs: number
  /**
   * 탭이 백그라운드일 때의 간격(ms).
   * 보이지 않는 화면을 같은 빈도로 갱신할 이유가 없다.
   */
  hiddenIntervalMs: number
  /** 연속 실패 시 backoff 상한(ms). */
  maxBackoffMs?: number
  /** false 면 폴링을 시작하지 않는다. */
  enabled?: boolean
  /**
   * 이 값이 바뀌면 폴링을 처음부터 다시 시작한다 (즉시 1회 조회 + backoff 초기화).
   * 서버 값이 방금 바뀐 시점(힌트 사용 직후 등)에 다음 주기를 기다리지 않기 위한 것이다.
   */
  restartKey?: number | string
}

const DEFAULT_MAX_BACKOFF_MS = 30000

/**
 * 지수 backoff 와 탭 가시성을 반영하는 폴링 (FE-16).
 *
 * `setInterval` 을 쓰지 않는다. setInterval 은 응답이 간격보다 오래 걸릴 때
 * 요청을 겹쳐 쌓고, 간격을 도중에 바꿀 수도 없다. 매번 다음 실행을 직접
 * 예약하는 방식이라 호출이 겹치지 않고 간격을 상황에 맞게 바꿀 수 있다.
 *
 * StrictMode 는 effect 를 두 번 실행한다. 각 실행이 자기 타이머와 취소 플래그를
 * 갖고 cleanup 에서 정리하므로 타이머가 중복으로 남지 않는다.
 */
export const usePolling = (
  task: () => Promise<PollResult>,
  options: PollingOptions,
) => {
  const {
    intervalMs,
    hiddenIntervalMs,
    maxBackoffMs = DEFAULT_MAX_BACKOFF_MS,
    enabled = true,
    restartKey = 0,
  } = options

  /*
   * task 는 매 렌더마다 새로 만들어지는 것이 보통이다. effect 의 의존성으로 두면
   * 렌더마다 폴링이 재시작되므로 ref 로 최신 것만 들고 있는다.
   */
  const taskRef = useRef(task)
  taskRef.current = task

  /**
   * 진행 중인 task 의 프라미스. 없으면 null.
   *
   * 한 effect 안에서는 다음 실행을 직접 예약하므로 겹칠 수 없다. 그런데
   * StrictMode 는 마운트 시 effect 를 두 번 실행하고 **두 실행이 각각 즉시 1회
   * task 를 호출한다.** 그래서 마운트마다 요청이 두 번 나갔다(라이브 확인).
   *
   * 건너뛰기(early return)로 막으면 안 된다 — 취소된 첫 인스턴스가 실행을 잡고
   * 살아남은 인스턴스가 건너뛰면 아무도 다음 주기를 예약하지 않아 폴링이 멈춘다.
   * 그래서 **진행 중 프라미스를 공유**한다: 요청은 한 번만 나가고, 살아남은
   * 인스턴스는 그 결과를 받아 정상적으로 다음 주기를 잡는다.
   */
  const runningRef = useRef<Promise<PollResult> | null>(null)

  useEffect(() => {
    if (!enabled) return undefined

    let cancelled = false
    let timerId: number | undefined
    let failures = 0

    const isHidden = () => typeof document !== 'undefined' && document.visibilityState === 'hidden'

    const nextDelay = () => {
      if (failures === 0) return isHidden() ? hiddenIntervalMs : intervalMs
      // 연속 실패는 간격을 두 배씩 늘린다. 죽은 서버를 같은 빈도로 두드리지 않는다.
      const base = isHidden() ? hiddenIntervalMs : intervalMs
      return Math.min(base * 2 ** failures, maxBackoffMs)
    }

    const schedule = (delay: number) => {
      if (cancelled) return
      timerId = window.setTimeout(run, delay)
    }

    /** 진행 중이면 그 프라미스를 그대로 돌려준다. 요청은 한 번만 나간다. */
    const invoke = (): Promise<PollResult> => {
      if (runningRef.current) return runningRef.current

      const pending = taskRef.current()
      runningRef.current = pending

      const release = () => {
        if (runningRef.current === pending) runningRef.current = null
      }
      // 거부도 여기서 받아 둔다. 안 받으면 unhandled rejection 으로 새어 나간다.
      void pending.then(release, release)

      return pending
    }

    const run = async () => {
      if (cancelled) return

      let result: PollResult = 'continue'
      try {
        result = await invoke()
        failures = 0
      } catch {
        // task 가 스스로 처리하지 못한 예외는 실패로 센다.
        failures += 1
      }

      if (cancelled || result === 'stop') return
      schedule(nextDelay())
    }

    const handleVisibilityChange = () => {
      if (cancelled) return
      if (timerId) window.clearTimeout(timerId)

      if (isHidden()) {
        /*
         * 이미 예약돼 있던 타이머를 그대로 두면 "완화"가 한 주기 늦게 적용된다.
         * 숨는 즉시 다음 주기를 hidden 간격으로 다시 잡는다.
         */
        schedule(nextDelay())
        return
      }

      /*
       * 탭으로 돌아오면 다음 주기를 기다리지 않고 즉시 한 번 갱신한다.
       * 기다리게 하면 사용자는 낡은 숫자를 보면서 화면이 멈춘 줄 안다.
       */
      void run()
    }

    void run()
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      cancelled = true
      if (timerId) window.clearTimeout(timerId)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [enabled, hiddenIntervalMs, intervalMs, maxBackoffMs, restartKey])
}
