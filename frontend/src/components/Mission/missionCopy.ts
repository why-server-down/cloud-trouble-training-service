import { MissionResponse } from '../../types/training'

const missionCopy: Record<string, { name: string; description: string }> = {
  pod_failure: {
    name: '사라진 애플리케이션',
    description: 'Nginx Pod가 ImagePullBackOff 상태입니다. 이미지 이름을 수정하여 Pod를 정상 상태로 복구하세요.',
  },
  memory_stress: {
    name: '메모리 부족',
    description: '애플리케이션 Pod가 메모리 부족으로 종료됩니다. 리소스 제한을 확인하고 조정하세요.',
  },
  service_misconfig: {
    name: '끊어진 연결',
    description: 'Service 설정 오류로 트래픽이 Pod에 전달되지 않습니다. selector 설정을 확인하세요.',
  },
  network_latency: {
    name: '응답 없는 서버',
    description: 'Pod에 지속적인 장애가 발생합니다. 상태 확인 설정을 점검하고 자동 복구되도록 구성하세요.',
  },
}

/** 화면에 쓰는 미션 이름·설명. 카드와 인시던트 바가 같은 이름을 쓰도록 한 곳에서 정한다. */
export const getMissionCopy = (mission: Pick<MissionResponse, 'chaos_type' | 'name' | 'description'>) =>
  missionCopy[mission.chaos_type] || { name: mission.name, description: mission.description }
