import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Terminal as XTerm } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import ConfirmModal from '../Feedback/ConfirmModal'
import { useTerminalWebSocket } from '../../hooks/useTerminalWebSocket'
import { getEnvironmentTerminal } from '../../config/environments'
import { EnvironmentId } from '../../types/training'
import { getOfflineCommandNotice, getTerminalPrompt } from '../../utils/terminal'
import 'xterm/css/xterm.css'
import './Terminal.css'

interface TerminalProps {
  /** 이 터미널이 붙은 훈련 환경. 프롬프트·자동완성·안내 문구가 여기서 갈린다. */
  environment: EnvironmentId
  sessionId?: string
  token?: string
  namespace?: string
}

const Terminal: React.FC<TerminalProps> = ({ environment, sessionId, token, namespace }) => {
  const terminalElementRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<XTerm | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const currentLineRef = useRef('')
  const commandHistoryRef = useRef<string[]>([])
  const historyIndexRef = useRef(-1)
  const isConnectedRef = useRef(false)
  const commandQueueRef = useRef<{ cmd: string; wasEchoed: boolean }[]>([])
  const isExecutingRef = useRef(false)
  const onCommandCompleteRef = useRef<(() => void) | null>(null)
  const [confirmCommand, setConfirmCommand] = useState<string | null>(null)
  const [terminalReady, setTerminalReady] = useState(false)

  const terminalMeta = getEnvironmentTerminal(environment)
  const getPrompt = useCallback(
    () => getTerminalPrompt(environment, namespace),
    [environment, namespace],
  )

  /**
   * 환경이나 세션이 바뀌면 이전 입력을 물려주지 않는다. 큐에 남은 명령이
   * 그대로 실행되면 사용자가 이전 환경에서 친 명령이 새 환경으로 나간다.
   */
  useEffect(() => {
    commandQueueRef.current = []
    currentLineRef.current = ''
    isExecutingRef.current = false
    historyIndexRef.current = commandHistoryRef.current.length
  }, [environment, sessionId])

  const { isConnected, connectionStatus, error, sendCommand } = useTerminalWebSocket({
    environment,
    sessionId: sessionId || '',
    token: token || '',
    terminal: terminalReady ? xtermRef.current : null,
    namespace,
    onConfirmRequired: setConfirmCommand,
    onCommandComplete: useCallback(() => {
      onCommandCompleteRef.current?.()
    }, []),
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
      theme: { background: '#090d0c', foreground: '#e5dfd0', cursor: '#e88745', selectionBackground: '#3a281d' },
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

    const processNextCommand = () => {
      if (isExecutingRef.current) return
      if (commandQueueRef.current.length === 0) return

      const { cmd, wasEchoed } = commandQueueRef.current.shift()!
      isExecutingRef.current = true

      const command = cmd.trim()

      if (!wasEchoed) terminal.write(cmd + '\r\n')
      else terminal.write('\r\n')

      if (command === 'clear') {
        terminal.clear()
        terminal.write(getPrompt())
        isExecutingRef.current = false
        setTimeout(processNextCommand, 0)
        return
      }

      if (command) {
        commandHistoryRef.current.push(command)
        historyIndexRef.current = commandHistoryRef.current.length
        if (isConnectedRef.current && sessionId && token) {
          sendCommand(command)
        } else {
          terminal.writeln(getOfflineCommandNotice(environment, command))
          terminal.write(getPrompt())
          isExecutingRef.current = false
          setTimeout(processNextCommand, 0)
        }
      } else {
        terminal.write(getPrompt())
        isExecutingRef.current = false
        setTimeout(processNextCommand, 0)
      }
    }

    onCommandCompleteRef.current = () => {
      isExecutingRef.current = false
      processNextCommand()
    }

    const queueCommand = (cmd: string, wasEchoed: boolean) => {
      commandQueueRef.current.push({ cmd, wasEchoed })
      processNextCommand()
    }

    terminal.onData((data) => {
      if (data.length > 1 && (data.includes('\r') || data.includes('\n'))) {
        let normalizedData = data.replace(/\r\n/g, '\r').replace(/\n/g, '\r')
        if (!normalizedData.endsWith('\r')) {
          normalizedData += '\r'
        }
        const lines = normalizedData.split('\r')
        lines.forEach((line, index) => {
          if (index < lines.length - 1) {
            queueCommand(currentLineRef.current + line, false)
            currentLineRef.current = ''
          }
        })
        return
      }

      const code = data.charCodeAt(0)

      if (code === 13) {
        queueCommand(currentLineRef.current, true)
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
        const matches = terminalMeta.completions.filter((command) => command.startsWith(currentLineRef.current))
        if (matches.length === 1) {
          terminal.write(matches[0].slice(currentLineRef.current.length))
          currentLineRef.current = matches[0]
        } else if (matches.length > 1) {
          terminal.write(`\r\n  ${matches.join('\r\n  ')}\r\n${getPrompt()}${currentLineRef.current}`)
        }
      } else if (code >= 32 && code !== 127) {
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
  }, [environment, getPrompt, sendCommand, sessionId, terminalMeta, token])

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
        <span className="terminal-label">{terminalMeta.headerLabel}</span>
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
