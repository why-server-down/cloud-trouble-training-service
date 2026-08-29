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

  it('명령 정책이 없는 환경에서는 무엇이 허용되는지 단정하지 않는다', () => {
    const notice = getOfflineCommandNotice('linux', 'systemctl status nginx')

    expect(notice).toContain('연결')
    expect(notice).not.toContain('만 실행할 수 있습니다')
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

  it('자동완성 후보는 그 환경의 실행 파일이거나 로컬 명령이다', () => {
    // 서버가 거절할 명령을 Tab 으로 완성해 주면 안 된다.
    for (const environment of ENVIRONMENT_IDS) {
      const { binary, completions } = ENVIRONMENT_TERMINAL[environment]
      for (const candidate of completions) {
        if (candidate === 'clear') continue
        expect(binary).not.toBeNull()
        expect(candidate.startsWith(`${binary} `)).toBe(true)
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
