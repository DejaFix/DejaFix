import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { cssVar, sevCss } from '../lib/colors'
import { useThemeVersion } from '../hooks/useThemeVersion'
import { severityLabel, shortAgo } from '../lib/format'
import { useDashboardSummary, useIncidents } from '../lib/queries'
import type { DashboardSummary, Incident, Measured, Severity } from '../lib/types'
import { Collapsible } from '../components/Collapsible'
import { EChart } from '../components/EChart'
import { AnalysisBadge, SeverityInfoChip, Unknown } from '../components/IncidentParts'
import { kstShort } from '../components/incidentFormat'

/** Measured 하나를 화면 값으로. unknown이거나 value가 null이면 0·빈칸 대신 UnknownValue(SAFE-10). */
function MeasuredText({ m }: { m: Measured | undefined }) {
  if (!m) return <Unknown reason="TOOL_ERROR" />
  if (m.unknown || m.value === null) return <Unknown reason={m.unknown_reason} at={m.collected_at} />
  return <>{m.value.toLocaleString('ko-KR')}</>
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
}function DiskForecast() {
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
          itemStyle: { borderColor: cssVar('--surface'), borderWidth: 2, borderRadius: 0 },
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

const SEV_KEY = ['info', 'info', 'warning', 'average', 'high', 'disaster'] as const
const LIST_LIMIT = 10

const minutesSince = (iso: string, nowMs: number) => Math.max(0, Math.round((nowMs - new Date(iso).getTime()) / 60_000))

/** 장애가 있는 서버만 타일로 그리고, 나머지는 '정상 N대' 한 칸으로 묶는다(정상 서버 이름은 이 화면이 받지 않는다). */
function ServerMap({ list, okHosts, loading }: { list: Incident[]; okHosts: Measured | undefined; loading: boolean }) {
  const tiles = useMemo(() => {
    const m = new Map<string, { name: string; level: number; count: number; firstId: number }>()
    for (const i of list) {
      if (i.status !== 'problem') continue
      const name = i.host.name ?? '(호스트 불명)'
      const cur = m.get(name)
      if (!cur) m.set(name, { name, level: i.severity.level, count: 1, firstId: i.id })
      else {
        cur.count += 1
        if (i.severity.level > cur.level) {
          cur.level = i.severity.level
          cur.firstId = i.id
        }
      }
    }
    return [...m.values()].sort((a, b) => b.level - a.level || b.count - a.count)
  }, [list])
  return (
    <section className="card" id="sec-hosts">
      <div className="card-head">
        <h2 className="card-title">서버 지도</h2>
        <span className="card-sub">장애가 있는 서버만 표시 · 나머지는 정상으로 묶음</span>
      </div>
      <div className="tiles">
        {tiles.map((t) => (
          <Link key={t.name} to={`/incidents/${t.firstId}`} className={`tile sev-${SEV_KEY[t.level]}`}>
            <span className="tile-name mono">{t.name}</span>
            <span className="tile-count">장애 {t.count}건</span>
          </Link>
        ))}
        <div className="tile ok">
          <span className="tile-name">정상</span>
          <span className="tile-count">
            {loading ? '…' : <MeasuredText m={okHosts} />}대
          </span>
        </div>
      </div>
    </section>
  )
}

/** 우측 레일: 가장 급한 장애 1건. 심각도 색 그라데이션 카드이고, 값은 목록(#10)에 있는 것만 쓴다. */
function UrgentCard({ incident, nowMs, loading }: { incident: Incident | undefined; nowMs: number; loading: boolean }) {
  return (
    <section className="rail-block">
      <h2 className="rail-title">가장 급한 장애</h2>
      {loading ? (
        <div className="skeleton" />
      ) : !incident ? (
        <div className="urgent calm">해결되지 않은 장애가 없습니다.</div>
      ) : (
        <Link to={`/incidents/${incident.id}`} className={`urgent sev-${SEV_KEY[incident.severity.level]}`}>
          <span className="urgent-chip">{severityName[incident.severity.level]}</span>
          <span className="urgent-title">{incident.title}</span>
          <span className="urgent-meta">
            <span>
              <small>호스트</small>
              <b className="mono">{incident.host.name ?? '확인할 수 없음'}</b>
            </span>
            <span>
              <small>시작</small>
              <b>{kstShort(incident.started_at) ?? '—'}</b>
            </span>
            <span>
              <small>경과</small>
              <b>{shortAgo(minutesSince(incident.started_at, nowMs))}</b>
            </span>
          </span>
        </Link>
      )}
    </section>
  )
}

const severityName = ['미분류', '정보', '경고', '보통', '높음', '심각']

/** 값 하나. 모르면 0·빈칸 대신 '확인할 수 없음'(SAFE-10). */
function Num({ m }: { m: Measured | undefined }) {
  if (!m || m.unknown || m.value === null) return <span className="sum-unknown">확인할 수 없음</span>
  return <>{m.value.toLocaleString('ko-KR')}</>
}

/** 우측 레일: 요약 4칸. 현황 홈 KPI(#5)를 그대로 보여 준다. */
function SummaryTiles({ s, loading }: { s: DashboardSummary | undefined; loading: boolean }) {
  const unit = (m: Measured | undefined) => (m && !m.unknown && m.value !== null ? m.unit : '')
  return (
    <section className="rail-block">
      <h2 className="rail-title">요약</h2>
      <div className="sum-grid">
        <div className="sum-tile">
          <span className="sum-label">
            <i className="dot" style={{ background: sevCss.warning }} />
            진행 중
          </span>
          <span className="sum-value">{loading ? '…' : <Num m={s?.active_incidents} />}</span>
          <small>{unit(s?.active_incidents)}</small>
        </div>
        <div className="sum-tile">
          <span className="sum-label">
            <i className="dot" style={{ background: sevCss.high }} />
            높음 이상
          </span>
          <span className="sum-value">{loading ? '…' : <Num m={s?.high_incidents} />}</span>
          <small>{unit(s?.high_incidents)}</small>
        </div>
        <div className="sum-tile">
          <span className="sum-label">
            <i className="dot" style={{ background: sevCss.info }} />
            정상 호스트
          </span>
          <span className="sum-value">
            {loading ? (
              '…'
            ) : (
              <>
                <Num m={s?.hosts.ok} /> / <Num m={s?.hosts.total} />
              </>
            )}
          </span>
          <small>{s && !s.hosts.unknown.unknown && s.hosts.unknown.value ? `확인 불가 ${s.hosts.unknown.value}대` : '대'}</small>
        </div>
        <div className="sum-tile">
          <span className="sum-label">
            <i className="dot" style={{ background: sevCss.average }} />
            오늘 리포트
          </span>
          <span className="sum-value">{loading ? '…' : <Num m={s?.reports_today} />}</span>
          <small>
            {s && !s.avg_analysis_sec.unknown && s.avg_analysis_sec.value !== null
              ? `평균 분석 ${s.avg_analysis_sec.value}초`
              : unit(s?.reports_today)}
          </small>
        </div>
      </div>
    </section>
  )
}
export default function Dashboard() {
  const summary = useDashboardSummary()
  const incidents = useIncidents({ limit: 50 })
  const list = incidents.data?.data
  const nowMs = incidents.dataUpdatedAt
  // 우선순위 = 해결되지 않은 장애를 심각도 높은 순, 같으면 최근 시작 순. 나머지(해결됨 포함)는 접어 둔다.
  const { top, rest, first } = useMemo(() => {
    const open = (list ?? [])
      .filter((i) => i.status === 'problem')
      .sort((a, b) => b.severity.level - a.severity.level || Date.parse(b.started_at) - Date.parse(a.started_at))
    const resolved = (list ?? []).filter((i) => i.status !== 'problem')
    return { top: open.slice(0, LIST_LIMIT), rest: [...open.slice(LIST_LIMIT), ...resolved], first: open[0] }
  }, [list])
  const groups = useQuery({ queryKey: ['groups'], queryFn: api.crossGroups })
  const baselines = useQuery({ queryKey: ['baselines'], queryFn: api.baselines })
  const s = summary.data?.data
  const loadingKpi = summary.isPending
  const high = s?.high_incidents
  const headline =
    !high || high.unknown || high.value === null
      ? loadingKpi
        ? '불러오는 중'
        : '장애 현황을 확인할 수 없습니다.'
      : high.value > 0
        ? `지금 확인이 필요한 장애가 ${high.value.toLocaleString('ko-KR')}건 있습니다.`
        : '지금 급하게 확인할 장애는 없습니다.'

  return (
    <div className="page page-wide">
      <div className="dash-layout">
      <div className="dash-main">
      <div className="hero">
        <div className="hero-line">
          <h1 className="page-title">현황 · 장애 대응</h1>
          <span
            className="info-tip"
            tabIndex={0}
            role="note"
            aria-label="Zabbix 기본 장애 화면과 건수가 다를 수 있습니다"
            data-tip="Zabbix 기본 ‘장애’ 화면과 건수가 다를 수 있습니다. 이 화면은 수집된 장애를 심각도 순으로 보여 줍니다."
          >
            i
          </span>
        </div>
        <p className="hero-headline">{headline}</p>
      </div>

      <section id="sec-priority" className="priority">
        <div className="card-head">
          <h2 className="card-title">지금 확인할 장애</h2>
          <span className="card-sub">심각도 순 · 누르면 상세 · AI 분석 · 근거</span>
        </div>
        {incidents.isError && !list ? (
          <p className="card-sub">장애 목록을 불러오지 못했습니다. 15초 뒤 다시 시도합니다.</p>
        ) : !list ? (
          <div className="skeleton" />
        ) : (
          <>
            {incidents.isError && <p className="card-sub">갱신 실패 — 마지막으로 받은 목록입니다.</p>}
            {top.length === 0 ? (
              <div className="card calm-card">
                <span className="card-sub">해결되지 않은 장애가 없습니다.</span>
              </div>
            ) : (
              <div className="card list-card">
                {top.map((i) => (
                  <IncidentRow key={i.id} i={i} />
                ))}
              </div>
            )}
            {rest.length > 0 && (
              <Collapsible id="sec-rest" title="나머지 · 해결된 장애" count={rest.length} meta="목록 밖의 장애">
                {rest.map((i) => (
                  <IncidentRow key={i.id} i={i} />
                ))}
                {incidents.data?.meta.next_cursor && (
                  <div className="alert-row">
                    <span className="card-sub">더 오래된 장애는 상세 목록 화면에서 확인합니다 (구현 예정)</span>
                  </div>
                )}
              </Collapsible>
            )}
          </>
        )}
      </section>

      <div className="grid two section-gap">
        <ServerMap list={list ?? []} okHosts={s?.hosts.ok} loading={loadingKpi} />
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
      </div>

      <div className="section-gap">
        <Collapsible title="추가 분석" meta="평소와 다른 값 · 디스크 예측 · 추세 · 시간대 분포">
          <section className="card inner-card">
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
          <div className="grid two section-gap">
            <section className="card" id="sec-disk">
              <DiskForecast />
            </section>
            <section className="card">
              <TrendChart />
            </section>
          </div>
          <section className="card section-gap">
            <Heatmap />
          </section>
        </Collapsible>
      </div>
      </div>
      <aside className="dash-rail" aria-label="요약">
        <UrgentCard incident={first} nowMs={nowMs} loading={!list && !incidents.isError} />
        <SummaryTiles s={s} loading={loadingKpi} />
      </aside>
      </div>
    </div>
  )
}