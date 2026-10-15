import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { cssVar, sevCss } from '../lib/colors'
import { useThemeVersion } from '../hooks/useThemeVersion'
import { severityLabel, shortAgo } from '../lib/format'
import { useDashboardSummary, useIncidents } from '../lib/queries'
import type { Incident, Measured, Severity } from '../lib/types'
import { Collapsible } from '../components/Collapsible'
import { EChart } from '../components/EChart'
import { Icon } from '../components/Icon'
import { AnalysisBadge, SeverityInfoChip, Unknown } from '../components/IncidentParts'
import { kstShort } from '../components/incidentFormat'

/** Measured 하나를 화면 값으로. unknown이거나 value가 null이면 0·빈칸 대신 UnknownValue(SAFE-10). */
function MeasuredText({ m }: { m: Measured | undefined }) {
  if (!m) return <Unknown reason="TOOL_ERROR" />
  if (m.unknown || m.value === null) return <Unknown reason={m.unknown_reason} at={m.collected_at} />
  return <>{m.value.toLocaleString('ko-KR')}</>
}

function Kpi({
  label,
  value,
  unit,
  hint,
  color,
  target,
  loading,
}: {
  label: string
  value: React.ReactNode
  unit?: string
  hint: React.ReactNode
  color: string
  target?: string
  loading: boolean
}) {
  const go = () => target && document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  const body = (
    <>
      <div className="kpi-label">
        <span className="dot" style={{ background: color }} />
        {label}
      </div>
      <div className="kpi-value">
        {loading ? (
          '…'
        ) : (
          <>
            {value}
            {unit && <small>{unit}</small>}
          </>
        )}
      </div>
      <div className="kpi-hint">{loading ? '불러오는 중' : hint}</div>
    </>
  )
  return target ? (
    <button type="button" className="card kpi-card" onClick={go}>
      {body}
    </button>
  ) : (
    <div className="card kpi-card">{body}</div>
  )
}

function IncidentRow({ i }: { i: Incident }) {
  return (
    <Link className="alert-row" to={`/incidents/${i.id}`}>
      <SeverityInfoChip severity={i.severity} />
      <div className="alert-main">
        <div className="alert-name">{i.title}</div>
        <div className="alert-meta">
          <span className="mono">{i.host.name ?? <Unknown reason="NOT_COLLECTED" />}</span>
          {i.status === 'resolved' && <span className="repeat">해결됨</span>}
        </div>
      </div>
      <AnalysisBadge status={i.analysis.status} />
      <span className="alert-time">{kstShort(i.started_at) ?? '—'}</span>
    </Link>
  )
}

const DAY_MS = 24 * 3600_000

function DiskForecast() {
  const { data } = useQuery({ queryKey: ['disk'], queryFn: api.diskForecasts })
  if (!data) return <div className="skeleton" />
  const color = (d: number) => (d <= 7 ? sevCss.high : d <= 30 ? sevCss.warning : sevCss.info)
  return (
    <>
      <div className="card-head">
        <h2 className="card-title">디스크 고갈 예측</h2>
        <span className="card-sub">100%에 닿기까지 남은 일수</span>
        <span className="legend">
          <span>
            <i style={{ background: sevCss.high }} />
            7일
          </span>
          <span>
            <i style={{ background: sevCss.warning }} />
            30일
          </span>
          <span>
            <i style={{ background: sevCss.info }} />
            이후
          </span>
        </span>
      </div>
      {data.map((d) => (
        <div className="bar-row" key={d.host}>
          <span className="mono">{d.host}</span>
          <div className="bar-track">
            {d.daysLeft !== null && (
              <div
                className="bar-fill"
                style={{ width: `${Math.min(100, (d.daysLeft / 30) * 100)}%`, background: color(d.daysLeft) }}
              />
            )}
          </div>
          <span>{d.daysLeft === null ? <span className="card-sub">확인 불가</span> : `${d.daysLeft}일`}</span>
        </div>
      ))}
    </>
  )
}

