import { useEffect, useRef, useState } from 'react'
import { Terminal } from 'xterm'

interface WebSocketMessage {
  type: 'output' | 'error' | 'confirm'
  data?: string
  message?: string
  command?: string
  exit_code?: number
  execution_time?: number
}

interface UseTerminalWebSocketProps {
  sessionId: string
  token: string
  terminal: Terminal | null
  namespace?: string
  onConfirmRequired?: (command: string) => void
}

export const useTerminalWebSocket = ({
  sessionId,
  token,
  terminal,
  namespace,
  onConfirmRequired,
}: UseTerminalWebSocketProps) => {
  const wsRef = useRef<WebSocket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const initialMessageReceivedRef = useRef(false)

  // WebSocket Base URL - 환경변수에서 가져오기
  const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'
  
  // 프롬프트 생성
  const getPrompt = () => {
    if (namespace) {
      const shortNs = namespace.startsWith('user-') 
        ? namespace.slice(0, 15) + '...' 
        : namespace
      return `[${shortNs}]$ `
    }
    return '$ '
  }

  useEffect(() => {
    if (!sessionId || !token || !terminal) {
      console.log('⏸️ WebSocket 연결 대기 중 - sessionId:', !!sessionId, 'token:', !!token, 'terminal:', !!terminal)
      return
    }

    console.log('🔌 WebSocket 연결 시작...')

    // WebSocket 연결
    const wsUrl = `${WS_BASE_URL}/ws/terminal/${sessionId}?token=${token}`
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('✅ WebSocket 연결 성공')
      setIsConnected(true)
      setError(null)
    }

    ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data)
        console.log('📥 Received WebSocket message:', message)

        switch (message.type) {
          case 'output':
            // 서버에서 받은 출력을 터미널에 표시
            if (message.data && terminal) {
              console.log('📝 Writing to terminal:', message.data.substring(0, 100))
              console.log('📝 Full data length:', message.data.length)
              console.log('📝 Full data:', message.data)
              console.log('📝 Terminal ready:', !!terminal)
              terminal.write(message.data)
              
              // 초기 연결 메시지면 프롬프트 추가
              if (message.data.includes('Connected to namespace:') && !initialMessageReceivedRef.current) {
                initialMessageReceivedRef.current = true
                terminal.write(getPrompt())
              } else if (!message.data.includes('Connected to namespace:')) {
                // 일반 명령어 응답이면 프롬프트 추가
                terminal.write(`\r\n${getPrompt()}`)
              }
            } else {
              console.warn('⚠️ Terminal not ready or no data')
            }
            break

          case 'error':
            // 에러 메시지를 빨간색으로 표시
            if (message.message) {
              terminal.write(`\r\n\x1b[31mError: ${message.message}\x1b[0m\r\n`)
            }
            break

          case 'confirm':
            // 삭제 확인 요청
            if (message.command && onConfirmRequired) {
              onConfirmRequired(message.command)
            }
            break

          default:
            console.warn('알 수 없는 메시지 타입:', message)
        }
      } catch (err) {
        console.error('메시지 파싱 에러:', err)
      }
    }

    ws.onerror = (event) => {
      console.error('❌ WebSocket 에러:', event)
      setError('WebSocket 연결 에러가 발생했습니다')
    }

    ws.onclose = (event) => {
      console.log('🔌 WebSocket 연결 종료:', event.code, event.reason)
      setIsConnected(false)

      if (event.code === 4001) {
        setError('인증 실패: 토큰이 유효하지 않습니다')
      }
    }

    wsRef.current = ws

    // 정리 함수
    return () => {
      console.log('🧹 WebSocket 정리 중...')
      initialMessageReceivedRef.current = false
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
    }
  }, [sessionId, token, terminal]) // terminal이 변경될 때만 재연결

  // 명령어 전송 함수
  const sendCommand = (command: string, confirmed: boolean = false) => {
    console.log('📤 Sending command:', command, 'confirmed:', confirmed)
    
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.error('❌ WebSocket이 연결되지 않았습니다. readyState:', wsRef.current?.readyState)
      return
    }

    const message = {
      type: 'command',
      command,
      ...(confirmed && { confirmed: true }),
    }

    console.log('📤 Sending message:', JSON.stringify(message))
    wsRef.current.send(JSON.stringify(message))
  }

  return {
    isConnected,
    error,
    sendCommand,
  }
}
