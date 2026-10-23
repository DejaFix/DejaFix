import type { ReactElement } from 'react'

const paths = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  cost: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5c0-1 1.2-1.6 2.5-1.6s2.5.6 2.5 1.7c0 2.2-5 1.200-5 3.600 0 1.100 1.200 1.700 2.500 1.700s2.500-.6 2.500-1.500M12 6.500v1.400M12 16v1.500" />
    </>
  ),
  compare: <path d="M7 20V10M12 20V4M17 20v-7" />,
  report: (
    <>
      <path d="M7 3h7l4 4v14H7z" />
      <path d="M14 3v4h4M9.500 12h5M9.500 16h5" />
    </>
  ),
  plan: (
    <>
      <rect x="5" y="5" width="14" height="16" rx="2" />
      <path d="M9 3h6v4H9zM9 13l2 2 4-4" />
    </>
  ),
  bell: <path d="M6 16v-5a6 6 0 0112 0v5l1.500 2h-15zM10 20a2 2 0 004 0" />,
  admin: <path d="M12 3l8 3v6c0 4.500-3.400 8-8 9-4.600-1-8-4.500-8-9V6z" />,
  agent: (
    <>
      <circle cx="12" cy="12" r="2.500" />
      <circle cx="5" cy="6" r="1.800" />
      <circle cx="19" cy="6" r="1.800" />
      <circle cx="12" cy="20" r="1.800" />
      <path d="M6.500 7.200l3.500 3.300M17.500 7.200l-3.500 3.300M12 14.500v3.700" />
    </>
  ),
  sparkle: (
    <path d="M12 3l1.800 5.200L19 10l-5.200 1.800L12 17l-1.800-5.200L5 10l5.200-1.800zM19 16l.8 2.200L22 19l-2.200.8L19 22l-.8-2.200L16 19l2.200-.8z" />
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.500" />
      <path d="M16 16l4.500 4.500" />
    </>
  ),
  send: <path d="M12 19V5M6 11l6-6 6 6" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  chevron: <path d="M9 6l6 6-6 6" />,
  logo: <path d="M5 16l4-9 3 6 2-4 5 7" />,
} satisfies Record<string, ReactElement>

export type IconName = keyof typeof paths

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  )
}
