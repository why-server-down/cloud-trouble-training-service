import {
  ENVIRONMENT_IDS,
  EnvironmentId,
  EnvironmentStatus,
  isEnvironmentStatus,
} from '../types/training'

/**
 * 환경 탭에 쓰는 표시 문구.
 *
 * 백엔드 `GET /api/environments` 는 id / status / capabilities 만 내보내고
 * label 같은 표시 문구는 프론트 책임이라고 계약되어 있다
 * (`backend/app/api/environments.py` docstring).
 * 그래서 이 파일은 순수 표시용 메타만 갖고, 가용성 판단은 담지 않는다.
 */
export interface EnvironmentDisplayMeta {
  label: string
  subtitle: string
  /** 미션 시작 전 field guide 의 "상태 조사" 단계 설명 (FE-09). */
  investigationHint: string
}

/** Record 로 선언해 환경이 추가되면 컴파일 단계에서 누락이 드러나게 한다. */
export const ENVIRONMENT_META: Record<EnvironmentId, EnvironmentDisplayMeta> = {
  kubernetes: {
    label: 'Kubernetes',
    subtitle: '쿠버네티스 장애 대응',
    investigationHint: 'Pod, Deployment, Service 상태와 이벤트를 차례로 확인합니다.',
  },
  docker: {
    label: 'Docker',
    subtitle: '컨테이너 운영',
    investigationHint: '컨테이너 상태와 로그, 네트워크·볼륨 설정을 차례로 확인합니다.',
  },
  linux: {
    label: 'Linux',
    subtitle: '시스템 관리',
    investigationHint: '프로세스, 디스크 사용량, 부하 지표를 차례로 확인합니다.',
  },
}

/**
 * 환경별 터미널 설정 (FE-07).
 *
 * `binary` 와 `completions` 의 원본은 백엔드 명령 정책
 * (`backend/app/services/command_validator.py`) 이다. 프론트가 여기서 더 넓게
 * 제안하면 사용자는 서버가 거절할 명령을 Tab 으로 완성하게 된다.
 */
export interface EnvironmentTerminalMeta {
  /** 터미널 헤더 라벨. 어느 환경의 셸인지 한눈에 보이게 한다. */
  headerLabel: string
  /**
   * argv[0] 이 고정 실행 파일인 환경의 그 실행 파일 (kubectl / docker).
   * 명령 자체가 argv[0] 인 환경(Linux)은 null 이고 `allowedCommands` 를 쓴다.
   */
  binary: string | null
  /**
   * argv[0] 자체로 허용 여부가 갈리는 환경의 명령 목록 (FE-09).
   * 원본은 `LinuxPolicy` 의 READ_COMMANDS + FILE_READ_COMMANDS + RECOVERY_COMMANDS 다.
   * binary 환경은 null.
   */
  allowedCommands: readonly string[] | null
  /** Tab 자동완성 후보. */
  completions: readonly string[]
  /**
   * 미션 시작 전 field guide 에 보여줄 조사 시작 명령 (FE-09).
   * 예전에는 App.tsx 에 kubectl 명령이 하드코딩돼 Docker/Linux 탭에서도 그대로 보였다.
   */
  investigationStarters: readonly string[]
}

