import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { chartGrid, chartText, sevColor } from '../lib/colors'
import { openedAgo, severityLabel, shortAgo } from '../lib/format'
import type { AlertItem, Severity } from '../lib/types'
import { Collapsible } from '../components/Collapsible'
import { SeverityChip, UnknownValue } from '../components/Chips'
import { EChart } from '../components/EChart'
import { Icon } from '../components/Icon'
import { useAssistant } from '../state/assistant'

function Kpi({ label, value, unit, hint, color, href }: { label: string; value: number | null; unit: string; hint: string; color: string; href: string }) {
  return (
    <a className="card kpi-card" href={href}>
      <div className="kpi-label"><span className="dot" style={{ background: color }} />{label}</div>
      <div className="kpi-value">{value === null ? <UnknownValue /> : <>{value}<small>{unit}</small></>}</div>
      <div className="kpi-hint">{hint}</div>
    </a>
  )
}

function AlertRow({ a }: { a: AlertItem }) {
  const detail = a.group === 'new' && ['a1', 'a2', 'a3', 'a4'].includes(a.id)
  const body = (
    <>
      <SeverityChip severity={a.severity} />
      <div className="alert-main">
        <div className="alert-name">{a.name}</div>
        <div className="alert-meta"><span className="mono">{a.host}</span>{a.repeat24h && <span className="repeat">24시간 {a.repeat24h}회 반복</span>}</div>
      </div>
      <span className="alert-time">{openedAgo(a.minutesOpen)}</span>
    </>
  )
  return detail ? <Link className="alert-row" to={`/incidents/${a.id}`}>{body}</Link> : <div className="alert-row">{body}</div>
}

function DiskForecast() {
  const { data } = useQuery({ queryKey: ['disk'], queryFn: api.diskForecasts })
  if (!data) return <div className="skeleton" />
  const color = (d: number) => (d <= 7 ? sevColor.high : d <= 30 ? sevColor.warning : sevColor.info)
  return (
    <>
      <div className="card-head"><h2 className="card-title">디스크 고갈 예측</h2><span className="card-sub">100%에 닿기까지 남은 일수</span>
        <span className="legend"><span><i style={{ background: sevColor.high }} />7일</span><span><i style={{ background: sevColor.warning }} />30일</span><span><i style={{ background: sevColor.info }} />이후</span></span></div>
      {data.map((d) => (
        <div className="bar-row" key={d.host}>
          <span className="mono">{d.host}</span>
          <div className="bar-track">{d.daysLeft !== null && <div className="bar-fill" style={{ width: `${Math.min(100, (d.daysLeft / 30) * 100)}%`, background: color(d.daysLeft) }} />}</div>
          <span>{d.daysLeft === null ? <span className="card-sub">확인 불가</span> : `${d.daysLeft}일`}</span>
        </div>
      ))}
    </>
  )
}

function TrendChart() {
  const { data } = useQuery({ queryKey: ['trend'], queryFn: api.trend })
  const option = useMemo(() => {
    if (!data) return null
    const sev: Severity[] = ['disaster', 'high', 'average', 'warning', 'info']
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 40, right: 8, top: 12, bottom: 28 },
      xAxis: { type: 'category', data: data.map((d) => d.label), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: chartText } },
      yAxis: { type: 'value', axisLabel: { color: chartText }, splitLine: { lineStyle: { color: chartGrid } } },
      series: sev.map((s) => ({ name: severityLabel[s], type: 'bar', stack: 'total', itemStyle: { color: sevColor[s] }, data: data.map((d) => d.counts[s]) })),
    }
  }, [data])
  return (
    <>
      <div className="card-head"><h2 className="card-title">하루에 알림이 열린 횟수</h2><span className="card-sub">최근 14일 · 심각도별</span></div>
      {option ? <EChart option={option} /> : <div className="skeleton" />}
    </>
  )
}

function Heatmap() {
  const { data } = useQuery({ queryKey: ['heat'], queryFn: api.heatmap })
  const option = useMemo(() => {
    if (!data) return null
    return {
      tooltip: { formatter: (p: { value: number[] }) => `${data.projects[p.value[1]]} · ${p.value[0]}시 · ${p.value[2]}건` },
      grid: { left: 56, right: 16, top: 8, bottom: 52 },
      xAxis: { type: 'category', data: Array.from({ length: 24 }, (_, h) => `${h}시`), splitArea: { show: false }, axisLabel: { color: chartText, interval: 2 }, axisLine: { show: false }, axisTick: { show: false } },
      yAxis: { type: 'category', inverse: true, data: data.projects, axisLabel: { color: chartText }, axisLine: { show: false }, axisTick: { show: false } },
      visualMap: { min: 0, max: 60, orient: 'horizontal', left: 'center', bottom: 0, itemWidth: 12, itemHeight: 120, text: ['많음', '적음'], textStyle: { color: chartText }, inRange: { color: ['#f0f0f2', '#f3c9c4', '#d13f36', '#8f1d1d'] } },
      series: [{ type: 'heatmap', data: data.cells, itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 4 } }],
    }
  }, [data])
  return (
    <>
      <div className="card-head"><h2 className="card-title">언제 · 어디서 장애가 났나</h2><span className="card-sub">최근 24시간 · 프로젝트별 알림 열린 횟수</span></div>
      {option ? <EChart option={option} tall /> : <div className="skeleton" />}
    </>
  )
}

