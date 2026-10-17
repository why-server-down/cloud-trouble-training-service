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

/* 모바일 하단 탭 바 아이콘 (FE-26). 글자 라벨과 함께 쓰는 20px 선 아이콘. */
const tabIconProps = { ...iconProps, width: 20, height: 20, viewBox: '0 0 20 20', className: 'tab-icon' }

export const ListIcon: React.FC = () => (
  <svg {...tabIconProps}>
    <path d="M7 5.5h9M7 10h9M7 14.5h9" />
    <path d="M3.75 5.5h.01M3.75 10h.01M3.75 14.5h.01" strokeWidth="2" />
  </svg>
)

export const TerminalIcon: React.FC = () => (
  <svg {...tabIconProps}>
    <rect x="2.5" y="3.5" width="15" height="13" rx="2.5" />
    <path d="m6 8 2.5 2L6 12M10.5 12.5H14" />
  </svg>
)

export const ChatIcon: React.FC = () => (
  <svg {...tabIconProps}>
    <path d="M4.5 4h11A1.5 1.5 0 0 1 17 5.5v7a1.5 1.5 0 0 1-1.5 1.5H9l-3.5 2.5V14h-1A1.5 1.5 0 0 1 3 12.5v-7A1.5 1.5 0 0 1 4.5 4Z" />
  </svg>
)

export const ChartIcon: React.FC = () => (
  <svg {...tabIconProps}>
    <path d="M3.5 16.5h13" />
    <path d="M6 13V9.5M10 13V5.5M14 13v-5" />
  </svg>
)

export const GuideIcon: React.FC = () => (
  <svg {...tabIconProps}>
    <path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H15v12H5.5A1.5 1.5 0 0 0 4 16.5v-12Z" />
    <path d="M4 16.5A1.5 1.5 0 0 0 5.5 18H15v-3" />
    <path d="M7.5 7h4.5" />
  </svg>
)
