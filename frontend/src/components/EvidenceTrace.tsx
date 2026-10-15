import { useState } from 'react'
import type { EvidenceCall } from '../lib/types'

// AI가 어떤 도구를 몇 번 호출해 답했는지 보여 주는 근거 접이식. 모든 검증 결과에 같이 쓴다.
export function EvidenceTrace({ calls }: { calls: EvidenceCall[] }) {
  const [open, setOpen] = useState(false)
  if (calls.length === 0) return null
  const total = calls.reduce((s, c) => s + c.ms, 0)
  return (
    <div className="evidence">
      <button className="evidence-head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className="dot" />
        근거 — 도구 {calls.length}회 · {total}ms
      </button>
      {open && (
        <div className="evidence-body">
          {calls.map((c, i) => (
            <div className="evidence-item" key={i}>
              <strong>{c.tool}</strong><span className="evidence-ms">{c.ms}ms</span>
              <code className="evidence-cmd">{c.command}</code>
              <div className="evidence-result">{c.result}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
