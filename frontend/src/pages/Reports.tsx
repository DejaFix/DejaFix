import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'

export default function Reports() {
  const { data } = useQuery({ queryKey: ['reports'], queryFn: api.reports })
  const [selected, setSelected] = useState<string | null>(null)
  const current = data?.find((r) => r.id === (selected ?? data[0]?.id))
  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">리포트</h1>
        <p className="page-sub">장애별 보고서 초안입니다. 확인되지 않은 항목은 '확인할 수 없음'으로 따로 표시합니다.</p>
      </div>
      {!data ? (
        <div className="skeleton" />
      ) : (
        <div className="detail-grid" style={{ gridTemplateColumns: '300px minmax(0, 1fr)' }}>
          <section className="card">
            <div className="list">
              {data.map((r) => (
                <button
                  key={r.id}
                  className="list-row"
                  style={{ background: 'transparent', border: 0, textAlign: 'left', width: '100%' }}
                  onClick={() => setSelected(r.id)}
                >
                  <div style={{ flex: 1 }}>
                    <div className="list-title">{r.title}</div>
                    <div className="list-sub">{r.createdAt}</div>
                  </div>
                  <span className={`chip ${r.status === 'sent' ? 'green' : 'neutral'}`}>
                    {r.status === 'sent' ? '발송됨' : '초안'}
                  </span>
                </button>
              ))}
            </div>
          </section>
          {current && (
            <section className="card report-body">
              <div className="card-head">
                <h2 className="card-title">{current.title}</h2>
              </div>
              {current.sections.map((s) => (
                <div key={s.heading}>
                  <h3>{s.heading}</h3>
                  <p>{s.body}</p>
                </div>
              ))}
              <div style={{ marginTop: 20, display: 'flex', gap: 8 }}>
                <button className="btn primary" disabled>
                  메일 발송 (Backend 연결 후)
                </button>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