function TrendChart() {
  const { data } = useQuery({ queryKey: ['trend'], queryFn: api.trend })
  const theme = useThemeVersion()
  const option = useMemo(() => {
    if (!data) return null
    void theme
    const text = cssVar('--chart-text')
    const sev: Severity[] = ['disaster', 'high', 'average', 'warning', 'info']
    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: cssVar('--surface'),
        borderColor: cssVar('--border-strong'),
        textStyle: { color: cssVar('--text') },
      },
      grid: { left: 40, right: 8, top: 12, bottom: 28 },
      xAxis: {
        type: 'category',
        data: data.map((d) => d.label),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: text },
      },
      yAxis: { type: 'value', axisLabel: { color: text }, splitLine: { lineStyle: { color: cssVar('--chart-grid') } } },
      series: sev.map((s) => ({
        name: severityLabel[s],
        type: 'bar',
        stack: 'total',
        itemStyle: { color: cssVar(`--sev-${s}`) },
        data: data.map((d) => d.counts[s]),
      })),
    }
  }, [data, theme])
  return (
    <>
      <div className="card-head">
        <h2 className="card-title">하루에 알림이 열린 횟수</h2>
        <span className="card-sub">최근 14일 · 심각도별</span>
      </div>
      {option ? <EChart option={option} /> : <div className="skeleton" />}
    </>
  )
}

