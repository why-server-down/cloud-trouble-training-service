import { ENVIRONMENT_IDS, EnvironmentId } from '../types/training'

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

/** 탭 노출 순서. 백엔드 SUPPORTED_ENVIRONMENTS 순서를 그대로 따른다. */
export const ENVIRONMENT_ORDER: readonly EnvironmentId[] = ENVIRONMENT_IDS

export const getEnvironmentMeta = (environment: EnvironmentId): EnvironmentDisplayMeta =>
  ENVIRONMENT_META[environment]
