import { MissionResponse } from '../../types/training'

interface MissionCopy {
  /** 화면 이름. 없으면 서버 이름을 쓴다. */
  name?: string
  description?: string
  /**
   * 미션이 끝난 뒤 디브리프에 보여 주는 원인과 복구 경로 (FE-27).
   * 정답을 담고 있으므로 진행 중에는 보여 주지 않는다. `백틱`은 명령으로 그린다.
   * 원본은 백엔드 주입기·검증기(backend/CLAUDE.md 장애 표)다.
   */
  cause: string
}

const missionCopy: Record<string, MissionCopy> = {
  pod_failure: {
    name: '멈춰 버린 배포',
    description: '새로 배포한 Nginx Pod가 잘못된 이미지 때문에 ImagePullBackOff에 멈춰 있습니다. 이미지를 바로잡아 배포를 끝내세요.',
    cause:
      'Deployment의 이미지가 존재하지 않는 태그로 바뀌어 새 Pod가 이미지를 받지 못했고, 기존 Pod만 Running으로 남아 응답하고 있었습니다. `kubectl describe pod`의 Events에서 실패한 이미지를 확인하고, 아직 Running인 기존 Pod의 이미지로 `kubectl set image`하거나 `kubectl rollout undo deployment/nginx`로 되돌리면 복구됩니다. Pod를 지우면 같은 잘못된 이미지로 다시 만들어질 뿐입니다.',
  },
  memory_stress: {
    name: '메모리 부족',
    description: '새로 배포한 Pod가 메모리 한도를 넘어 계속 종료됩니다(종료 코드 137). 리소스 제한을 확인하고 조정하세요.',
    cause:
      '앱이 시작할 때 쓰는 메모리보다 컨테이너 메모리 한도(limit, 6Mi)가 낮아 새 Pod가 반복 종료(종료 코드 137)됐습니다. `kubectl describe pod`의 Last State(Exit Code 137)와 Limits를 확인하고 `kubectl set resources deployment/nginx --limits=memory=128Mi`로 한도를 올리면 복구됩니다.',
  },
  service_misconfig: {
    name: '끊어진 연결',
    description: 'Service 설정 오류로 트래픽이 Pod에 전달되지 않습니다. selector 설정을 확인하세요.',
    cause:
      'Service의 selector가 Pod 라벨과 맞지 않아 Endpoints가 비어 있었습니다. `kubectl get endpoints`와 `kubectl get pods --show-labels`로 차이를 확인하고 selector를 고치면 트래픽이 흐릅니다.',
  },
  network_latency: {
    name: '응답 없는 서버',
    description: 'Pod는 Running인데 Ready가 되지 않아 Service가 트래픽을 보내지 못합니다. Readiness Probe 설정을 확인해 다시 트래픽을 받게 하세요.',
    cause:
      'readinessProbe가 존재하지 않는 경로를 검사해 Pod가 Running이어도 Ready가 되지 못했습니다. `kubectl describe pod`의 Readiness 실패 이벤트를 보고 probe를 고치거나 제거하면 복구됩니다.',
  },
  docker_container_stopped: {
    cause: '훈련 컨테이너가 중지돼 있었습니다. `docker ps -a`에서 Exited 상태를 확인하고 `docker start`로 다시 띄우면 복구됩니다.',
  },
  docker_network_disconnect: {
    cause:
      '컨테이너는 실행 중이었지만 훈련 네트워크에서 분리돼 다른 컨테이너와 통신하지 못했습니다. `docker inspect`의 Networks 항목을 보고 `docker network connect`로 다시 연결하면 복구됩니다.',
  },
  docker_cpu_throttle: {
    cause:
      '컨테이너 CPU 상한이 0.05 CPU로 줄어 응답이 느려졌습니다. 상한은 `docker stats`에 드러나지 않고 `docker inspect`의 HostConfig.NanoCpus로 확인합니다. `docker update --cpus 1`로 올리면 복구됩니다.',
  },
  linux_process_flood: {
    cause: '`afterfail-worker` 프로세스가 대량으로 생겨 있었습니다. `ps`로 같은 이름이 많은 것을 확인하고 `pkill -f`로 정리하면 복구됩니다.',
  },
  linux_disk_pressure: {
    cause: '작업 디렉터리에 큰 파일이 생겨 디스크가 가득 찼습니다. `df`와 `du`로 큰 파일을 찾아 지우면 복구됩니다.',
  },
  linux_cpu_saturation: {
    cause:
      'CPU를 태우는 워커 두 개가 돌고 있었습니다. 프로세스 수가 적어 목록만으로는 눈에 띄지 않고 `top`에서 CPU 사용률을 봐야 찾을 수 있습니다. `pkill -f`로 정리하면 복구됩니다.',
  },
}

/** 화면에 쓰는 미션 이름·설명. 카드와 인시던트 바가 같은 이름을 쓰도록 한 곳에서 정한다. */
export const getMissionCopy = (mission: Pick<MissionResponse, 'chaos_type' | 'name' | 'description'>) => {
  const copy = missionCopy[mission.chaos_type]
  return { name: copy?.name ?? mission.name, description: copy?.description ?? mission.description }
}

/** 디브리프의 원인 설명. 모르는 장애면 null — 없는 원인을 지어내지 않는다. */
export const getMissionCause = (chaosType: string): string | null => missionCopy[chaosType]?.cause ?? null

/**
 * 힌트 단계 (설계 문서 6.3.1). 힌트를 살 때마다 한 단계 올라가고, 미션이 끝날 때까지 튜터의
 * **모든 답**이 그 단계로 구체적이 된다 — 한 번 받고 끝나는 쪽지가 아니다. 뜻은 튜터 프롬프트
 * (`ai-data/prompts/socratic_tutor.md` 의 Hint levels)와 맞춘다. 0단계는 사지 않은 기본값이다.
 */
export const HINT_LEVELS = [
  { name: '질문으로 방향만', detail: '되묻는 질문으로 어디를 볼지 이끕니다. 원인과 명령은 말하지 않습니다.' },
  { name: '조사할 곳', detail: '관찰한 증거를 바탕으로 어디를 조사할지 짚어 줍니다.' },
  { name: '진단 명령', detail: '원인을 찾는 명령까지 알려 줍니다. 고치는 방법은 아직 말하지 않습니다.' },
  { name: '원인과 복구 방법', detail: '원인을 밝히고 고치는 명령과 그 이유를 알려 줍니다.' },
] as const

export const MAX_HINT_LEVEL = HINT_LEVELS.length - 1

/** 산 힌트 수 → 튜터 단계. 예전 시도처럼 3번 넘게 샀어도 3단계다. */
export const hintLevelOf = (hintsUsed: number) => Math.min(Math.max(hintsUsed, 0), MAX_HINT_LEVEL)