export const ENVIRONMENT_TERMINAL: Record<EnvironmentId, EnvironmentTerminalMeta> = {
  kubernetes: {
    headerLabel: 'SHELL / KUBECTL',
    binary: 'kubectl',
    allowedCommands: null,
    investigationStarters: [
      'kubectl get pods',
      'kubectl get deployments',
      'kubectl get services',
      'kubectl get events --sort-by=.metadata.creationTimestamp',
    ],
    completions: [
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
      'clear',
    ],
  },
  docker: {
    headerLabel: 'SHELL / DOCKER',
    binary: 'docker',
    allowedCommands: null,
    investigationStarters: [
      'docker ps -a',
      'docker logs ',
      'docker inspect ',
      'docker network inspect ',
    ],
    // BE-12 DockerPolicy 의 READ_COMMANDS / READ_SUBCOMMANDS / RECOVERY_COMMANDS 범위 안에서만 고른다.
    completions: [
      'docker ps',
      'docker ps -a',
      'docker images',
      'docker inspect ',
      'docker logs ',
      'docker stats --no-stream',
      'docker top ',
      'docker diff ',
      'docker port ',
      'docker network ls',
      'docker network inspect ',
      'docker volume ls',
      'docker volume inspect ',
      'docker container ls',
      'docker container inspect ',
      'docker start ',
      'docker restart ',
      'docker stop ',
      'docker unpause ',
      'docker update --memory ',
      'docker version',
      'docker info',
      'clear',
    ],
  },
  linux: {
    headerLabel: 'SHELL / LINUX',
    // Linux 는 단일 바이너리가 아니라 명령 자체가 argv[0] 이다 (BE-16 LinuxPolicy).
    binary: null,
    // LinuxPolicy 의 READ_COMMANDS + FILE_READ_COMMANDS + RECOVERY_COMMANDS 를 그대로 옮겼다.
    allowedCommands: [
      'ps', 'free', 'df', 'du', 'top', 'uptime', 'iostat',
      'ss', 'netstat', 'lsof', 'pstree', 'id', 'whoami', 'env',
      'cat', 'head', 'tail', 'wc', 'ls', 'stat', 'find',
      'kill', 'pkill', 'rm', 'truncate',
    ],
    // 실제 장애 유형(disk_pressure / cpu_saturation / process_flood)을 조사하는 순서대로.
    investigationStarters: ['ps aux', 'df -h', 'top -b -n 1', 'cat /proc/loadavg'],
    /*
     * 계획서 FE-09 의 최소 목록에는 systemctl / journalctl / dmesg 가 있지만
     * LinuxPolicy 가 셋 다 배제한다 — 이 이미지에 systemd 가 없고 커널 링 버퍼도
     * 막혀 있다(BE-16 실측). 제안하면 사용자가 그것을 정답으로 착각한다.
     *
     * 값이 분리되는 플래그(`-n 50`, `-s 0`)는 예전에 넣을 수 없었다 —
     * `LinuxPolicy._check_paths` 가 플래그 값을 경로로 오인해 거절했다. 백엔드가
     * 명령별 `VALUE_FLAGS` 표로 고쳤으므로(2026-09-02) 이제 넣는다. 아래 항목은
     * `CommandValidator.validate_command(..., environment='linux')` 에 그대로 넣어
     * OK / CONFIRM 을 확인한 것만 남겼다. 표에 없는 플래그는 여전히 값이 경로로
     * 읽히므로, 새 항목을 넣기 전에 `VALUE_FLAGS` 를 먼저 본다.
     */
    completions: [
      'ps aux',
      'ps -ef',
      'ps -o pid,rss,comm',
      'pstree -p',
      'top -b -n 1',
      'uptime',
      'free -m',
      'df -h',
      'du -sh /tmp/afterfail',
      'du -d 1 /tmp/afterfail',
      'iostat',
      'ss -lntp',
      'netstat -lntp',
      'lsof ',
      'id',
      'whoami',
      'env',
      'cat /proc/loadavg',
      'cat /proc/meminfo',
      'ls -al /tmp/afterfail',
      'find /tmp/afterfail',
      'find /tmp/afterfail -type f',
      'stat ',
      'stat -c %s /tmp/afterfail/',
      'head ',
      'head -n 50 /tmp/afterfail/',
      'tail ',
      'tail -n 50 /tmp/afterfail/',
      'wc -l ',
      // 복구 계열. 전부 확인 계약을 거친다(LinuxPolicy.CONFIRM_SUBCOMMANDS).
      'kill ',
      'kill -s TERM ',
      'pkill -f afterfail-',
      'rm /tmp/afterfail/',
      'truncate -s 0 /tmp/afterfail/',
      'clear',
    ],
  },
}

export const getEnvironmentTerminal = (environment: EnvironmentId): EnvironmentTerminalMeta =>
  ENVIRONMENT_TERMINAL[environment]

/**
 * 환경별 관측(Grafana / Prometheus) 설정 (FE-08).
 *
 * 대시보드 정의의 원본은 `infra/monitoring/grafana/dashboards/` 다(백엔드 소유 경로).
 * 지금 존재하는 것은 `k8s-survival-overview` 하나뿐이므로 Docker / Linux 는
 * `dashboard: null` 이다 — 없는 UID 를 추측해 iframe 을 띄우면 사용자에게
 * Grafana 404 가 보인다. 대시보드가 추가되면 이 표만 채우면 화면이 열린다.
 */
export interface EnvironmentObservabilityMeta {
  /** Grafana 대시보드. 이 환경 전용 대시보드가 없으면 null. */
  dashboard: {
    uid: string
    /** URL 경로의 slug. Grafana 는 slug 가 틀려도 열어주지만 링크 가독성을 위해 맞춘다. */
    slug: string
    /** scope 값을 넘길 대시보드 변수 이름. */
    scopeVar: string
  } | null
  /**
   * readiness 판정에 쓸 PromQL. `{scope}` 자리에 escape 된 scope 가 들어간다.
   * 대시보드가 없는 환경은 null 이다 — 없는 화면의 준비 상태를 물을 이유가 없다.
   */
  readinessQueryTemplate: string | null
}

export const ENVIRONMENT_OBSERVABILITY: Record<EnvironmentId, EnvironmentObservabilityMeta> = {
  kubernetes: {
    dashboard: {
      uid: 'k8s-survival-overview',
      slug: 'afterfail-incident-triage',
      scopeVar: 'namespace',
    },
    readinessQueryTemplate: 'sum(kube_pod_status_phase{namespace=~"{scope}"})',
  },
  // BE 소유의 infra/monitoring 에 Docker 컨테이너 메트릭 대시보드가 아직 없다.
  docker: { dashboard: null, readinessQueryTemplate: null },
  // Linux 샌드박스 메트릭 대시보드도 마찬가지다.
  linux: { dashboard: null, readinessQueryTemplate: null },
}

