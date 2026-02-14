import React, { useEffect, useRef } from 'react'
import { Terminal as XTerm } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'
import './Terminal.css'

const Terminal: React.FC = () => {
  const terminalRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<XTerm | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const currentLineRef = useRef<string>('')

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
    fitAddon.fit()

    // 환영 메시지 출력
    terminal.writeln('Welcome to K8s Survival Camp Terminal! 🚀')
    terminal.writeln('Connected to namespace: user-demo')
    terminal.writeln('Type kubectl commands to interact with your cluster.')
    terminal.writeln('')
    terminal.write('$ ')

    // 사용자 입력 처리
    terminal.onData((data) => {
      const code = data.charCodeAt(0)

      // Enter 키 (13)
      if (code === 13) {
        terminal.write('\r\n')
        const command = currentLineRef.current.trim()

        if (command) {
          // 명령어 실행 (현재는 로컬에서 시뮬레이션)
          handleCommand(terminal, command)
        }

        currentLineRef.current = ''
        terminal.write('$ ')
      }
      // Backspace 키 (127)
      else if (code === 127) {
        if (currentLineRef.current.length > 0) {
          currentLineRef.current = currentLineRef.current.slice(0, -1)
          terminal.write('\b \b')
        }
      }
      // 일반 문자
      else {
        currentLineRef.current += data
        terminal.write(data)
      }
    })

    // 창 크기 변경 시 터미널 크기 조절
    const handleResize = () => {
      fitAddon.fit()
    }
    window.addEventListener('resize', handleResize)

    // refs 저장
    xtermRef.current = terminal
    fitAddonRef.current = fitAddon

    // 정리 함수
    return () => {
      window.removeEventListener('resize', handleResize)
      terminal.dispose()
    }
  }, [])

  // 명령어 처리 함수 (시뮬레이션)
  const handleCommand = (terminal: XTerm, command: string) => {
    // kubectl 명령어인지 확인
    if (!command.startsWith('kubectl')) {
      terminal.writeln('\x1b[31mError: Only kubectl commands are allowed\x1b[0m')
      return
    }

    // 간단한 시뮬레이션 응답
    if (command.includes('get pods')) {
      terminal.writeln('NAME                     READY   STATUS    RESTARTS   AGE')
      terminal.writeln('web-app-7d8f9c5b6-x4k2m  1/1     Running   0          5m')
      terminal.writeln('backend-6b9d8f7c5-p9n3l  1/1     Running   0          5m')
    } else if (command.includes('get services')) {
      terminal.writeln('NAME          TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE')
      terminal.writeln('web-service   ClusterIP   10.96.0.1       <none>        80/TCP     5m')
    } else if (command.includes('help')) {
      terminal.writeln('Available commands:')
      terminal.writeln('  kubectl get pods       - List all pods')
      terminal.writeln('  kubectl get services   - List all services')
      terminal.writeln('  kubectl describe pod   - Describe a pod')
      terminal.writeln('  kubectl logs           - View pod logs')
    } else {
      terminal.writeln(`Executing: ${command}`)
      terminal.writeln('\x1b[33m(Backend connection not implemented yet)\x1b[0m')
    }
  }

  return (
    <div className="terminal-container">
      <div className="terminal-wrapper" ref={terminalRef}></div>
    </div>
  )
}

export default Terminal
