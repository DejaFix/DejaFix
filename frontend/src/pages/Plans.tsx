import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { RiskBadge } from '../components/Chips'
import { Icon } from '../components/Icon'

export const statusText = { draft: '작성됨', reviewed: '검토 완료', discarded: '폐기' } as const

export default function Plans() {
  const { data } = useQuery({ queryKey: ['plans'], queryFn: api.plans })
  return (
    <div className="page">
      <div className="page-head"><h1 className="page-title">변경 계획</h1><p className="page-sub">AI가 만든 대응 계획입니다. 이 시스템은 계획까지만 만들고 직접 실행하지 않습니다.</p></div>
      <div className="note" style={{ marginBottom: 16 }}><Icon name="admin" size={16} />운영 Zabbix에는 쓰지 않습니다. 계획의 승인은 '검토가 끝났다'는 뜻이며, 실제 실행은 담당자가 별도로 합니다.</div>
      <section className="card">
        {!data ? <div className="skeleton" /> : (
          <div className="list">
            {data.map((p) => (
              <Link className="list-row" key={p.id} to={`/plans/${p.id}`}>
                <div style={{ flex: 1, minWidth: 0 }}><div className="list-title">{p.title}</div><div className="list-sub">{p.createdAt} · 단계 {p.steps.length}개</div></div>
                <RiskBadge risk={p.risk} />
                <span className={`chip ${p.status === 'reviewed' ? 'green' : 'neutral'}`}>{statusText[p.status]}</span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