function Heatmap() {
  const { data } = useQuery({ queryKey: ['heat'], queryFn: api.heatmap })
  const theme = useThemeVersion()
  const option = useMemo(() => {
    if (!data) return null
    void theme
    const chartText = cssVar('--chart-text')
    return {
      tooltip: {
        backgroundColor: cssVar('--surface'),
        borderColor: cssVar('--border-strong'),
        textStyle: { color: cssVar('--text') },
        formatter: (p: { value: number[] }) => `${data.projects[p.value[1]]} · ${p.value[0]}시 · ${p.value[2]}건`,
      },
      grid: { left: 56, right: 16, top: 8, bottom: 52 },
      xAxis: {
        type: 'category',
        data: Array.from({ length: 24 }, (_, h) => `${h}시`),
        splitArea: { show: false },
        axisLabel: { color: chartText, interval: 2 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: data.projects,
        axisLabel: { color: chartText },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      visualMap: {
        min: 0,
        max: 60,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        itemWidth: 12,
        itemHeight: 120,
        text: ['많음', '적음'],
        textStyle: { color: chartText },
        inRange: { color: [cssVar('--heat-0'), cssVar('--heat-1'), cssVar('--heat-2'), cssVar('--heat-3')] },
      },
      series: [
        {
          type: 'heatmap',
          data: data.cells,
          itemStyle: { borderColor: cssVar('--surface'), borderWidth: 2, borderRadius: 4 },
        },
      ],
    }
  }, [data, theme])
  return (
    <>
      <div className="card-head">
        <h2 className="card-title">언제 · 어디서 장애가 났나</h2>
        <span className="card-sub">최근 24시간 · 프로젝트별 알림 열린 횟수</span>
      </div>
      {option ? <EChart option={option} tall /> : <div className="skeleton" />}
    </>
  )
}

export default function Dashboard() {
  const summary = useDashboardSummary()
  const incidents = useIncidents({ limit: 50 })
  const list = incidents.data?.data
  // 표시용 묶음일 뿐이다: 시작 24시간 안 = 새 장애, 그 외 = 오래된 장애
  const nowMs = incidents.dataUpdatedAt
  const fresh = list?.filter((i) => nowMs - new Date(i.started_at).getTime() < DAY_MS) ?? []
  const old = list?.filter((i) => nowMs - new Date(i.started_at).getTime() >= DAY_MS) ?? []
  const groups = useQuery({ queryKey: ['groups'], queryFn: api.crossGroups })
  const baselines = useQuery({ queryKey: ['baselines'], queryFn: api.baselines })
  const s = summary.data?.data
  const loadingKpi = summary.isPending

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">현황 · 장애 대응</h1>
        <p className="page-sub">
          {s ? (
            <>
              지금 진행 중인 장애 <MeasuredText m={s.active_incidents} />건 · 감시 호스트{' '}
              <MeasuredText m={s.hosts.total} />대
            </>
          ) : loadingKpi ? (
            '불러오는 중'
          ) : (
            <Unknown reason="TOOL_ERROR" />
          )}
        </p>
      </div>
      <div className="note" style={{ marginBottom: 16 }}>
        <Icon name="bell" size={16} />
        Zabbix 기본 '장애' 화면과 건수가 다를 수 있습니다. 이 화면은 최근 24시간 안에 열린 알림과 오래 열려 있는 알림을
        나눠서 보여 줍니다. (목업 설명)
      </div>

      <div className="grid kpi">
        <Kpi
          label="진행 중인 장애"
          value={<MeasuredText m={s?.active_incidents} />}
          unit={s && !s.active_incidents.unknown ? s.active_incidents.unit : undefined}
          hint="수집된 장애 중 아직 해결되지 않은 것"
          color={sevCss.warning}
          target="sec-new"
          loading={loadingKpi}
        />
        <Kpi
          label="높음 이상 장애"
          value={<MeasuredText m={s?.high_incidents} />}
          unit={s && !s.high_incidents.unknown ? s.high_incidents.unit : undefined}
          hint="심각도 높음·심각(4·5)"
          color={sevCss.high}
          target="sec-new"
          loading={loadingKpi}
        />
        <Kpi
          label="정상 호스트"
          value={
            <>
              <MeasuredText m={s?.hosts.ok} /> / <MeasuredText m={s?.hosts.total} />
            </>
          }
          unit="대"
          hint={
            <>
              확인 불가 <MeasuredText m={s?.hosts.unknown} />대
            </>
          }
          color={sevCss.info}
          loading={loadingKpi}
        />
        <Kpi
          label="오늘 리포트"
          value={<MeasuredText m={s?.reports_today} />}
          unit={s && !s.reports_today.unknown ? s.reports_today.unit : undefined}
          hint={
            <>
              평균 분석 시간 <MeasuredText m={s?.avg_analysis_sec} />
              {s && !s.avg_analysis_sec.unknown && s.avg_analysis_sec.value !== null ? '초' : ''}
            </>
          }
          color={sevCss.average}
          loading={loadingKpi}
        />
      </div>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">지금 확인할 장애</h2>
          <span className="card-sub">누르면 장애 상세 · AI 분석 · 근거</span>
        </div>
        {incidents.isError && !list ? (
          <p className="card-sub">장애 목록을 불러오지 못했습니다. 15초 뒤 다시 시도합니다.</p>
        ) : !list ? (
          <div className="skeleton" />
        ) : (
          <>
            {incidents.isError && <p className="card-sub">갱신 실패 — 마지막으로 받은 목록입니다.</p>}
            <Collapsible
              id="sec-new"
              title="새로 열린 장애"
              count={fresh.length}
              meta="최근 24시간 안에 시작 — 지금 생긴 문제"
              defaultOpen
            >
              {fresh.length === 0 && (
                <div className="alert-row">
                  <span className="card-sub">최근 24시간 안에 시작한 장애가 없습니다.</span>
                </div>
              )}
              {fresh.map((i) => (
                <IncidentRow key={i.id} i={i} />
              ))}
            </Collapsible>
            <Collapsible id="sec-old" title="오래된 장애" count={old.length} meta="24시간 넘게 지난 장애">
              {old.length === 0 && (
                <div className="alert-row">
                  <span className="card-sub">해당하는 장애가 없습니다.</span>
                </div>
              )}
              {old.map((i) => (
                <IncidentRow key={i.id} i={i} />
              ))}
              {incidents.data?.meta.next_cursor && (
                <div className="alert-row">
                  <span className="card-sub">더 오래된 장애는 상세 목록 화면에서 확인합니다 (구현 예정)</span>
                </div>
              )}
            </Collapsible>
          </>
        )}
      </section>

      <div className="grid two" style={{ marginTop: 16 }}>
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">같은 알림이 여러 서버에서</h2>
            <span className="card-sub">한 원인이 여러 서버에 동시에 나타난 것일 수 있다</span>
          </div>
          {!groups.data ? (
            <div className="skeleton" />
          ) : (
            groups.data.map((g) => (
              <div className="group-row" key={g.id}>
                <span className="count-pill">{g.serverCount}대</span>
                <span style={{ flex: 1, minWidth: 0 }}>{g.name}</span>
                <Link className="btn small" to={`/compare?group=${g.id}`}>
                  이 서버들 비교
                </Link>
              </div>
            ))
          )}
        </section>
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">평소와 다른 값</h2>
            <span className="card-sub">지금 같은 요일 · 시간대의 평소 범위를 벗어난 서버</span>
          </div>
          {!baselines.data ? (
            <div className="skeleton" />
          ) : (
            baselines.data.map((b) => (
              <div className="baseline-row" key={b.host}>
                <span className="baseline-host mono">{b.host}</span>
                <span>
                  {b.metric}{' '}
                  <span className="baseline-now">
                    {b.now}
                    {b.unit}
                  </span>
                </span>
                <span className="baseline-range">
                  평소 {b.baselineMin}–{b.baselineMax}
                  {b.unit}
                </span>
                <span className="baseline-since">{shortAgo(b.sinceMinutes)}</span>
              </div>
            ))
          )}
        </section>
      </div>

      <div className="grid two" style={{ marginTop: 16 }}>
        <section className="card" id="sec-disk">
          <DiskForecast />
        </section>
        <section className="card">
          <TrendChart />
        </section>
      </div>
      <section className="card" style={{ marginTop: 16 }}>
        <Heatmap />
      </section>
    </div>
  )
}
