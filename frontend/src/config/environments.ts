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
}

/** Record 로 선언해 환경이 추가되면 컴파일 단계에서 누락이 드러나게 한다. */
export const ENVIRONMENT_META: Record<EnvironmentId, EnvironmentDisplayMeta> = {
  kubernetes: { label: 'Kubernetes', subtitle: '쿠버네티스 장애 대응' },
  docker: { label: 'Docker', subtitle: '컨테이너 운영' },
  linux: { label: 'Linux', subtitle: '시스템 관리' },
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
   * 이 환경에서 실행할 수 있는 명령의 실행 파일.
   * 백엔드 정책이 아직 없는 환경은 null 이다 — 없는 정책을 추측해 쓰지 않는다.
   */
  binary: string | null
  /** Tab 자동완성 후보. */
  completions: readonly string[]
}

export const ENVIRONMENT_TERMINAL: Record<EnvironmentId, EnvironmentTerminalMeta> = {
  kubernetes: {
    headerLabel: 'SHELL / KUBECTL',
    binary: 'kubectl',
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
    // BE-16~18 이 아직 없어 명령 정책이 정해지지 않았다. 정해지면 여기를 채운다.
    binary: null,
    completions: ['clear'],
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
