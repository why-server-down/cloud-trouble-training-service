import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Terminal as XTerm } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import ConfirmModal from '../Feedback/ConfirmModal'
import { useTerminalWebSocket } from '../../hooks/useTerminalWebSocket'
import 'xterm/css/xterm.css'
import './Terminal.css'

interface TerminalProps {
  sessionId?: string
  token?: string
  namespace?: string
}

const kubectlCommands = [
  'kubectl get pods',
  'kubectl get services',
  'kubectl get deployments',
  'kubectl describe pod ',
  'kubectl describe service ',
  'kubectl logs ',
  'kubectl delete pod ',
  'kubectl apply -f ',
  'kubectl version',
  'kubectl help',
  'kubectl get all',
]

const Terminal: React.FC<TerminalProps> = ({ sessionId, token, namespace }) => {
  const terminalElementRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<XTerm | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const currentLineRef = useRef('')
  const commandHistoryRef = useRef<string[]>([])
  const historyIndexRef = useRef(-1)
  const isConnectedRef = useRef(false)
  const [confirmCommand, setConfirmCommand] = useState<string | null>(null)
  const [terminalReady, setTerminalReady] = useState(false)

  const getPrompt = useCallback(() => {
    if (!namespace) return '$ '
    return `[${namespace.startsWith('user-') ? namespace.slice(0, 15) + '...' : namespace}]$ `
  }, [namespace])

  const { isConnected, connectionStatus, error, sendCommand } = useTerminalWebSocket({
    sessionId: sessionId || '',
    token: token || '',
    terminal: terminalReady ? xtermRef.current : null,
    namespace,
    onConfirmRequired: setConfirmCommand,
  })

  useEffect(() => {
    isConnectedRef.current = isConnected
  }, [isConnected])

  useEffect(() => {
    if (!terminalElementRef.current) return

    const terminal = new XTerm({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      theme: { background: '#1e1e1e', foreground: '#ffffff', cursor: '#61dafb', selectionBackground: '#3e3e3e' },
      rows: 30,
      cols: 100,
    })
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.open(terminalElementRef.current)
    xtermRef.current = terminal
    fitAddonRef.current = fitAddon
    setTerminalReady(true)

    const fitTimer = window.setTimeout(() => fitAddon.fit(), 100)
    const handleResize = () => window.setTimeout(() => fitAddonRef.current?.fit(), 100)
    window.addEventListener('resize', handleResize)

    if (!sessionId || !token) {
      terminal.writeln('로그인이 필요합니다.')
      terminal.writeln('먼저 로그인해 주세요.')
    }

    const clearCurrentLine = () => {
      for (let index = 0; index < currentLineRef.current.length; index += 1) terminal.write('\b \b')
    }

    terminal.onData((data) => {
      const code = data.charCodeAt(0)

      if (code === 13) {
        terminal.write('\r\n')
        const command = currentLineRef.current.trim()
        if (command) {
          commandHistoryRef.current.push(command)
          historyIndexRef.current = commandHistoryRef.current.length
          if (isConnectedRef.current && sessionId && token) sendCommand(command)
          else terminal.writeln(command.startsWith('kubectl') ? '터미널 연결을 기다리는 중입니다.' : 'Error: Only kubectl commands are allowed')
        }
        if (!command || !isConnectedRef.current) terminal.write(getPrompt())
        currentLineRef.current = ''
      } else if (code === 127 && currentLineRef.current.length > 0) {
        currentLineRef.current = currentLineRef.current.slice(0, -1)
        terminal.write('\b \b')
      } else if (data === '\x1b[A' && historyIndexRef.current > 0) {
        clearCurrentLine()
        historyIndexRef.current -= 1
        currentLineRef.current = commandHistoryRef.current[historyIndexRef.current]
        terminal.write(currentLineRef.current)
      } else if (data === '\x1b[B') {
        clearCurrentLine()
        if (historyIndexRef.current < commandHistoryRef.current.length - 1) {
          historyIndexRef.current += 1
          currentLineRef.current = commandHistoryRef.current[historyIndexRef.current]
          terminal.write(currentLineRef.current)
        } else {
          historyIndexRef.current = commandHistoryRef.current.length
          currentLineRef.current = ''
        }
      } else if (code === 3) {
        terminal.write(`^C\r\n${getPrompt()}`)
        currentLineRef.current = ''
      } else if (code === 12) {
        terminal.clear()
        terminal.write(getPrompt())
        currentLineRef.current = ''
      } else if (code === 9) {
        const matches = kubectlCommands.filter((command) => command.startsWith(currentLineRef.current))
        if (matches.length === 1) {
          terminal.write(matches[0].slice(currentLineRef.current.length))
          currentLineRef.current = matches[0]
        } else if (matches.length > 1) {
          terminal.write(`\r\n  ${matches.join('\r\n  ')}\r\n${getPrompt()}${currentLineRef.current}`)
        }
      } else if (code >= 32) {
        currentLineRef.current += data
        terminal.write(data)
      }
    })

    return () => {
      window.clearTimeout(fitTimer)
      window.removeEventListener('resize', handleResize)
      terminal.dispose()
      setTerminalReady(false)
    }
  }, [getPrompt, sendCommand, sessionId, token])

  useEffect(() => {
    if (error) xtermRef.current?.write(`\r\n\x1b[33m${error}\x1b[0m\r\n${getPrompt()}`)
  }, [error, getPrompt])

  const handleConfirmCommand = () => {
    if (!confirmCommand) return
    sendCommand(confirmCommand, true)
    setConfirmCommand(null)
  }

  const handleCancelCommand = () => {
    xtermRef.current?.write(`\r\n명령 실행을 취소했습니다.\r\n${getPrompt()}`)
    setConfirmCommand(null)
  }

  return (
    <div className="terminal-container">
      <div className="terminal-status">
        {connectionStatus === 'connected' && <span className="status-connected">연결됨</span>}
        {connectionStatus === 'connecting' && <span className="status-connecting">연결 중...</span>}
        {connectionStatus === 'disconnected' && <span className="status-disconnected">연결 끊김</span>}
      </div>
      <div className="terminal-wrapper" ref={terminalElementRef}></div>
      {confirmCommand && <ConfirmModal title="명령 실행 확인" message={`다음 명령을 실행하시겠습니까?\n\n${confirmCommand}`} confirmLabel="실행" danger onConfirm={handleConfirmCommand} onCancel={handleCancelCommand} />}
    </div>
  )
}

export default Terminal
