import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { ResolutionNotes } from '../components/ResolutionNotes'
import {
  AnalysisBadge,
  ConfidenceChip,
  EvidenceIds,
  EvidencePanel,
  MailLogRow,
  PlanStepCard,
  SeverityInfoChip,
  Unknown,
} from '../components/IncidentParts'
import { SimilarCasesCard } from '../components/SimilarCasesCard'
import { analysisNotes, kstShort } from '../components/incidentFormat'
import { ApiError } from '../lib/http'
import { useIncidentDetail } from '../lib/queries'
import { useAssistant } from '../state/assistant'

export default function IncidentDetail({ embedded = false }: { embedded?: boolean }) {
  const { id = '' } = useParams()
  const { ask } = useAssistant()
  const { data: res, isLoading, isError, error } = useIncidentDetail(id)
  const [openEv, setOpenEv] = useState<string | null>(null)

  const data = res?.data
  const known = useMemo(() => new Set((data?.evidence ?? []).map((e) => e.id)), [data])

  if (embedded && !data) return null // 요약 화면이 불러오는 중·없음 상태를 먼저 처리한다
  if (isLoading)
    return (
      <div className="page">
        <div className="skeleton" />
      </div>
    )
  if (!data) {
    const notFound = error instanceof ApiError && error.status === 404
    return (
      <div className="page">
        <div className="empty">
          <h2>{isError && !notFound ? '장애 정보를 불러오지 못했습니다' : '장애를 찾을 수 없습니다'}</h2>
          <Link className="btn" to="/">
            현황으로 돌아가기
          </Link>
        </div>
      </div>
    )
  }

  const { incident, report, evidence, plan, steps, mail_logs } = data
  const status = incident.analysis.status
  const pick = (evId: string) => {
    setOpenEv(evId)
    document.getElementById(`ev-${evId}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }
  const toggle = (evId: string) => setOpenEv((cur) => (cur === evId ? null : evId))

  return (
    <div className={embedded ? 'embedded' : 'page'}>
      {embedded && (
        <div className="embedded-actions">
          <button
            className="btn dark"
            onClick={() => ask(`${incident.host.name ?? '이 서버'}의 '${incident.title}' 장애 원인을 알려줘`)}
          >
            <Icon name="sparkle" size={16} />
            AI에게 묻기
          </button>
        </div>
      )}
      {!embedded && (
      <>
      <div className="crumb">
        <Link to="/">현황 · 장애 대응</Link> / 장애 상세
      </div>
      <div className="page-head" style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <h1 className="page-title">{incident.title}</h1>
          <p className="page-sub">
            <span className="mono">{incident.host.name ?? <Unknown reason="NOT_COLLECTED" />}</span> · 시작{' '}
            {kstShort(incident.started_at) ?? '—'}
            {incident.status === 'resolved' && ` · 해결 ${kstShort(incident.resolved_at) ?? '—'}`}
          </p>
        </div>
        <AnalysisBadge status={status} />
        <SeverityInfoChip severity={incident.severity} />
        <button
          className="btn dark"
          onClick={() => ask(`${incident.host.name ?? '이 서버'}의 '${incident.title}' 장애 원인을 알려줘`)}
        >
          <Icon name="sparkle" size={16} />
          AI에게 묻기
        </button>
      </div>
      </>
      )}
      {isError && <p className="card-sub">갱신 실패 — 마지막으로 받은 내용을 표시 중입니다.</p>}

      {!report ? (
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">AI 초동 분석</h2>
          </div>
          <p className="card-sub">{analysisNotes[status] || '리포트가 아직 없습니다.'}</p>
        </section>
      ) : (
        <div className="detail-grid">
          <div>
            <section className="card">
              <div className="card-head">
                <h2 className="card-title">AI 초동 분석</h2>
                {report.kind === 'fallback' && (
                  <span className="chip amber">LLM 미연결/실패 — 규칙 기반 최소 리포트</span>
                )}
              </div>
              <p>{report.summary}</p>
            </section>
            <section className="card">
              <div className="card-head">
                <h2 className="card-title">원인 후보</h2>
              </div>
              {report.causes.length === 0 && <p className="card-sub">원인 후보가 없습니다.</p>}
              {report.causes.map((c) => (
                <div className="cand" key={c.rank}>
                  <div className="cand-head">
                    <span className="cand-rank">{c.rank}</span>
                    <span className="cand-title">{c.title}</span>
                    <span style={{ marginLeft: 'auto' }}>
                      <ConfidenceChip confidence={c.confidence} />
                    </span>
                  </div>
                  <p className="cand-reason">{c.reasoning}</p>
                  <p className="cand-reason">사람이 확인할 방법: {c.verify}</p>
                  <EvidenceIds ids={c.evidence_ids} known={known} onPick={pick} />
                </div>
              ))}
            </section>
            {report.facts.length > 0 && (
              <section className="card">
                <div className="card-head">
                  <h2 className="card-title">수치</h2>
                </div>
                <ul className="bullets">
                  {report.facts.map((f) => (
                    <li key={f.label}>
                      {f.label}:{' '}
                      {f.value === null ? (
                        <Unknown reason={f.unknown_reason} at={f.collected_at} />
                      ) : (
                        `${f.value}${f.unit ?? ''}`
                      )}
                      <EvidenceIds ids={f.evidence_ids} known={known} onPick={pick} />
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {report.unknowns.length > 0 && (
              <section className="card">
                <div className="card-head">
                  <h2 className="card-title">확인할 수 없음</h2>
                </div>
                <ul className="bullets">
                  {report.unknowns.map((u) => (
                    <li key={u.label}>
                      {u.label} · <Unknown reason={u.reason} />
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
          <div>
            <section className="card">
              <div className="card-head">
                <h2 className="card-title">영향</h2>
              </div>
              <ul className="bullets">
                {report.impact.hosts.length > 0 && <li>호스트: {report.impact.hosts.join(', ')}</li>}
                {report.impact.services.length > 0 && <li>서비스: {report.impact.services.join(', ')}</li>}
                <li>사용자 영향: {report.impact.user_impact ?? <Unknown reason="NO_DATA" />}</li>
              </ul>
              <EvidenceIds ids={report.impact.evidence_ids} known={known} onPick={pick} />
            </section>
            {report.next_checks.length > 0 && (
              <section className="card">
                <div className="card-head">
                  <h2 className="card-title">사람이 확인할 것</h2>
                </div>
                <ul className="bullets">
                  {report.next_checks.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>
      )}

      {report && <SimilarCasesCard report={report} hits={data.knowledge_hits} onPick={pick} />}

      {report && (
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">근거 (EvidenceTrace)</h2>
          </div>
          <EvidencePanel evidence={evidence} openId={openEv} onToggle={toggle} />
        </section>
      )}

      {plan && (
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">변경 계획 미리보기</h2>
            <span className="chip neutral">최고 티어 {plan.max_tier}</span>
          </div>
          <p className="card-sub">
            미리보기 전용입니다. 이 화면에서는 아무것도 실행하지 않으며, 티어는 규칙이 정합니다.
          </p>
          <p>{plan.title}</p>
          {plan.goal && <p className="card-sub">목표: {plan.goal}</p>}
          {plan.assumptions.length > 0 && (
            <ul className="bullets">
              {plan.assumptions.map((a) => (
                <li key={a}>가정: {a}</li>
              ))}
            </ul>
          )}
          {steps.map((s) => (
            <PlanStepCard key={s.seq} step={s} known={known} onPick={pick} />
          ))}
        </section>
      )}

      {incident.status === 'resolved' && <ResolutionNotes incidentId={incident.id} />}

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">메일 발송 기록</h2>
        </div>
        {mail_logs.length === 0 ? (
          <p className="card-sub">발송 기록이 없습니다.</p>
        ) : (
          <ul className="bullets">
            {mail_logs.map((m) => (
              <MailLogRow key={m.id} log={m} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
