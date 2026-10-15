import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { openedAgo } from '../lib/format'
import { SeverityChip, VerdictChip } from '../components/Chips'
import { EvidenceTrace } from '../components/EvidenceTrace'
import { Icon } from '../components/Icon'
import { useAssistant } from '../state/assistant'

export default function IncidentDetail() {
  const { id = '' } = useParams()
  const { ask } = useAssistant()
  const { data, isLoading } = useQuery({ queryKey: ['incident', id], queryFn: () => api.incident(id) })

  if (isLoading)
    return (
      <div className="page">
        <div className="skeleton" />
      </div>
    )
  if (!data)
    return (
      <div className="page">
        <div className="empty">
          <h2>장애를 찾을 수 없습니다</h2>
          <Link className="btn" to="/">
            현황으로 돌아가기
          </Link>
        </div>
      </div>
    )

  const { alert } = data
  return (
    <div className="page">
      <div className="crumb">
        <Link to="/">현황 · 장애 대응</Link> / 장애 상세
      </div>
      <div className="page-head" style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <h1 className="page-title">{alert.name}</h1>
          <p className="page-sub">
            <span className="mono">{alert.host}</span> · {openedAgo(alert.minutesOpen)}
            {alert.repeat24h ? ` · 24시간 ${alert.repeat24h}회 반복` : ''}
          </p>
        </div>
        <SeverityChip severity={alert.severity} />
        <button className="btn dark" onClick={() => ask(`${alert.host}의 '${alert.name}' 장애 원인을 알려줘`)}>
          <Icon name="sparkle" size={16} />
          AI에게 묻기
        </button>
      </div>

      <div className="detail-grid">
        <div>
          <section className="card">
            <div className="card-head">
              <h2 className="card-title">AI 초동 분석</h2>
            </div>
            <p>{data.summary}</p>
          </section>
          <section className="card">
            <div className="card-head">
              <h2 className="card-title">원인 후보</h2>
              <span className="card-sub">후보마다 읽기 전용 검증을 실행하고 결과를 표시합니다</span>
            </div>
            {data.candidates.map((c, i) => (
              <div className={`cand v-${c.verdict}`} key={c.id}>
                <div className="cand-head">
                  <span className="cand-rank">{i + 1}</span>
                  <span className="cand-title">{c.title}</span>
                  <span style={{ marginLeft: 'auto' }}>
                    <VerdictChip verdict={c.verdict} />
                  </span>
                </div>
                <p className="cand-sum">{c.summary}</p>
                <p className="cand-reason">
                  {c.verdict === 'refuted'
                    ? '왜 아닌가: '
                    : c.verdict === 'unknown'
                      ? '확인할 수 없는 이유: '
                      : '근거: '}
                  {c.reason}
                </p>
                <EvidenceTrace calls={c.checks} />
              </div>
            ))}
          </section>
        </div>
        <div>
          <section className="card">
            <div className="card-head">
              <h2 className="card-title">영향</h2>
            </div>
            <ul className="bullets">
              {data.impact.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </section>
          <section className="card">
            <div className="card-head">
              <h2 className="card-title">타임라인</h2>
            </div>
            <ul className="timeline">
              {data.timeline.map((t) => (
                <li key={t.at + t.text}>
                  <time>{t.at}</time>
                  {t.text}
                </li>
              ))}
            </ul>
          </section>
          <section className="card">
            <div className="card-head">
              <h2 className="card-title">변경 계획</h2>
            </div>
            {data.planId ? (
              <Link className="btn primary" to={`/plans/${data.planId}`}>
                계획 보기
              </Link>
            ) : (
              <p className="card-sub">이 장애에는 아직 변경 계획이 없습니다. (생성 기능은 Backend 연결 후)</p>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
