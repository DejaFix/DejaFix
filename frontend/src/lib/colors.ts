// DOM에서는 var(--토큰)을 그대로 쓰고, 차트(ECharts)는 현재 테마의 실제 값을 읽어서 쓴다.
export const sevCss = {
  info: 'var(--sev-info)',
  warning: 'var(--sev-warning)',
  average: 'var(--sev-average)',
  high: 'var(--sev-high)',
  disaster: 'var(--sev-disaster)',
} as const

export function cssVar(name: string): string {
  try {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  } catch {
    return ''
  }
}
