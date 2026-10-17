import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Terminal as XTerm } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import ConfirmModal from '../Feedback/ConfirmModal'
import { useTerminalWebSocket } from '../../hooks/useTerminalWebSocket'
import { getEnvironmentTerminal } from '../../config/environments'
import {
  deleteBackward,
  deleteForward,
  deleteToStart,
  deleteWordBackward,
  EditResult,
  insertText,
  moveEnd,
  moveHome,
  moveLeft,
  moveRight,
  replaceLine,
} from '../../utils/lineEditor'
import { EnvironmentId } from '../../types/training'
import {
  getOfflineCommandNotice,
  getTerminalPrompt,
  TERMINAL_COMMAND_EVENT,
  TERMINAL_INSERT_EVENT,
} from '../../utils/terminal'
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
  /** 입력줄 안 커서 위치 (글자 수). ←/→ 로 줄 중간을 고칠 수 있다 (FE-28). */
  const cursorRef = useRef(0)
  /** Esc 로 터미널을 빠져나갈 때 focus 를 받을 자리. 그다음 Tab 이 다음 요소로 간다. */
  const exitTargetRef = useRef<HTMLDivElement>(null)
  /** 여러 줄 붙여넣기. 바로 실행하지 않고 확인을 받는다 (FE-28). */
  const [pendingPaste, setPendingPaste] = useState<string[] | null>(null)
  const queueCommandsRef = useRef<((commands: string[]) => void) | null>(null)
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
    cursorRef.current = 0
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
      /*
       * 스크린리더가 출력과 입력줄을 읽을 수 있게 접근성 트리를 함께 그린다 (FE-28).
       * 꺼 두면 캔버스만 있어 화면을 읽는 사용자에게 터미널은 빈 상자다.
       */
      screenReaderMode: true,
      rows: 30,
      cols: 100,
    })
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.open(terminalElementRef.current)
    xtermRef.current = terminal
    setTerminalReady(true)
    // 긴 명령이 줄바꿈돼도 `\b` 로 윗줄까지 커서를 옮길 수 있게 한다 (reverse wraparound).
    terminal.write('\x1b[?45h')
    /*
     * 스크린리더가 읽을 이름과 빠져나가는 방법 (FE-28). xterm 기본 이름은 영어 "Terminal input"
     * 이고, Tab 은 자동완성에 쓰여 Tab 으로는 나갈 수 없다.
     */
    terminal.textarea?.setAttribute('aria-label', `${terminalMeta.headerLabel} 입력`)
    terminal.textarea?.setAttribute('aria-describedby', 'terminal-exit-hint')
    /*
     * xterm 은 출력 live region 을 assertive 로 만든다. kubectl 표가 나올 때마다 다른 낭독을
     * 끊고 끼어들어서 polite 로 낮춘다.
     */
    terminalElementRef.current
      .querySelectorAll('[aria-live="assertive"]')
      .forEach((region) => region.setAttribute('aria-live', 'polite'))
    /*
     * 터미널이 열리면 바로 칠 수 있게 focus 를 준다 (미션 시작 직후 focus 가 숨은 카드에 남던 문제).
     * 터치 기기는 가상 키보드가 화면 절반을 덮으므로 사용자가 눌렀을 때만 연다.
     */
    if (window.matchMedia?.('(pointer: fine)').matches) terminal.focus()

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

    const lineState = () => ({ line: currentLineRef.current, cursor: cursorRef.current })
    /** 편집 결과를 입력줄 상태에 반영하고 화면에 그린다. */
    const commit = (result: EditResult) => {
      currentLineRef.current = result.line
      cursorRef.current = result.cursor
      if (result.output) terminal.write(result.output)
    }
    const resetLine = () => {
      currentLineRef.current = ''
      cursorRef.current = 0
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
          // 결과 시트의 "내가 실행한 명령"용. 연결이 없어 보내지 못한 명령은 알리지 않는다.
          window.dispatchEvent(new CustomEvent<string>(TERMINAL_COMMAND_EVENT, { detail: command }))
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
    // 붙여넣기 확인 시트가 확정되면 이 경로로 차례로 실행한다.
    queueCommandsRef.current = (commands) => commands.forEach((command) => queueCommand(command, false))

    /*
     * 브리핑에서 누른 조사 명령 (FE-26). 실행하지 않고 입력줄에만 붙인다 —
     * 사용자가 확인하고 Enter 를 누른다. 입력 중이던 내용은 지우지 않는다.
     */
    const handleInsert = (event: Event) => {
      const command = (event as CustomEvent<unknown>).detail
      if (typeof command !== 'string' || !command) return
      commit(moveEnd(lineState()))
      const text = currentLineRef.current && !currentLineRef.current.endsWith(' ') ? ` ${command}` : command
      commit(insertText(lineState(), text))
      terminal.focus()
    }
    window.addEventListener(TERMINAL_INSERT_EVENT, handleInsert)

    terminal.onData((data) => {
      /*
       * 여러 줄 붙여넣기 (FE-28). 예전에는 줄마다 확인 없이 연달아 실행했다. 한 줄이면
       * 그대로 입력하고 실행하지만, 두 줄 이상이면 무엇이 실행될지 보여 주고 확인을 받는다.
       */
      if (data.length > 1 && /[\r\n]/.test(data)) {
        const lines = data.replace(/\r\n?/g, '\n').split('\n').map((line) => line.trim()).filter(Boolean)
        if (lines.length === 1) {
          commit(insertText(lineState(), lines[0]))
          const command = currentLineRef.current
          commit(moveEnd(lineState()))
          resetLine()
          queueCommand(command, true)
        } else if (lines.length > 1) {
          setPendingPaste(lines)
        }
        return
      }

      // Esc: 터미널에서 빠져나간다. 그다음 Tab 이 다음 요소로 간다 (키보드 트랩 방지).
      if (data === '\x1b') {
        terminal.blur()
        exitTargetRef.current?.focus()
        return
      }

      const code = data.charCodeAt(0)

      if (code === 13) {
        const command = currentLineRef.current
        commit(moveEnd(lineState()))
        resetLine()
        queueCommand(command, true)
      } else if (code === 127) {
        commit(deleteBackward(lineState()))
      } else if (data === '\x1b[3~') {
        commit(deleteForward(lineState()))
      } else if (data === '\x1b[D') {
        commit(moveLeft(lineState()))
      } else if (data === '\x1b[C') {
        commit(moveRight(lineState()))
      } else if (code === 1 || data === '\x1b[H' || data === '\x1bOH' || data === '\x1b[1~') {
        commit(moveHome(lineState()))
      } else if (code === 5 || data === '\x1b[F' || data === '\x1bOF' || data === '\x1b[4~') {
        commit(moveEnd(lineState()))
      } else if (code === 21) {
        commit(deleteToStart(lineState()))
      } else if (code === 23) {
        commit(deleteWordBackward(lineState()))
      } else if (data === '\x1b[A') {
        if (historyIndexRef.current > 0) {
          historyIndexRef.current -= 1
          commit(replaceLine(lineState(), commandHistoryRef.current[historyIndexRef.current]))
        }
      } else if (data === '\x1b[B') {
        if (historyIndexRef.current < commandHistoryRef.current.length - 1) {
          historyIndexRef.current += 1
          commit(replaceLine(lineState(), commandHistoryRef.current[historyIndexRef.current]))
        } else {
          historyIndexRef.current = commandHistoryRef.current.length
          commit(replaceLine(lineState(), ''))
        }
      } else if (code === 3) {
        // Ctrl+C 는 입력 중인 줄을 버린다. 서버에서 이미 실행 중인 명령은 멈추지 않는다(명령마다 시간 제한이 있다).
        terminal.write(`^C\r\n${getPrompt()}`)
        resetLine()
      } else if (code === 12) {
        terminal.clear()
        terminal.write(getPrompt())
        resetLine()
      } else if (code === 9) {
        // 자동완성은 줄 끝에서, 무언가 입력했을 때만. 빈 줄에서 목록 전체를 쏟아내지 않는다.
        const line = currentLineRef.current
        if (!line.trim() || cursorRef.current !== line.length) return
        const matches = terminalMeta.completions.filter((command) => command.startsWith(line))
        if (matches.length === 1) {
          commit(insertText(lineState(), matches[0].slice(line.length)))
        } else if (matches.length > 1) {
          terminal.write(`\r\n  ${matches.join('\r\n  ')}\r\n${getPrompt()}${line}`)
        }
      } else if (code >= 32 && !data.startsWith('\x1b')) {
        commit(insertText(lineState(), data))
      }
    })

    return () => {
      disposed = true
      window.removeEventListener(TERMINAL_INSERT_EVENT, handleInsert)
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

  const confirmPaste = () => {
    const commands = pendingPaste
    setPendingPaste(null)
    if (commands) queueCommandsRef.current?.(commands)
    xtermRef.current?.focus()
  }

  const cancelPaste = () => {
    setPendingPaste(null)
    xtermRef.current?.focus()
  }

  const handleCancelCommand = () => {
    xtermRef.current?.write(`\r\n명령 실행을 취소했습니다.\r\n${getPrompt()}`)
    setConfirmCommand(null)
  }

  return (
    <div className="terminal-container">
      <div className="terminal-status">
        <span className="terminal-label">{terminalMeta.headerLabel}</span>
        <span id="terminal-exit-hint" className="terminal-exit-hint">Esc: 터미널에서 나가기</span>
        <span className={`terminal-connection status-${connectionStatus}`} role="status">
          <span className="terminal-connection-dot" aria-hidden="true" />
          {CONNECTION_LABEL[connectionStatus]}
        </span>
      </div>
      <div className="terminal-wrapper" ref={terminalElementRef}></div>
      {/*
        * Esc 로 나왔을 때 focus 가 머무는 자리. 터미널 뒤에 있어야 다음 Tab 이 터미널 안쪽이
        * 아니라 다음 요소로 간다.
        */}
      <div
        className="terminal-exit-target"
        ref={exitTargetRef}
        tabIndex={-1}
        aria-label={`${terminalMeta.headerLabel}에서 나왔습니다`}
      />
      {pendingPaste && (
        <ConfirmModal
          title={`붙여넣은 명령 ${pendingPaste.length}개 실행`}
          message={`아래 명령을 차례로 실행합니다.\n\n${pendingPaste.join('\n')}`}
          confirmLabel="차례로 실행"
          onConfirm={confirmPaste}
          onCancel={cancelPaste}
        />
      )}
      {confirmCommand && <ConfirmModal title="명령 실행 확인" message={`다음 명령을 실행하시겠습니까?\n\n${confirmCommand}`} confirmLabel="실행" danger onConfirm={handleConfirmCommand} onCancel={handleCancelCommand} />}
    </div>
  )
}

export default Terminal
