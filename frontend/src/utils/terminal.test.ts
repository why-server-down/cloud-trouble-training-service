import { describe, expect, it } from 'vitest'

import { getOfflineCommandNotice, getTerminalPrompt } from './terminal'
import { ENVIRONMENT_TERMINAL } from '../config/environments'
import { ENVIRONMENT_IDS } from '../types/training'

describe('getTerminalPrompt (FE-07)', () => {
  it('환경과 namespace 를 함께 보여준다', () => {
    expect(getTerminalPrompt('docker', 'user-abc')).toBe('[docker:user-abc]$ ')
  })

  it('긴 user- namespace 는 줄여서 보여준다', () => {
    const prompt = getTerminalPrompt('kubernetes', 'user-0123456789abcdef0123')

    expect(prompt).toBe('[kubernetes:user-0123456789...]$ ')
  })

  it('user- 로 시작하지 않는 namespace 는 그대로 쓴다', () => {
    expect(getTerminalPrompt('kubernetes', 'training')).toBe('[kubernetes:training]$ ')
  })

  it('세션이 아직 없어 namespace 를 모를 때도 환경은 드러낸다', () => {
    // 세션은 지연 생성되므로 (FE-04) namespace 가 없는 순간이 실제로 존재한다.
    expect(getTerminalPrompt('linux', undefined)).toBe('[linux]$ ')
  })

  it('환경마다 프롬프트가 구분된다', () => {
    const prompts = ENVIRONMENT_IDS.map((environment) => getTerminalPrompt(environment, 'user-abc'))

    expect(new Set(prompts).size).toBe(ENVIRONMENT_IDS.length)
  })
})

describe('getOfflineCommandNotice (FE-07)', () => {
  it('연결 전 그 환경의 명령을 치면 연결 대기라고 알린다', () => {
    expect(getOfflineCommandNotice('docker', 'docker ps -a')).toContain('연결')
    expect(getOfflineCommandNotice('docker', 'docker ps -a')).not.toContain('kubectl')
  })

  it('실행 파일만 친 경우도 그 환경 명령으로 본다', () => {
    expect(getOfflineCommandNotice('kubernetes', 'kubectl')).toContain('연결')
  })

  it('다른 환경 명령을 치면 이 환경에서 쓸 수 있는 것을 알려준다', () => {
    expect(getOfflineCommandNotice('docker', 'kubectl get pods')).toBe(
      '이 환경에서는 docker 명령만 실행할 수 있습니다.',
    )
  })

  it('Kubernetes 전용 문구가 다른 환경에 새어나오지 않는다', () => {
    expect(getOfflineCommandNotice('docker', 'ls -al')).not.toContain('kubectl')
  })

  it('앞뒤 공백이 있어도 같은 명령으로 본다', () => {
    expect(getOfflineCommandNotice('docker', '   docker ps   ')).toContain('연결')
  })

  it('접두사만 같은 다른 명령은 그 환경 명령으로 오인하지 않는다', () => {
    // 'dockerize' 는 docker 가 아니다.
    expect(getOfflineCommandNotice('docker', 'dockerize --help')).toBe(
      '이 환경에서는 docker 명령만 실행할 수 있습니다.',
    )
  })

  it('allowlist 환경에서는 허용 목록에 없는 명령을 먼저 구분해 알린다 (FE-09)', () => {
    // LinuxPolicy 가 systemd 부재로 배제한 명령이다. 정답으로 착각하게 두지 않는다.
    const notice = getOfflineCommandNotice('linux', 'systemctl status nginx')

    expect(notice).toContain('systemctl')
    expect(notice).toContain('실행할 수 없습니다')
    // 단일 바이너리 문구를 쓰면 안 된다 — Linux 는 실행 파일이 하나가 아니다.
    expect(notice).not.toContain('명령만 실행할 수 있습니다')
  })

  it('allowlist 환경에서 허용된 명령은 연결 문제로 안내한다 (FE-09)', () => {
    expect(getOfflineCommandNotice('linux', 'ps aux')).toContain('연결')
    expect(getOfflineCommandNotice('linux', 'df -h')).toContain('연결')
    expect(getOfflineCommandNotice('linux', '')).toContain('연결')
  })

  it('allowlist 판정은 argv[0] 만 본다 — 접두어가 같은 다른 명령을 통과시키지 않는다', () => {
    expect(getOfflineCommandNotice('linux', 'psql -l')).toContain('실행할 수 없습니다')
    expect(getOfflineCommandNotice('linux', 'dfx')).toContain('실행할 수 없습니다')
  })

  it('빈 명령에도 안내를 낸다', () => {
    expect(getOfflineCommandNotice('kubernetes', '')).toBeTruthy()
  })
})

