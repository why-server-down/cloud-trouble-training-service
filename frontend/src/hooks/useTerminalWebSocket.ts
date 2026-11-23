import { useCallback, useEffect, useRef, useState } from 'react'
import { Terminal } from 'xterm'
import { AUTH_EXPIRED_EVENT } from '../services/api'
import { EnvironmentId } from '../types/training'
import { getTerminalPrompt } from '../utils/terminal'

interface WebSocketMessage {
  type: 'output' | 'error' | 'confirm'
  data?: string
  message?: string
  command?: string
}

interface UseTerminalWebSocketProps {
  /** 프롬프트에 쓰이고, 바뀌면 기존 연결을 닫고 다시 연결한다. */
  environment: EnvironmentId
  sessionId: string
  token: string
  terminal: Terminal | null
  namespace?: string
  onConfirmRequired?: (command: string) => void
  onCommandComplete?: () => void
}

export type TerminalConnectionStatus = 'connecting' | 'connected' | 'disconnected'

const MAX_RECONNECT_ATTEMPTS = 3
const RECONNECT_DELAY_MS = 2000

// 서버가 의도적으로 닫는 close code. 재연결 대상이 아니다.
// 4000 다른 탭이 세션 인수 · 4003 소유자 불일치 · 4004 세션 없음 · 4010 환경 불가
const NO_RETRY_CLOSE_CODES = new Set([4000, 4003, 4004, 4010])

const closeCodeMessage = (code: number): string => {
  if (code === 4000) return '다른 탭에서 터미널에 연결되어 이 연결이 종료되었습니다. 이 탭을 새로고침하면 다시 연결됩니다.'
  if (code === 4010) return '이 환경의 터미널을 사용할 수 없습니다.'
  return '터미널 세션을 찾을 수 없습니다. 세션을 다시 열어 주세요.'
}

const getDefaultWsBaseUrl = () => `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`

const normalizeWsBaseUrl = (configuredUrl?: string) => {
  if (!configuredUrl) return getDefaultWsBaseUrl()

  try {
    const url = new URL(configuredUrl)
    const isSameBrowserHost = url.hostname === window.location.hostname
    const isDockerServiceName = url.hostname === 'backend'

    if (isDockerServiceName || (isSameBrowserHost && url.port === '8000')) {
      return getDefaultWsBaseUrl()
    }
  } catch {
    return configuredUrl
  }

  return configuredUrl.replace(/\/$/, '')
}

export const useTerminalWebSocket = ({ environment, sessionId, token, terminal, namespace, onConfirmRequired, onCommandComplete }: UseTerminalWebSocketProps) => {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const initialMessageReceivedRef = useRef(false)
  const confirmHandlerRef = useRef(onConfirmRequired)
  const completeHandlerRef = useRef(onCommandComplete)
  const [connectionStatus, setConnectionStatus] = useState<TerminalConnectionStatus>('disconnected')
  const [error, setError] = useState<string | null>(null)
  const [reconnectKey, setReconnectKey] = useState(0)
  const wsBaseUrl = normalizeWsBaseUrl(import.meta.env.VITE_WS_BASE_URL)

  useEffect(() => {
    confirmHandlerRef.current = onConfirmRequired
    completeHandlerRef.current = onCommandComplete
  }, [onConfirmRequired, onCommandComplete])

  const getPrompt = useCallback(
    () => getTerminalPrompt(environment, namespace),
    [environment, namespace],
  )

  /**
   * 환경이나 세션이 바뀌면 재연결 상태를 새로 시작한다.
   *
   * 아래 연결 effect 안에서 초기화하면 안 된다 — 그 effect 는 reconnectKey 로도
   * 다시 도는데, 그때마다 카운터가 0 이 되면 3회 상한이 사라져 무한 재연결이 된다.
   */
  useEffect(() => {
    reconnectAttemptsRef.current = 0
    initialMessageReceivedRef.current = false
  }, [environment, sessionId])

  useEffect(() => {
    if (!sessionId || !token || !terminal) return

    setConnectionStatus('connecting')
    const ws = new WebSocket(`${wsBaseUrl}/ws/terminal/${sessionId}?token=${token}`)
    let intentionallyClosed = false

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0
      setConnectionStatus('connected')
      setError(null)
    }

    ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data)
        if (message.type === 'output') {
          // 출력이 없는 성공 명령(예: truncate)도 서버는 data:'' 로 보낸다.
          // data 가 falsy 라고 건너뛰면 완료 콜백이 안 불려 터미널이 멈춘다.
          if (message.data) {
            terminal.write(message.data)
          }
          if (message.data && message.data.includes('Connected to namespace:')) {
            if (!initialMessageReceivedRef.current) {
              initialMessageReceivedRef.current = true
              terminal.write(getPrompt())
            }
          } else {
            terminal.write(`\r\n${getPrompt()}`)
          }
          completeHandlerRef.current?.()
        }
        if (message.type === 'error' && message.message) {
          terminal.write(`\r\n\x1b[31mError: ${message.message}\x1b[0m\r\n${getPrompt()}`)
          completeHandlerRef.current?.()
        }
        if (message.type === 'confirm' && message.command) confirmHandlerRef.current?.(message.command)
      } catch (parseError) {
        console.error('WebSocket 메시지 파싱 실패:', parseError)
      }
    }

    ws.onerror = () => setError('터미널 연결 중 오류가 발생했습니다.')
    ws.onclose = (event) => {
      setConnectionStatus('disconnected')
      if (intentionallyClosed) return
      // 명령 실행 중 예기치 않게 끊겨도 실행 상태를 풀어 큐가 멈추지 않게 한다.
      completeHandlerRef.current?.()
      if (event.code === 4001) {
        setError('인증이 만료되었습니다. 다시 로그인해 주세요.')
        window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
        return
      }
      // 서버가 의도적으로 닫은 코드는 재연결하지 않는다. 특히 4000(다른 탭이 세션을
      // 가져감)에 재연결하면 두 탭이 서로를 끝없이 끊는 핑퐁이 된다.
      if (NO_RETRY_CLOSE_CODES.has(event.code)) {
        setError(closeCodeMessage(event.code))
        return
      }
      if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttemptsRef.current += 1
        setError(`터미널 연결이 끊겼습니다. 재연결 중입니다. (${reconnectAttemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})`)
        reconnectTimerRef.current = window.setTimeout(() => {
          initialMessageReceivedRef.current = false
          setReconnectKey((current) => current + 1)
        }, RECONNECT_DELAY_MS)
        return
      }
      setError('터미널 재연결에 실패했습니다. 페이지를 새로고침해 주세요.')
    }

    wsRef.current = ws
    return () => {
      intentionallyClosed = true
      if (reconnectTimerRef.current !== null) window.clearTimeout(reconnectTimerRef.current)
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close()
    }
  }, [environment, getPrompt, reconnectKey, sessionId, terminal, token, wsBaseUrl])

  const sendCommand = useCallback((command: string, confirmed: boolean = false) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError('터미널이 연결되지 않았습니다.')
      return false
    }
    wsRef.current.send(JSON.stringify({ type: 'command', command, ...(confirmed && { confirmed: true }) }))
    return true
  }, [])

  return { isConnected: connectionStatus === 'connected', connectionStatus, error, sendCommand }
}
