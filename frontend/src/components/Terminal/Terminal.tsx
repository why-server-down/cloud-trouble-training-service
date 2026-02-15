import React, { useEffect, useRef, useState } from 'react'
import { Terminal as XTerm } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import { useTerminalWebSocket } from '../../hooks/useTerminalWebSocket'
import 'xterm/css/xterm.css'
import './Terminal.css'

interface TerminalProps {
  sessionId?: string
  token?: string
  namespace?: string
}

const Terminal: React.FC<TerminalProps> = ({ sessionId, token, namespace }) => {
  const terminalRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<XTerm | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const currentLineRef = useRef<string>('')
  const [confirmCommand, setConfirmCommand] = useState<string | null>(null)
  const [terminalReady, setTerminalReady] = useState(false)
  
  // 명령어 히스토리
  const commandHistoryRef = useRef<string[]>([])
  const historyIndexRef = useRef<number>(-1)
  
  // 자동완성 관련
  const kubectlCommands = [
    'kubectl get pods',
    'kubectl get services',
    'kubectl get deployments',
    'kubectl get nodes',
    'kubectl describe pod ',
    'kubectl describe service ',
    'kubectl logs ',
    'kubectl delete pod ',
    'kubectl apply -f ',
    'kubectl version',
    'kubectl help',
    'kubectl get namespaces',
    'kubectl get all',
  ]
  
  // isConnected를 ref로도 관리
  const isConnectedRef = useRef<boolean>(false)

  // WebSocket 연결 - 터미널이 준비된 후에만 연결
  const { isConnected, error, sendCommand } = useTerminalWebSocket({
    sessionId: sessionId || '',
    token: token || '',
    terminal: terminalReady ? xtermRef.current : null,
    namespace: namespace,
    onConfirmRequired: (command) => {
      setConfirmCommand(command)
    },
  })
  
  // isConnected가 변경될 때 ref 업데이트
  useEffect(() => {
    isConnectedRef.current = isConnected
    console.log('🔄 isConnected 업데이트:', isConnected)
  }, [isConnected])
  
  // 프롬프트 생성 함수
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
    if (!terminalRef.current) return

    // xterm.js 터미널 인스턴스 생성
    const terminal = new XTerm({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      theme: {
        background: '#1e1e1e',
        foreground: '#ffffff',
        cursor: '#61dafb',
        selectionBackground: '#3e3e3e',
      },
      rows: 30,
      cols: 100,
    })

    // FitAddon: 터미널 크기를 자동으로 조절
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)

    // 터미널을 DOM에 연결
    terminal.open(terminalRef.current)
    
    // fit()은 DOM이 완전히 렌더링된 후 실행
    const fitTimer = setTimeout(() => {
      try {
        fitAddon.fit()
      } catch (error) {
        console.warn('FitAddon fit() failed:', error)
      }
    }, 100)

    // WebSocket 연결 전 안내 메시지
    if (!sessionId || !token) {
      terminal.writeln('⚠️  로그인이 필요합니다')
      terminal.writeln('먼저 로그인을 해주세요.')
    }

    // 사용자 입력 처리
    terminal.onData((data) => {
      const code = data.charCodeAt(0)

      // Enter 키 (13)
      if (code === 13) {
        terminal.write('\r\n')
        const command = currentLineRef.current.trim()

        if (command) {
          // 명령어 히스토리에 추가
          commandHistoryRef.current.push(command)
          historyIndexRef.current = commandHistoryRef.current.length
          
          // 디버깅: 연결 상태 확인 (ref 사용)
          console.log('🔍 Debug - isConnected:', isConnectedRef.current, 'sessionId:', sessionId, 'token:', token ? 'exists' : 'missing')
          
          // WebSocket이 연결되어 있으면 서버로 전송
          if (isConnectedRef.current && sessionId && token) {
            sendCommand(command)
            // 서버 응답을 기다리므로 여기서 프롬프트 출력 안 함
          } else {
            // 연결 안 되어 있으면 로컬 시뮬레이션
            handleCommandLocal(terminal, command)
            terminal.write(getPrompt())
          }
        } else {
          // 빈 명령어면 프롬프트만 출력
          terminal.write(getPrompt())
        }

        currentLineRef.current = ''
      }
      // Backspace 키 (127)
      else if (code === 127) {
        if (currentLineRef.current.length > 0) {
          currentLineRef.current = currentLineRef.current.slice(0, -1)
          terminal.write('\b \b')
        }
      }
      // 화살표 위 (27, 91, 65) - 이전 명령어
      else if (data === '\x1b[A') {
        if (historyIndexRef.current > 0) {
          // 현재 입력 지우기
          for (let i = 0; i < currentLineRef.current.length; i++) {
            terminal.write('\b \b')
          }
          
          // 이전 명령어 가져오기
          historyIndexRef.current--
          const prevCommand = commandHistoryRef.current[historyIndexRef.current]
          currentLineRef.current = prevCommand
          terminal.write(prevCommand)
        }
      }
      // 화살표 아래 (27, 91, 66) - 다음 명령어
      else if (data === '\x1b[B') {
        if (historyIndexRef.current < commandHistoryRef.current.length - 1) {
          // 현재 입력 지우기
          for (let i = 0; i < currentLineRef.current.length; i++) {
            terminal.write('\b \b')
          }
          
          // 다음 명령어 가져오기
          historyIndexRef.current++
          const nextCommand = commandHistoryRef.current[historyIndexRef.current]
          currentLineRef.current = nextCommand
          terminal.write(nextCommand)
        } else if (historyIndexRef.current === commandHistoryRef.current.length - 1) {
          // 마지막 명령어에서 아래 누르면 빈 줄
          for (let i = 0; i < currentLineRef.current.length; i++) {
            terminal.write('\b \b')
          }
          historyIndexRef.current = commandHistoryRef.current.length
          currentLineRef.current = ''
        }
      }
      // Ctrl+C (3) - 현재 입력 취소
      else if (code === 3) {
        terminal.write(`^C\r\n${getPrompt()}`)
        currentLineRef.current = ''
      }
      // Ctrl+L (12) - 화면 지우기
      else if (code === 12) {
        terminal.clear()
        terminal.write(getPrompt())
        currentLineRef.current = ''
      }
      // Tab (9) - 자동완성
      else if (code === 9) {
        const currentInput = currentLineRef.current
        
        // kubectl로 시작하는 명령어만 자동완성
        if (currentInput.startsWith('kubectl') || currentInput === 'k') {
          const matches = kubectlCommands.filter(cmd => 
            cmd.startsWith(currentInput)
          )
          
          if (matches.length === 1) {
            // 정확히 하나 매칭되면 자동완성
            const completion = matches[0]
            const toAdd = completion.slice(currentInput.length)
            
            currentLineRef.current = completion
            terminal.write(toAdd)
          } else if (matches.length > 1) {
            // 여러 개 매칭되면 목록 표시
            terminal.write('\r\n')
            matches.forEach(match => {
              terminal.write(`  ${match}\r\n`)
            })
            terminal.write(getPrompt() + currentInput)
          }
        }
      }
      // 일반 문자
      else if (code >= 32) {
        currentLineRef.current += data
        terminal.write(data)
      }
    })

    // 창 크기 변경 시 터미널 크기 조절
    const handleResize = () => {
      if (fitAddonRef.current && xtermRef.current) {
        setTimeout(() => {
          try {
            fitAddonRef.current?.fit()
          } catch (error) {
            console.warn('FitAddon resize failed:', error)
          }
        }, 100)
      }
    }
    window.addEventListener('resize', handleResize)

    // refs 저장
    xtermRef.current = terminal
    fitAddonRef.current = fitAddon

    // 터미널 준비 완료 표시
    setTerminalReady(true)

    // 정리 함수
    return () => {
      clearTimeout(fitTimer)
      window.removeEventListener('resize', handleResize)
      terminal.dispose()
      setTerminalReady(false)
    }
  }, []) // 의존성 배열 비우기 - 한 번만 실행

  // WebSocket 연결 상태 표시
  useEffect(() => {
    if (!xtermRef.current) return

    // 에러만 표시 (연결 성공 메시지는 백엔드에서 전송)
    if (error) {
      xtermRef.current.write(`\r\n❌ ${error}\r\n`)
    }
  }, [isConnected, error])

  // 삭제 확인 다이얼로그
  useEffect(() => {
    if (confirmCommand && xtermRef.current) {
      const confirmed = window.confirm(
        `정말로 이 명령어를 실행하시겠습니까?\n\n${confirmCommand}`
      )

      if (confirmed) {
        sendCommand(confirmCommand, true)
      } else {
        xtermRef.current.write(`\r\n취소되었습니다.\r\n${getPrompt()}`)
      }

      setConfirmCommand(null)
    }
  }, [confirmCommand, sendCommand, namespace])

  // 로컬 시뮬레이션 (WebSocket 연결 전)
  const handleCommandLocal = (terminal: XTerm, command: string) => {
    if (!command.startsWith('kubectl')) {
      terminal.writeln('\x1b[31mError: Only kubectl commands are allowed\x1b[0m')
      return
    }

    terminal.writeln('\x1b[33m⚠️  로컬 시뮬레이션 모드\x1b[0m')
    terminal.writeln('\x1b[33m로그인하면 실제 클러스터에 연결됩니다.\x1b[0m')

    if (command.includes('get pods')) {
      terminal.writeln('NAME                     READY   STATUS    RESTARTS   AGE')
      terminal.writeln('web-app-7d8f9c5b6-x4k2m  1/1     Running   0          5m')
      terminal.writeln('backend-6b9d8f7c5-p9n3l  1/1     Running   0          5m')
    } else if (command.includes('get services')) {
      terminal.writeln('NAME          TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE')
      terminal.writeln('web-service   ClusterIP   10.96.0.1       <none>        80/TCP     5m')
    } else {
      terminal.writeln(`Executing: ${command}`)
    }
  }

  return (
    <div className="terminal-container">
      {/* 연결 상태 표시 */}
      <div className="terminal-status">
        {isConnected ? (
          <span className="status-connected">🟢 연결됨</span>
        ) : (
          <span className="status-disconnected">🔴 연결 안 됨</span>
        )}
      </div>
      <div className="terminal-wrapper" ref={terminalRef}></div>
    </div>
  )
}

export default Terminal
