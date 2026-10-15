import { Fragment, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { won } from '../lib/format'
import type { CostItem } from '../lib/types'
import { RiskBadge, UnknownValue } from '../components/Chips'
import { EvidenceTrace } from '../components/EvidenceTrace'
import { Icon } from '../components/Icon'

type Filter = 'all' | 'low' | 'unknown'
const isUnknown = (c: CostItem) => c.note.startsWith('확인할 수 없음')
const saving = (c: CostItem) => (c.recommendedMonthly === null ? 0 : c.currentMonthly - c.recommendedMonthly)
const pct = (v: number | null) => (v === null ? <UnknownValue /> : `${v}%`)

export default function Cost() {
  const { data } = useQuery({ queryKey: ['cost'], queryFn: api.costItems })
  const [filter, setFilter] = useState<Filter>('all')
  const [open, setOpen] = useState<string | null>(null)

  const shown = useMemo(() => {
    const list = (data ?? []).filter((c) => (filter === 'low' ? c.risk === 'low' : filter === 'unknown' ? isUnknown(c) : true))
    return [...list].sort((a, b) => saving(b) - saving(a))
  }, [data, filter])

  const total = (data ?? []).reduce((s, c) => s + saving(c), 0)
  const recs = (data ?? []).filter((c) => c.recommendedType !== null).length
  const unknown = (data ?? []).filter(isUnknown).length
  const top = [...(data ?? [])].filter((c) => saving(c) > 0).sort((a, b) => saving(b) - saving(a))
  const maxSaving = top[0] ? saving(top[0]) : 1

  return (
    <div className="page">
      <div className="page-head"><h1 className="page-title">비용 절감</h1><p className="page-sub">최근 30일 사용률로 인스턴스 크기를 줄여도 되는지 검토합니다. 권고만 보여 주고 변경은 하지 않습니다.</p></div>
      <div className="note warn" style={{ marginBottom: 16 }}><Icon name="cost" size={16} />금액은 목업 단가로 계산한 예상값입니다. AWS MCP를 연결하면 실제 단가와 사용률로 바뀝니다.</div>

      <div className="grid kpi">
        <div className="card kpi-card"><div className="kpi-label"><span className="dot" style={{ background: 'var(--risk-low)' }} />한 달 절감 예상</div><div className="kpi-value">{data ? total.toLocaleString('ko-KR') : '—'}<small>원</small></div><div className="kpi-hint">권고를 모두 적용했을 때</div></div>
        <div className="card kpi-card"><div className="kpi-label"><span className="dot" style={{ background: 'var(--sev-info)' }} />절감 권고</div><div className="kpi-value">{recs}<small>건</small></div><div className="kpi-hint">크기를 줄여도 되는 인스턴스</div></div>
        <div className="card kpi-card"><div className="kpi-label"><span className="dot" style={{ background: 'var(--text-3)' }} />분석 대상</div><div className="kpi-value">{data?.length ?? '—'}<small>대</small></div><div className="kpi-hint">AWS 인스턴스</div></div>
        <div className="card kpi-card"><div className="kpi-label"><span className="dot" style={{ background: 'var(--sev-warning)' }} />확인할 수 없음</div><div className="kpi-value">{unknown}<small>대</small></div><div className="kpi-hint">필요한 지표가 수집되지 않음</div></div>
      </div>

      <div className="grid two">
        <section className="card">
          <div className="card-head"><h2 className="card-title">절감 예상 상위</h2><span className="card-sub">월 기준</span></div>
          {top.map((c) => (
            <div className="bar-row" key={c.id} style={{ gridTemplateColumns: '110px 1fr 96px' }}>
              <span className="mono">{c.host}</span>
              <div className="bar-track"><div className="bar-fill" style={{ width: `${(saving(c) / maxSaving) * 100}%`, background: 'var(--risk-low)' }} /></div>
              <span style={{ textAlign: 'right' }}>{won(saving(c))}</span>
            </div>
          ))}
          {top.length === 0 && <p className="card-sub">절감 권고가 없습니다.</p>}
        </section>
        <section className="card">
          <div className="card-head"><h2 className="card-title">읽는 방법</h2></div>
          <ul className="bullets">
            <li>평균과 최대(p95) 사용률이 모두 낮을 때만 줄이도록 권고합니다.</li>
            <li>위험 등급은 줄인 뒤 사용률이 80%를 넘을 가능성으로 정합니다.</li>
            <li>GPU, 메모리가 높은 서버는 CPU가 낮아도 권고하지 않습니다.</li>
            <li>지표가 없으면 추정하지 않고 '확인할 수 없음'으로 표시합니다.</li>
          </ul>
        </section>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="toolbar">
          <h2 className="card-title">인스턴스별 권고</h2>
          <div className="seg spacer" role="group" aria-label="필터">
            {([['all', '전체'], ['low', '위험 낮음'], ['unknown', '확인할 수 없음']] as const).map(([k, l]) => <button key={k} className={filter === k ? 'on' : ''} onClick={() => setFilter(k)}>{l}</button>)}
          </div>
        </div>
        {!data ? <div className="skeleton" /> : (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>인스턴스</th><th>현재 유형</th><th className="num">평균 CPU</th><th className="num">최대 CPU</th><th className="num">평균 메모리</th><th>권고 유형</th><th className="num">월 비용</th><th className="num">월 절감</th><th>위험</th></tr></thead>
              <tbody>
                {shown.map((c) => (
                  <Fragment key={c.id}>
                    <tr style={{ cursor: 'pointer' }} onClick={() => setOpen(open === c.id ? null : c.id)} aria-expanded={open === c.id}>
                      <td><span className="mono">{c.host}</span></td>
                      <td className="mono">{c.currentType}</td>
                      <td className="num">{pct(c.avgCpu)}</td>
                      <td className="num">{pct(c.p95Cpu)}</td>
                      <td className="num">{pct(c.avgMemory)}</td>
                      <td>{c.recommendedType ? <span className="mono">{c.recommendedType}</span> : isUnknown(c) ? <UnknownValue /> : <span className="chip neutral">권고 없음</span>}</td>
                      <td className="num">{won(c.currentMonthly)}</td>
                      <td className="num">{saving(c) > 0 ? won(saving(c)) : '—'}</td>
                      <td>{c.risk ? <RiskBadge risk={c.risk} /> : <span className="card-sub">—</span>}</td>
                    </tr>
                    {open === c.id && (
                      <tr className="hl"><td colSpan={9}>
                        <p style={{ fontSize: 14 }}>{c.note}</p>
                        <EvidenceTrace calls={c.evidence} />
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="assistant-note">행을 누르면 근거를 볼 수 있습니다.</p>
      </section>
    </div>
  )
}
