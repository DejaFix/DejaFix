import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { PlanStatus } from '../lib/types'
import { RiskBadge } from '../components/Chips'
import { Icon } from '../components/Icon'
import { statusText } from './Plans'

export default function PlanDetail() {
  const { id = '' } = useParams()
  const { data, isLoading } = useQuery({ queryKey: ['plan', id], queryFn: () => api.plan(id) })
  const [override, setOverride] = useState<PlanStatus | null>(null)

  if (isLoading) return <div className="page"><div className="skeleton" /></div>
  if (!data) return <div className="page"><div className="empty"><h2>계획을 찾을 수 없습니다</h2><Link className="btn" to="/plans">목록으로</Link></div></div>

  const status = override ?? data.status
  return (
    <div className="page">
      <div className="crumb"><Link to="/plans">변경 계획</Link> / 상세</div>
      <div className="page-head" style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}><h1 className="page-title">{data.title}</h1><p className="page-sub">{data.createdAt} · 연결된 장애 <Link to={`/incidents/${data.incidentId}`} style={{ color: 'var(--primary)' }}>보기</Link></p></div>
        <RiskBadge risk={data.risk} />
        <span className={`chip ${status === 'reviewed' ? 'green' : 'neutral'}`}>{statusText[status]}</span>
      </div>
      <div className="note warn" style={{ marginBottom: 16 }}><Icon name="admin" size={16} />이 계획은 실행되지 않습니다. 아래 명령은 미리보기이며, 실행은 담당자가 직접 합니다.</div>

      <div className="detail-grid">
        <section className="card">
          <div className="card-head"><h2 className="card-title">실행 단계(미리보기)</h2></div>
          {data.steps.map((s, i) => (
            <div className="step" key={s.command}>
              <div className="step-no">단계 {i + 1}</div>
              <code className="cmd">{s.command}</code>
              <p style={{ marginTop: 8, fontSize: 14 }}>{s.purpose}</p>
              <div className="rollback">되돌리기: {s.rollback}</div>
            </div>
          ))}
        </section>
        <div>
          <section className="card">
            <div className="card-head"><h2 className="card-title">예상 영향</h2></div>
            <ul className="bullets">{data.impact.map((t) => <li key={t}>{t}</li>)}</ul>
            <p className="card-sub" style={{ marginTop: 12 }}>예측이며 보증이 아닙니다. 의사결정 보조용입니다.</p>
          </section>
          <section className="card">
            <div className="card-head"><h2 className="card-title">검토</h2></div>
            <p className="card-sub" style={{ marginBottom: 12 }}>{data.risk === 'high' ? '위험 등급이 높음이라 승인자 2명이 필요합니다.' : '승인자 1명이 검토합니다.'}</p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn primary" disabled={status !== 'draft'} onClick={() => setOverride('reviewed')}>검토 완료로 표시</button>
              <button className="btn" disabled={status === 'discarded'} onClick={() => setOverride('discarded')}>폐기</button>
            </div>
            <p className="assistant-note">상태 변경은 이 화면에서만 반영되는 목업입니다.</p>
          </section>
        </div>
      </div>
    </div>
  )
}
