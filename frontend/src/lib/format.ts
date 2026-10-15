import type { Risk, Role, Severity, Verdict } from './types'

export const severityLabel: Record<Severity, string> = { info: '정보', warning: '경고', average: '보통', high: '높음', disaster: '심각' }
export const riskLabel: Record<Risk, string> = { low: '낮음', medium: '보통', high: '높음' }
export const verdictLabel: Record<Verdict, string> = { confirmed: '확인됨', refuted: '반증됨', unknown: '판단 불가' }

export function openedAgo(minutes: number): string {
  if (minutes < 60) return `${minutes}분 전 열림`
  if (minutes < 1440) return `${Math.round(minutes / 60)}시간 전 열림`
  return `${Math.round(minutes / 1440)}일 전 열림`
}

export function shortAgo(minutes: number): string {
  if (minutes < 60) return `${minutes}분째`
  if (minutes < 1440) return `${Math.round(minutes / 60)}시간째`
  return `${Math.round(minutes / 1440)}일째`
}

// KST(UTC+9) 문자열을 UTC로 바꿔 보여 준다. 형식: 'YYYY-MM-DD HH:mm'
export function toUtc(kst: string): string {
  const [date, time] = kst.split(' ')
  const [h, m] = time.split(':').map(Number)
  const [y, mo, d] = date.split('-').map(Number)
  const t = new Date(Date.UTC(y, mo - 1, d, h - 9, m))
  const p = (n: number) => String(n).padStart(2, '0')
  return `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())} ${p(t.getUTCHours())}:${p(t.getUTCMinutes())}`
}

export const roleLabel: Record<Role, string> = { admin: '관리자', operator: '운영자', viewer: '조회자' }

export const won = (n: number): string => `${n.toLocaleString('ko-KR')}원`
