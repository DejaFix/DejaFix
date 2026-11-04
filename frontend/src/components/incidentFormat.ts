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

/** 본문 안의 UTC ISO8601 시각('2026-10-28T14:45:09Z')을 KST 'YYYY-MM-DD HH:mm'으로 바꾼다. 다른 글자는 그대로. */
export function kstInText(text: string): string {
  return text.replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z/g, (iso) => {
    const t = new Date(iso)
    if (Number.isNaN(t.getTime())) return iso
    const k = new Date(t.getTime() + 9 * 3600_000)
    return `${k.getUTCFullYear()}-${pad(k.getUTCMonth() + 1)}-${pad(k.getUTCDate())} ${pad(k.getUTCHours())}:${pad(k.getUTCMinutes())}`
  })
}

/**
 * RAG 청크 원문(excerpt)을 카드 본문으로 읽기 좋게 다듬는다. 표시 정리만 하고 문장은 만들거나 바꾸지 않는다.
 * - 마크다운 기호 제거: 제목 '#', 목록 '- '·'* ', 인용 '>', 굵게 '**', 코드 '`'
 * - 제목(title)이 그대로 들어 있는 줄은 카드 제목과 겹치므로 뺀다
 * - UTC 시각은 KST로 바꾼다
 */
export function readableExcerpt(excerpt: string, title: string): string {
  const plain = (s: string) => s.replace(/[*_`]/g, '').replace(/\s+/g, ' ').trim()
  const key = plain(title)
  const lines = kstInText(excerpt)
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*(?:#{1,6}\s+|>\s?|[-*+]\s+)/, ''))
    .map((line) => line.replace(/\*\*|__|`/g, '').trim())
    .filter((line) => line && !(key.length >= 4 && plain(line).includes(key)))
  return lines.join('\n')
}
