import React from 'react'

/*
 * 미션 패널에서 쓰는 작은 선 아이콘. 이모지는 플랫폼마다 모양과 크기가 달라 쓰지 않는다.
 * 모두 장식이므로 aria-hidden 이다 — 뜻은 항상 옆의 글자가 말한다.
 */
const iconProps = {
  width: 14,
  height: 14,
  viewBox: '0 0 16 16',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  focusable: false,
}

export const LockIcon: React.FC = () => (
  <svg {...iconProps} className="mission-icon">
    <rect x="3" y="7" width="10" height="7" rx="1.5" />
    <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
  </svg>
)

export const AlertIcon: React.FC = () => (
  <svg {...iconProps} className="mission-icon">
    <path d="M8 2.5 14 13H2L8 2.5Z" />
    <path d="M8 6.5v3" />
    <path d="M8 11.5h.01" />
  </svg>
)

export const CheckIcon: React.FC = () => (
  <svg {...iconProps} className="mission-icon">
    <path d="m3.5 8.5 3 3 6-7" />
  </svg>
)
