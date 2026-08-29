import { getEnvironmentTerminal } from '../config/environments'
import { EnvironmentId } from '../types/training'

/**
 * 프롬프트. 환경과 namespace 를 함께 보여줘 지금 어디에 명령을 치는지 드러낸다 (FE-07).
 * namespace 가 아직 없을 수 있다 — 세션은 지연 생성되기 때문이다 (FE-04).
 */
export const getTerminalPrompt = (environment: EnvironmentId, namespace: string | undefined): string => {
  // user-<uuid> 는 길어서 줄인다. 다만 실제로 잘렸을 때만 ... 을 붙인다 —
  // 잘리지 않은 이름에 ... 이 붙으면 없는 뒷부분이 있는 것처럼 읽힌다.
  const NAMESPACE_MAX = 15
  const scope = namespace
    ? namespace.length > NAMESPACE_MAX
      ? `${namespace.slice(0, NAMESPACE_MAX)}...`
      : namespace
    : null

  return scope ? `[${environment}:${scope}]$ ` : `[${environment}]$ `
}

/**
 * 연결 전 입력에 대한 안내. 명령을 서버로 보내지 않으므로 왜 실행되지 않았는지
 * 사용자에게 알려야 한다.
 *
 * 이 환경에서 쓸 수 없는 명령인지, 아직 연결되지 않았을 뿐인지를 구분한다 —
 * 예전에는 어느 환경이든 "Only kubectl commands are allowed" 를 냈다.
 */
export const getOfflineCommandNotice = (environment: EnvironmentId, command: string): string => {
  const { binary } = getEnvironmentTerminal(environment)
  const trimmed = command.trim()

  // 명령 정책이 아직 없는 환경에서는 무엇이 허용되는지 단정하지 않는다.
  if (!binary) return '터미널이 아직 연결되지 않았습니다. 연결된 뒤 다시 실행해 주세요.'

  if (trimmed === binary || trimmed.startsWith(`${binary} `)) {
    return '터미널이 아직 연결되지 않았습니다. 연결된 뒤 다시 실행해 주세요.'
  }

  return `이 환경에서는 ${binary} 명령만 실행할 수 있습니다.`
}
