import { shortAgo } from '../lib/format'
import { useIncidentDetail } from '../lib/queries'
import type { Incident, Tier } from '../lib/types'
import { ConfidenceChip, SeverityInfoChip, Unknown } from './IncidentParts'
import { analysisNotes, kstShort } from './incidentFormat'

// 현황의 '지금 확인할 장애' 카드: 고른 장애 하나를 ① 무엇이 · ② 왜 · ③ 어떻게 세 칸과 처리 흐름으로 보여 주고,
// 이 카드 아래에 장애 상세 내용이 이어진다. 값은 상세(#11) 응답에 있는 것만 쓰고, 없으면 지어내지 않는다(SAFE-08·10).
// 시계열(그래프용) 데이터는 이 응답에 없어 그래프는 그리지 않는다.

const tierClass: Record<Tier, string> = { A: 'ok', B: 'warn', C: 'bad' }
const DAY_MS = 24 * 3600_000

export function FocusCard({ incident, nowMs }: { incident: Incident; nowMs: number }) {
  const detail = useIncidentDetail(incident.id)
  const data = detail.data?.data
  const report = data?.report ?? null
  const plan = data?.plan ?? null
  const steps = data?.steps ?? []
  const mailLogs = data?.mail_logs ?? []

  const numeric = report?.facts.filter((f) => f.value !== null) ?? []
  const lead = numeric[0]
  const restFacts = numeric.slice(1, 4)
  const cause = report?.causes[0]
  const sentAt = mailLogs.find((m) => m.status === 'sent')?.sent_at ?? null
  const mins = Math.max(0, Math.round((nowMs - new Date(incident.started_at).getTime()) / 60_000))
  const isNew = nowMs - new Date(incident.started_at).getTime() < DAY_MS && incident.status === 'problem'
  const timeline: { label: string; at: string | null | undefined; state: 'done' | 'wait' | 'todo' }[] = [
    { label: 'Zabbix 장애', at: incident.started_at, state: 'done' },
    { label: 'AI 분석', at: report?.created_at, state: report ? 'done' : 'todo' },
    { label: '메일 발송', at: sentAt, state: sentAt ? 'done' : 'todo' },
    { label: '사람 확인', at: null, state: plan ? 'wait' : 'todo' },
  ]

  return (
    <section className="card focus-card" aria-label="선택한 장애 요약">
      <div className="focus-head">
        <SeverityInfoChip severity={incident.severity} />
        {isNew && <span className="chip info">새 장애</span>}
        {incident.status === 'resolved' && <span className="chip green">해결됨</span>}
        <h3 className="focus-title">{incident.title}</h3>
        <span className="focus-when">
          {kstShort(incident.started_at) ?? '—'} 발생 · {shortAgo(mins)}
        </span>
      </div>
      <div className="focus-host mono">{incident.host.name ?? <Unknown reason="NOT_COLLECTED" />}</div>

      <div className="dsum-cols">
        <div className="dsum-col">
          <div className="dsum-step">① 무엇이 · 현상</div>
          {detail.isPending ? (
            <div className="skeleton-line dark" />
          ) : lead ? (
            <>
              <div className="dsum-big">
                {String(lead.value)}
                {lead.unit && <small>{lead.unit}</small>}
              </div>
              <div className="dsum-cap">{lead.label}</div>
              {restFacts.length > 0 && (
                <ul className="dsum-facts">
                  {restFacts.map((f) => (
                    <li key={f.label}>
                      <span>{f.label}</span>
                      <b>
                        {String(f.value)}
                        {f.unit ?? ''}
                      </b>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <div className="dsum-text">
              {incident.title}
              <div className="dsum-cap" style={{ marginTop: 6 }}>
                <Unknown reason="NO_DATA" />
              </div>
            </div>
          )}
        </div>

        <div className="dsum-col">
          <div className="dsum-step">② 왜 · AI 분석</div>
          {detail.isPending ? (
            <div className="skeleton-line dark" />
          ) : cause ? (
            <>
              <div className="dsum-cap">원인 후보 1위</div>
              <div className="dsum-cause">{cause.title}</div>
              <div className="dsum-row">
                <ConfidenceChip confidence={cause.confidence} />
              </div>
              <p className="dsum-note">{cause.reasoning}</p>
            </>
          ) : report ? (
            <p className="dsum-note">{report.summary}</p>
          ) : (
            <p className="dsum-note">{analysisNotes[incident.analysis.status] || '리포트가 아직 없습니다.'}</p>
          )}
          {report?.kind === 'fallback' && <span className="chip amber">규칙 기반 리포트</span>}
        </div>

        <div className="dsum-col">
          <div className="dsum-step">③ 어떻게 · 변경 계획 (미리보기)</div>
          {detail.isPending ? (
            <div className="skeleton-line dark" />
          ) : steps.length > 0 ? (
            <ol className="dsum-steps">
              {steps.slice(0, 4).map((s) => (
                <li key={s.seq}>
                  <span className={`tier-dot ${tierClass[s.tier]}`}>{s.tier}</span>
                  <span>{s.title}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="dsum-note">변경 계획이 아직 없습니다.</p>
          )}
          {steps.length > 4 && <p className="dsum-cap">외 {steps.length - 4}단계</p>}
          <p className="dsum-cap">A 조회만 · B 승인 필요 · C 금지 — 실행은 사람이</p>
        </div>
      </div>

      <ol className="dsum-time" aria-label="처리 흐름">
        {timeline.map((t) => (
          <li key={t.label} className={t.state}>
            <i />
            <b>{t.label}</b>
            <span>{t.state === 'wait' ? '대기' : (kstShort(t.at) ?? '—')}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
