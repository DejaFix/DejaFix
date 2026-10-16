import type {
  AnalysisStatus,
  Confidence,
  Evidence,
  MailLog,
  PlanStep,
  SeverityInfo,
  Tier,
  UnknownReason,
} from '../lib/types'
import { UnknownValue } from './Chips'
import { kstShort } from './incidentFormat'

// 장애 상세(#11) 전용 표시 조각. 값만 보여 주고 원인·티어·문장은 만들거나 바꾸지 않는다(NFR-MAINT-010).

/** "확인할 수 없음 · 사유 · 수집 시각 HH:mm" — null을 0·빈칸으로 그리지 않는다(SAFE-10). */
export function Unknown({ reason, at }: { reason?: UnknownReason | null; at?: string | null }) {
  const time = kstShort(at)
  const label = ['확인할 수 없음', reason, time ? `수집 시각 ${time}` : null].filter(Boolean).join(' · ')
  return <UnknownValue label={label} />
}

const severityClass = ['info', 'info', 'warning', 'average', 'high', 'disaster']
const severityKo = ['미분류', '정보', '경고', '보통', '높음', '심각']

export function SeverityInfoChip({ severity }: { severity: SeverityInfo }) {
  return <span className={`chip ${severityClass[severity.level]}`}>{severityKo[severity.level]}</span>
}

const analysisText: Record<AnalysisStatus, { label: string; cls: string }> = {
  done: { label: '분석 완료', cls: 'green' },
  fallback: { label: '규칙 기반 리포트', cls: 'amber' },
  pending: { label: '분석 대기', cls: 'neutral' },
  running: { label: '분석 중', cls: 'neutral' },
  skipped: { label: '분석 건너뜀', cls: 'neutral' },
  failed: { label: '분석 실패', cls: 'riskhigh' },
}

export function AnalysisBadge({ status }: { status: AnalysisStatus }) {
  const a = analysisText[status]
  return <span className={`chip ${a.cls}`}>{a.label}</span>
}

const confidenceText: Record<Confidence, { label: string; cls: string }> = {
  low: { label: '확신도 낮음', cls: 'neutral' },
  medium: { label: '확신도 보통', cls: 'amber' },
  high: { label: '확신도 높음', cls: 'green' },
}

export function ConfidenceChip({ confidence }: { confidence: Confidence }) {
  const c = confidenceText[confidence]
  return <span className={`chip ${c.cls}`}>{c.label}</span>
}

const tierText: Record<Tier, { label: string; cls: string }> = {
  A: { label: 'A · 조회 · 안전', cls: 'green' },
  B: { label: 'B · 변경 · 승인 필요(미구현)', cls: 'amber' },
  C: { label: 'C · 금지 · 사람이 판단', cls: 'riskhigh' },
}

export function TierBadge({ tier }: { tier: Tier }) {
  const t = tierText[tier]
  return <span className={`chip ${t.cls}`}>{t.label}</span>
}

/** 근거 ID 칩. 누르면 아래 근거 패널의 해당 항목이 열린다. 기록에 없는 ID는 누를 수 없다. */
export function EvidenceIds({
  ids,
  known,
  onPick,
}: {
  ids: string[]
  known: Set<string>
  onPick: (id: string) => void
}) {
  if (ids.length === 0) return null
  return (
    <div className="chips" style={{ marginTop: 6 }}>
      <span className="card-sub">근거</span>
      {ids.map((id) =>
        known.has(id) ? (
          <button key={id} type="button" className="chip neutral mono" onClick={() => onPick(id)}>
            {id}
          </button>
        ) : (
          <span key={id} className="chip neutral mono" title="근거 기록 없음">
            {id}
          </span>
        ),
      )}
    </div>
  )
}

/** 이 리포트가 참조한 도구 호출 기록(SAFE-12). 근거 ID를 누르면 해당 항목이 열린다. */
export function EvidencePanel({
  evidence,
  openId,
  onToggle,
}: {
  evidence: Evidence[]
  openId: string | null
  onToggle: (id: string) => void
}) {
  if (evidence.length === 0) return <p className="card-sub">기록된 근거가 없습니다.</p>
  return (
    <div className="evidence">
      <div className="evidence-head" style={{ cursor: 'default' }}>
        <span className="dot" />
        근거 — 도구 {evidence.length}회
      </div>
      <div className="evidence-body">
        {evidence.map((e) => {
          const open = openId === e.id
          return (
            <div className="evidence-item" key={e.id} id={`ev-${e.id}`}>
              <button type="button" className="evidence-head" aria-expanded={open} onClick={() => onToggle(e.id)}>
                <strong>{e.tool}</strong> <span className="mono">{e.id}</span>
                {e.ok ? '' : ' · 실패'}
                {e.duration_ms !== null && <span className="evidence-ms"> {e.duration_ms}ms</span>}
              </button>
              {open && (
                <div>
                  <code className="evidence-cmd">{JSON.stringify(e.args)}</code>
                  <div className="evidence-result">{e.result_summary ?? <Unknown reason="NO_DATA" />}</div>
                  <div className="card-sub">
                    호출 {kstShort(e.called_at) ?? '—'}
                    {e.data_clock && ` · 데이터 시각 ${kstShort(e.data_clock) ?? e.data_clock}`}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** 계획 단계. 보여 주기만 한다 — 실행 버튼·토글은 없다(SAFE-04). */
export function PlanStepCard({
  step,
  onPick,
  known,
}: {
  step: PlanStep
  known: Set<string>
  onPick: (id: string) => void
}) {
  const rows: [string, string | null][] = [
    ['대상', step.target],
    ['사전 확인', step.precheck],
    ['예상 효과', step.expected_effect],
    ['위험', step.risk],
    ['롤백', step.rollback],
    ['판정 근거', step.rationale],
  ]
  return (
    <div className="cand">
      <div className="cand-head">
        <span className="cand-rank">{step.seq}</span>
        <span className="cand-title">{step.title}</span>
        <span style={{ marginLeft: 'auto' }}>
          <TierBadge tier={step.tier} />
        </span>
      </div>
      {step.command_preview && <code className="evidence-cmd">{step.command_preview}</code>}
      {rows.map(
        ([k, v]) =>
          v && (
            <p className="cand-reason" key={k}>
              {k}: {v}
            </p>
          ),
      )}
      <EvidenceIds ids={step.evidence_ids} known={known} onPick={onPick} />
    </div>
  )
}

const mailStatus: Record<MailLog['status'], { label: string; cls: string }> = {
  sent: { label: '발송됨', cls: 'green' },
  failed: { label: '실패', cls: 'riskhigh' },
  skipped: { label: '건너뜀', cls: 'neutral' },
}

export function MailLogRow({ log }: { log: MailLog }) {
  const s = mailStatus[log.status]
  return (
    <li>
      <span className="mono">{log.recipient}</span> <span className={`chip ${s.cls}`}>{s.label}</span>{' '}
      <span className="card-sub">
        시도 {log.attempts}회 · {kstShort(log.sent_at ?? log.created_at) ?? '—'}
        {log.error && ` · ${log.error}`}
      </span>
    </li>
  )
}