describe('환경별 터미널 설정 (FE-07)', () => {
  it('모든 환경이 헤더 라벨과 자동완성 목록을 갖는다', () => {
    for (const environment of ENVIRONMENT_IDS) {
      const meta = ENVIRONMENT_TERMINAL[environment]
      expect(meta.headerLabel).toBeTruthy()
      expect(meta.completions.length).toBeGreaterThan(0)
    }
  })

  it('자동완성 후보는 그 환경의 정책 안에 있다', () => {
    // 서버가 거절할 명령을 Tab 으로 완성해 주면 안 된다.
    for (const environment of ENVIRONMENT_IDS) {
      const { binary, allowedCommands, completions } = ENVIRONMENT_TERMINAL[environment]
      // 두 정책 형태 중 정확히 하나만 갖는다.
      expect(Boolean(binary) !== Boolean(allowedCommands), `${environment} 정책 형태`).toBe(true)

      for (const candidate of completions) {
        if (candidate === 'clear') continue
        if (binary) {
          expect(candidate.startsWith(`${binary} `), candidate).toBe(true)
        } else {
          expect(allowedCommands, candidate).toContain(candidate.split(/\s+/)[0])
        }
      }
    }
  })

  it('Docker 자동완성은 백엔드가 막는 명령을 제안하지 않는다', () => {
    // BE-12 DockerPolicy.BLOCKED_COMMANDS 중 오해하기 쉬운 것들.
    const blocked = ['run', 'exec', 'build', 'pull', 'push', 'compose', 'system', 'cp']
    const suggested = ENVIRONMENT_TERMINAL.docker.completions

    for (const subcommand of blocked) {
      expect(suggested.some((candidate) => candidate.startsWith(`docker ${subcommand}`))).toBe(false)
    }
  })

  it('Docker 자동완성에 계획서가 요구한 최소 조사 명령이 모두 있다', () => {
    const required = [
      'docker ps -a',
      'docker inspect ',
      'docker logs ',
      'docker stats --no-stream',
      'docker network ls',
      'docker network inspect ',
      'docker volume ls',
      'docker volume inspect ',
    ]

    for (const command of required) {
      expect(ENVIRONMENT_TERMINAL.docker.completions).toContain(command)
    }
  })

  it('환경마다 헤더 라벨이 다르다', () => {
    const labels = ENVIRONMENT_IDS.map((id) => ENVIRONMENT_TERMINAL[id].headerLabel)

    expect(new Set(labels).size).toBe(ENVIRONMENT_IDS.length)
  })
})

describe('Linux 터미널 설정 (FE-09)', () => {
  const linux = ENVIRONMENT_TERMINAL.linux

  it('계획서 목록이 아니라 LinuxPolicy 실측 목록을 따른다', () => {
    // BE-16 이 배제한 명령들: systemd 가 없고 커널 링 버퍼도 막혀 있다.
    for (const excluded of ['systemctl', 'journalctl', 'dmesg']) {
      expect(linux.allowedCommands).not.toContain(excluded)
      expect(linux.completions.some((c) => c.startsWith(excluded))).toBe(false)
    }
  })

  it('실제 장애 유형을 조사할 명령을 제안한다', () => {
    // linux_chaos_injector: disk_pressure / cpu_saturation / process_flood
    const heads = linux.completions.map((c) => c.split(/\s+/)[0])
    for (const command of ['ps', 'df', 'du', 'top', 'free', 'pstree', 'cat']) {
      expect(heads, command).toContain(command)
    }
  })

  it('경로를 받는 명령에 값이 분리되는 플래그를 붙이지 않는다', () => {
    /*
     * LinuxPolicy._check_paths 는 argv 에서 `-` 로 시작하지 않는 토큰을 전부
     * 경로로 본다. `tail -n 50 <path>` 의 `50` 이 경로로 오인돼 거절된다.
     */
    const pathCommands = ['cat', 'head', 'tail', 'wc', 'ls', 'stat', 'find', 'rm', 'truncate']
    for (const candidate of linux.completions) {
      const [head, ...rest] = candidate.trim().split(/\s+/)
      if (!pathCommands.includes(head)) continue
      const flagIndexes = rest.flatMap((token, i) => (token.startsWith('-') ? [i] : []))
      for (const i of flagIndexes) {
        const next = rest[i + 1]
        if (next === undefined) continue
        expect(next.startsWith('/') || next.startsWith('.'), candidate).toBe(true)
      }
    }
  })

  it('신호 명령은 훈련 프로세스 접두어를 붙여 제안한다', () => {
    // LinuxPolicy._check_signal_target 은 PID 또는 afterfail- 이름만 받는다.
    expect(linux.completions).toContain('pkill -f afterfail-')
  })

  it('쓰기 가능한 경로만 제안한다', () => {
    for (const candidate of linux.completions) {
      const head = candidate.trim().split(/\s+/)[0]
      if (head !== 'rm' && head !== 'truncate') continue
      expect(candidate, candidate).toContain('/tmp/afterfail')
    }
  })

  it('모든 환경이 조사 시작 명령을 갖고, 그 명령은 자동완성 정책과 같은 범위다', () => {
    for (const environment of ENVIRONMENT_IDS) {
      const { binary, allowedCommands, investigationStarters } = ENVIRONMENT_TERMINAL[environment]
      expect(investigationStarters.length, environment).toBeGreaterThan(0)
      for (const starter of investigationStarters) {
        if (binary) expect(starter.startsWith(`${binary} `), starter).toBe(true)
        else expect(allowedCommands, starter).toContain(starter.split(/\s+/)[0])
      }
    }
  })
})
