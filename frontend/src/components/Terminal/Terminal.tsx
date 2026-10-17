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

/*
 * xterm 은 CSS 변수를 읽지 못해 팔레트를 값으로 옮긴다. 원본은 index.css 토큰이다
 * (--terminal-bg, --text, --accent, --ok/--warning/--danger/--info).
 * ANSI 색은 상태 색과 같은 계열로 채도를 낮춰 kubectl 출력이 화면과 따로 놀지 않게 한다.
 */
const TERMINAL_THEME = {
  background: '#0a0c0b',
  foreground: '#eceae4',
  cursor: '#ec8a4b',
  cursorAccent: '#0a0c0b',
  selectionBackground: 'rgba(236, 138, 75, 0.28)',
  black: '#1a1f1d',
  red: '#ef6f5f',
  green: '#8cc084',
  yellow: '#e2b54f',
  blue: '#86b4d9',
  magenta: '#c39ac4',
  cyan: '#7fbfb5',
  white: '#c9ccc6',
  brightBlack: '#737d78',
  brightRed: '#f4877a',
  brightGreen: '#a5d19d',
  brightYellow: '#ecc56e',
  brightBlue: '#a2c6e4',
  brightMagenta: '#d4b0d6',
  brightCyan: '#9cd2c9',
  brightWhite: '#f4f2ec',
}

const TERMINAL_FONT = '"IBM Plex Mono", "SF Mono", Menlo, Consolas, "IBM Plex Sans KR", monospace'
/** Plex Mono 가 아직 없을 때 쓰는 스택. 값이 달라야 로딩 후 바꿀 때 xterm 이 글자 폭을 다시 잰다. */
const TERMINAL_FALLBACK_FONT = '"SF Mono", Menlo, Consolas, "IBM Plex Sans KR", monospace'
const TERMINAL_FONT_SIZE = 13

const CONNECTION_LABEL = {
  connected: '연결됨',
  connecting: '연결 중',
  disconnected: '연결 끊김',
} as const

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

    const fontSpec = `${TERMINAL_FONT_SIZE}px "IBM Plex Mono"`
    const fonts = typeof document !== 'undefined' ? document.fonts : undefined
    const terminal = new XTerm({
      cursorBlink: true,
      fontSize: TERMINAL_FONT_SIZE,
      // Plex Mono 는 글꼴 자체 줄 높이가 1.3em 이라 배수는 작게 둔다.
      lineHeight: 1.1,
      fontFamily: fonts?.check(fontSpec) === false ? TERMINAL_FALLBACK_FONT : TERMINAL_FONT,
      theme: TERMINAL_THEME,
      rows: 30,
      cols: 100,
    })
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.open(terminalElementRef.current)
    xtermRef.current = terminal
    setTerminalReady(true)

    let disposed = false
    // 숨겨진(0 크기) 상태에서 맞추면 2열로 줄었다가 다시 펴지며 스크롤백이 재배치된다.
    const fit = () => {
      const element = terminalElementRef.current
      if (disposed || !element || element.clientWidth === 0 || element.clientHeight === 0) return
      // 숨긴 채 열렸으면 글자 폭이 0 이라 맞출 수 없다. 같은 크기로 resize 하면 xterm 이 다시 잰다 (xterm #785).
      if (!fitAddon.proposeDimensions()) terminal.resize(terminal.cols, terminal.rows)
      fitAddon.fit()
    }

    // 웹폰트가 늦게 오면 대체 글꼴 폭으로 잰 칸이 어긋난다. 도착하면 글꼴을 바꿔 다시 잰다.
    fonts?.load(fontSpec).then(() => {
      if (disposed) return
      terminal.options.fontFamily = TERMINAL_FONT
      fit()
    }, () => {})

    /*
     * 숨김 해제(모바일 탭), 패널 폭 변경, 창 크기 변경을 모두 컨테이너 크기 변화로 받는다.
     * jsdom 처럼 ResizeObserver 가 없으면 창 resize 로 대신한다.
     */
    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => fit())
    resizeObserver?.observe(terminalElementRef.current)
    const handleResize = () => fit()
    if (!resizeObserver) window.addEventListener('resize', handleResize)
    const fitTimer = window.setTimeout(fit, 0)

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
      disposed = true
      window.clearTimeout(fitTimer)
      resizeObserver?.disconnect()
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
        <span className={`terminal-connection status-${connectionStatus}`}>
          <span className="terminal-connection-dot" aria-hidden="true" />
          {CONNECTION_LABEL[connectionStatus]}
        </span>
      </div>
      <div className="terminal-wrapper" ref={terminalElementRef}></div>
      {confirmCommand && <ConfirmModal title="명령 실행 확인" message={`다음 명령을 실행하시겠습니까?\n\n${confirmCommand}`} confirmLabel="실행" danger onConfirm={handleConfirmCommand} onCancel={handleCancelCommand} />}
    </div>
  )
}

export default Terminal