export const GRAFANA_BASE_URL = import.meta.env.VITE_GRAFANA_BASE_URL || 'http://localhost:3001'
export const PROMETHEUS_BASE_URL = import.meta.env.VITE_PROMETHEUS_BASE_URL || 'http://localhost:9090'

/** PromQL 라벨 값 안의 특수문자. 이걸 빼먹으면 namespace 에 `"` 가 있을 때 쿼리가 깨진다. */
export const escapePrometheusLabelValue = (value: string) =>
  value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')

export const hasObservabilityDashboard = (environment: EnvironmentId | null): boolean =>
  Boolean(environment && ENVIRONMENT_OBSERVABILITY[environment].dashboard)

/**
 * 관측 대시보드 URL. 대시보드가 없는 환경은 null 을 준다.
 * 호출자는 null 을 "관측 없음"으로 표시해야 한다 — K8s 대시보드로 대체하지 않는다.
 */
export const getGrafanaUrl = (
  environment: EnvironmentId | null,
  scope: string | null,
): string | null => {
  if (!environment) return null
  const { dashboard } = ENVIRONMENT_OBSERVABILITY[environment]
  if (!dashboard) return null
  return (
    `${GRAFANA_BASE_URL}/d/${dashboard.uid}/${dashboard.slug}` +
    `?orgId=1&kiosk&refresh=5s` +
    `&var-${dashboard.scopeVar}=${encodeURIComponent(scope || '.*')}`
  )
}

/** readiness probe URL. 대시보드가 없으면 null — polling 자체를 하지 않게 한다. */
export const getGrafanaDataProbeUrl = (
  environment: EnvironmentId | null,
  scope: string | null,
): string | null => {
  if (!environment) return null
  const { readinessQueryTemplate } = ENVIRONMENT_OBSERVABILITY[environment]
  if (!readinessQueryTemplate) return null
  const query = readinessQueryTemplate.replace(
    '{scope}',
    escapePrometheusLabelValue(scope || '.*'),
  )
  return `${PROMETHEUS_BASE_URL}/api/v1/query?query=${encodeURIComponent(query)}`
}

/** 탭 노출 순서. 백엔드 SUPPORTED_ENVIRONMENTS 순서를 그대로 따른다. */
export const ENVIRONMENT_ORDER: readonly EnvironmentId[] = ENVIRONMENT_IDS

export const getEnvironmentMeta = (environment: EnvironmentId): EnvironmentDisplayMeta =>
  ENVIRONMENT_META[environment]

/**
 * 상태별 보조 문구. tooltip 없이도 읽히도록 탭 안에 직접 노출한다(FE-03 인수 조건).
 * 백엔드가 아직 내보내지 않는 status 는 `statusNote()` 가 '상태 확인 불가'로 처리한다.
 */
export const ENVIRONMENT_STATUS_NOTES: Record<EnvironmentStatus, string> = {
  available: '훈련 가능',
  degraded: '일부 기능 불안정',
  preparing: '준비 중',
  disabled: '사용 중지',
}

export const statusNote = (status: string): string =>
  isEnvironmentStatus(status) ? ENVIRONMENT_STATUS_NOTES[status] : '상태 확인 불가'

/**
 * 선택 가능한 상태. degraded 는 경고를 띄우되 진입은 허용한다.
 * 모르는 status 는 선택 불가로 처리한다 — 실행 가능 여부를 낙관하지 않는다.
 */
export const isSelectableStatus = (status: string): boolean =>
  status === 'available' || status === 'degraded'

/** 준비 중 환경에서 무엇이 열릴 예정인지. 탭이 눌리지 않으므로 별도 섹션에 보여준다. */
export const ENVIRONMENT_ROADMAP: Record<EnvironmentId, string[]> = {
  kubernetes: [],
  docker: [
    'Docker Compose 서비스 장애 시뮬레이션',
    '컨테이너 리소스 제한 실습',
    '네트워크 격리 및 볼륨 마운트 문제 해결',
  ],
  linux: [
    '프로세스 및 서비스 장애 대응',
    '디스크 / 메모리 / CPU 포화 상태 복구',
    '시스템 로그 분석 및 트러블슈팅',
  ],
}

/**
 * 캡스톤2 스코프에서 빠진 영역. AGENTS.md 결정에 따라 "개발 예정" 탭이 아니라
 * 후속 연구로 표기하며, 백엔드 SUPPORTED_ENVIRONMENTS 에도 없다.
 */
export const RESEARCH_TOPICS: { label: string; note: string }[] = [
  { label: 'Application', note: '앱 성능 저하 · API 에러 패턴 분석' },
  { label: 'Database', note: '쿼리 지연 · 커넥션 풀 고갈 대응' },
]
