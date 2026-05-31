import { useCallback, useEffect, useRef, useState } from 'react'
import { Terminal } from 'xterm'
import { AUTH_EXPIRED_EVENT } from '../services/api'

interface WebSocketMessage {
  type: 'output' | 'error' | 'confirm'
  data?: string
  message?: string
  command?: string
}

interface UseTerminalWebSocketProps {
  sessionId: string
  token: string
  terminal: Terminal | null
  namespace?: string
  onConfirmRequired?: (command: string) => void
}

export type TerminalConnectionStatus = 'connecting' | 'connected' | 'disconnected'

const MAX_RECONNECT_ATTEMPTS = 3
const RECONNECT_DELAY_MS = 2000

export const useTerminalWebSocket = ({ sessionId, token, terminal, namespace, onConfirmRequired }: UseTerminalWebSocketProps) => {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const initialMessageReceivedRef = useRef(false)
  const confirmHandlerRef = useRef(onConfirmRequired)
  const [connectionStatus, setConnectionStatus] = useState<TerminalConnectionStatus>('disconnected')
  const [error, setError] = useState<string | null>(null)
  const [reconnectKey, setReconnectKey] = useState(0)
  const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'

  useEffect(() => {
    confirmHandlerRef.current = onConfirmRequired
  }, [onConfirmRequired])

  const getPrompt = useCallback(() => {
    if (!namespace) return '$ '
    return `[${namespace.startsWith('user-') ? namespace.slice(0, 15) + '...' : namespace}]$ `
  }, [namespace])

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
        if (message.type === 'output' && message.data) {
          terminal.write(message.data)
          if (message.data.includes('Connected to namespace:')) {
            if (!initialMessageReceivedRef.current) {
              initialMessageReceivedRef.current = true
              terminal.write(getPrompt())
            }
          } else {
            terminal.write(`\r\n${getPrompt()}`)
          }
        }
        if (message.type === 'error' && message.message) terminal.write(`\r\n\x1b[31mError: ${message.message}\x1b[0m\r\n${getPrompt()}`)
        if (message.type === 'confirm' && message.command) confirmHandlerRef.current?.(message.command)
      } catch (parseError) {
        console.error('WebSocket 메시지 파싱 실패:', parseError)
      }
    }

    ws.onerror = () => setError('터미널 연결 중 오류가 발생했습니다.')
    ws.onclose = (event) => {
      setConnectionStatus('disconnected')
      if (intentionallyClosed) return
      if (event.code === 4001) {
        setError('인증이 만료되었습니다. 다시 로그인해 주세요.')
        window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
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
  }, [getPrompt, reconnectKey, sessionId, terminal, token, wsBaseUrl])

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