export default function Dashboard() {
  const { ask } = useAssistant()
  const summary = useQuery({ queryKey: ['summary'], queryFn: api.summary })
  const alerts = useQuery({ queryKey: ['alerts'], queryFn: api.alerts })
  const groups = useQuery({ queryKey: ['groups'], queryFn: api.crossGroups })
  const baselines = useQuery({ queryKey: ['baselines'], queryFn: api.baselines })
  const s = summary.data

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">현황 · 장애 대응</h1>
        <p className="page-sub">{s ? `지금 열린 장애 ${s.openTotal}건 · 서버 ${s.serverTotal.toLocaleString()}대 감시 중` : '불러오는 중'}</p>
      </div>
      <div className="note" style={{ marginBottom: 16 }}>
        <Icon name="bell" size={16} />Zabbix 기본 '장애' 화면과 건수가 다를 수 있습니다. 이 화면은 최근 24시간 안에 열린 알림과 오래 열려 있는 알림을 나눠서 보여 줍니다. (목업 설명)
      </div>

      <div className="grid kpi">
        <Kpi label="새로 열린 장애" value={s?.newOpen ?? null} unit="건" hint="최근 24시간 안 · 높음 이상 0건" color={sevColor.high} href="#sec-new" />
        <Kpi label="반복해서 열리는 알림" value={s?.repeating ?? null} unit="건" hint="24시간에 3번 이상 열렸다 닫힘" color={sevColor.warning} href="#sec-new" />
        <Kpi label="오래 열려 있는 장애" value={s?.longOpen ?? null} unit="건" hint="가장 오래된 것 746일째" color={sevColor.info} href="#sec-old" />
        <Kpi label="30일 안에 가득 찰 디스크(예상)" value={s?.diskFullSoon ?? null} unit="대" hint="증가 속도가 그대로라면 · 지금 가득 찬 서버는 아님" color={sevColor.average} href="#sec-disk" />
      </div>

      <section className="card">
        <div className="card-head"><h2 className="card-title">지금 확인할 장애</h2><span className="card-sub">누르면 서버 상세 · 알림 판정식 · 관련 값</span></div>
        {!alerts.data ? <div className="skeleton" /> : (
          <>
            <Collapsible id="sec-new" title="새로 열린 장애" count={alerts.data.fresh.length} meta="최근 24시간 안에 열림 — 지금 생긴 문제" defaultOpen>
              {alerts.data.fresh.map((a) => <AlertRow key={a.id} a={a} />)}
            </Collapsible>
            <Collapsible id="sec-old" title="오래 열려 있는 장애" count={48} meta="24시간 넘게 열린 채 — 아직 문제인지, 정리할 알림인지 확인">
              {alerts.data.old.map((a) => <AlertRow key={a.id} a={a} />)}
              <div className="alert-row"><span className="card-sub">나머지 42건은 상세 목록 화면에서 확인합니다 (구현 예정)</span></div>
            </Collapsible>
          </>
        )}
      </section>

      <div className="grid two" style={{ marginTop: 16 }}>
        <section className="card">
          <div className="card-head"><h2 className="card-title">같은 알림이 여러 서버에서</h2><span className="card-sub">한 원인이 여러 서버에 동시에 나타난 것일 수 있다</span></div>
          {!groups.data ? <div className="skeleton" /> : groups.data.map((g) => (
            <div className="group-row" key={g.id}>
              <span className="count-pill">{g.serverCount}대</span>
              <span style={{ flex: 1, minWidth: 0 }}>{g.name}</span>
              <button className="btn small" onClick={() => ask(`${g.name} 알림이 ${g.serverCount}대에서 동시에 났어. 공통 원인이 뭐야?`)}>이 서버들 비교</button>
            </div>
          ))}
        </section>
        <section className="card">
          <div className="card-head"><h2 className="card-title">평소와 다른 값</h2><span className="card-sub">지금 같은 요일 · 시간대의 평소 범위를 벗어난 서버</span></div>
          {!baselines.data ? <div className="skeleton" /> : baselines.data.map((b) => (
            <div className="baseline-row" key={b.host}>
              <span className="baseline-host mono">{b.host}</span>
              <span>{b.metric} <span className="baseline-now">{b.now}{b.unit}</span></span>
              <span className="baseline-range">평소 {b.baselineMin}–{b.baselineMax}{b.unit}</span>
              <span className="baseline-since">{shortAgo(b.sinceMinutes)}</span>
            </div>
          ))}
        </section>
      </div>

      <div className="grid two" style={{ marginTop: 16 }}>
        <section className="card" id="sec-disk"><DiskForecast /></section>
        <section className="card"><TrendChart /></section>
      </div>
      <section className="card" style={{ marginTop: 16 }}><Heatmap /></section>
    </div>
  )
}
