import { Link } from 'react-router-dom'
import type { AnalysisReport, KnowledgeHit } from '../lib/types'
import { Unknown } from './IncidentParts'

// 저장된 값을 옮겨 표시만 한다. 문장 생성·번역·재정렬 없음(NFR-MAINT-010).
const SIMILAR_FACT_LABEL = '과거 유사 사례'
const MAX_HITS = 3
const sourceKo: Record<KnowledgeHit['source_type'], string> = {
  incident_report: '장애 리포트',
  runbook: '런북',
  pack_action: '팩 동작',
  resolution_note: '해결 메모',
}

/** 비슷한 과거 장애 카드. 해당 fact도 hits도 없으면 그리지 않고, fact만 있고 hits가 비면 "관련 지식 없음". */
export function SimilarCasesCard({
  report,
  hits,
  onPick,
}: {
  report: AnalysisReport
  hits?: KnowledgeHit[]
  onPick: (evidenceId: string) => void
}) {
  const fact = report.facts.find((f) => f.label === SIMILAR_FACT_LABEL)
  const list = (hits ?? []).slice(0, MAX_HITS)
  if (!fact && list.length === 0) return null
  const evId = fact?.evidence_ids[0]
  return (
    <section className="card">
      <div className="card-head">
        <h2 className="card-title">비슷한 과거 장애</h2>
      </div>
      {list.length === 0 ? (
        <Unknown reason="NO_DATA" at={fact?.collected_at} />
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 12 }}>
          {list.map((h) => (
            <li key={h.chunk_id}>
              <div>
                <strong>{h.title}</strong>
              </div>
              <div className="card-sub">
                {sourceKo[h.source_type]}
                {h.host_name && ` · ${h.host_name}`}
                {h.source_type === 'incident_report' && h.incident_id !== null && (
                  <>
                    {' · '}
                    <Link to={`/incidents/${h.incident_id}`}>장애 #{h.incident_id}</Link>
                  </>
                )}
              </div>
              <p
                style={{
                  margin: '4px 0',
                  whiteSpace: 'pre-line',
                  display: '-webkit-box',
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {h.excerpt}
              </p>
              {evId ? (
                <button
                  type="button"
                  className="chip neutral mono"
                  title="근거 패널에서 원문 열기"
                  onClick={() => onPick(evId)}
                >
                  {h.chunk_id}
                </button>
              ) : (
                <span className="chip neutral mono">{h.chunk_id}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
