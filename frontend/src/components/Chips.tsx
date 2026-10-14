import { riskLabel, severityLabel, verdictLabel } from '../lib/format'
import type { Risk, Severity, Verdict } from '../lib/types'

export function SeverityChip({ severity }: { severity: Severity }) {
  return <span className={`chip ${severity}`}>{severityLabel[severity]}</span>
}

export function RiskBadge({ risk }: { risk: Risk }) {
  const cls = risk === 'high' ? 'riskhigh' : risk
  return <span className={`chip ${cls}`}>위험 {riskLabel[risk]}</span>
}

export function VerdictChip({ verdict }: { verdict: Verdict }) {
  const cls = verdict === 'confirmed' ? 'green' : verdict === 'unknown' ? 'amber' : 'neutral'
  return <span className={`chip ${cls}`}>{verdictLabel[verdict]}</span>
}

// 확인되지 않은 값은 추정하지 않고 이 컴포넌트로 표시한다.
export function UnknownValue({ label = '확인할 수 없음' }: { label?: string }) {
  return <span className="unknown">{label}</span>
}
