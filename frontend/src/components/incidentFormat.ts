import type { AnalysisStatus } from '../lib/types'

const pad = (n: number) => String(n).padStart(2, '0')

/** UTC ISO8601 → 'MM-DD HH:mm' (KST). 값이 없으면 null. */
export function kstShort(iso: string | null | undefined): string | null {
  if (!iso) return null
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return null
  const k = new Date(t.getTime() + 9 * 3600_000)
  return `${pad(k.getUTCMonth() + 1)}-${pad(k.getUTCDate())} ${pad(k.getUTCHours())}:${pad(k.getUTCMinutes())}`
}

/** 리포트가 없을 때 분석 상태별 안내 문구 */
export const analysisNotes: Record<AnalysisStatus, string> = {
  done: '',
  fallback: '',
  pending: '아직 분석이 시작되지 않았습니다. 잠시 후 자동으로 갱신됩니다.',
  running: 'AI가 분석 중입니다. 완료되면 자동으로 갱신됩니다.',
  skipped: '분석 기준 미만의 장애라 분석하지 않았습니다.',
  failed: '분석에 실패했습니다. 리포트를 만들지 못했습니다.',
}

/**
 * 목록용 장애 제목. Zabbix 트리거 이름을 사람이 읽기 쉽게 줄인다(원문은 title 속성·상세 화면에 그대로).
 * - 앞의 템플릿 접두사 제거: 'Windows: …' → '…'
 * - '"서비스ID" (표시 이름 (서비스ID))'·'"서비스ID" (표시 이름)' → '표시 이름'
 * 문장을 새로 만들거나 번역하지 않고 중복만 덜어 낸다.
 */
export function readableTitle(title: string): string {
  const out = title
    .replace(/^[A-Za-z][\w .-]{0,40}:\s+/, '')
    .replace(/"([^"]+)"\s*\(([^()]*?)(?:\s*\(\1\))?\)/g, (_, id: string, name: string) => name.trim() || id)
    .trim()
  return out || title
}
