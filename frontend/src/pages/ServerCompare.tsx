import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { cssVar } from '../lib/colors'
import { useThemeVersion } from '../hooks/useThemeVersion'
import type { ServerMetric } from '../lib/types'
import { UnknownValue } from '../components/Chips'
import { EChart } from '../components/EChart'

const MAX = 4
const DEFAULT = ['app-web-01', 'app-web-02', 'app-web-03']

interface Row {
  label: string
  unit: string
  get: (s: ServerMetric) => number | null
  level: (v: number, s: ServerMetric) => 'bad' | 'warn' | null
}
const rows: Row[] = [
  {
    label: 'CPU',
    unit: '%',
    get: (s) => s.cpu,
    level: (v, s) =>
      s.cpuBaselineMax !== null && v > s.cpuBaselineMax * 1.25
        ? 'bad'
        : s.cpuBaselineMax !== null && v > s.cpuBaselineMax
          ? 'warn'
          : null,
  },
  { label: '메모리', unit: '%', get: (s) => s.memory, level: (v) => (v >= 90 ? 'bad' : v >= 80 ? 'warn' : null) },
  { label: '디스크 사용', unit: '%', get: (s) => s.disk, level: (v) => (v >= 95 ? 'bad' : v >= 85 ? 'warn' : null) },
  { label: '스왑', unit: '%', get: (s) => s.swap, level: (v) => (v >= 30 ? 'warn' : null) },
  { label: '디스크 응답', unit: 'ms', get: (s) => s.ioMs, level: (v) => (v >= 20 ? 'bad' : v >= 10 ? 'warn' : null) },
  { label: '열린 알림', unit: '건', get: (s) => s.openAlerts, level: (v) => (v >= 3 ? 'warn' : null) },
]

export default function ServerCompare() {
  const [params, setParams] = useSearchParams()
  const servers = useQuery({ queryKey: ['servers'], queryFn: api.servers })
  const groups = useQuery({ queryKey: ['groups'], queryFn: api.crossGroups })
  const theme = useThemeVersion()

  const groupId = params.get('group')
  const group = groups.data?.find((g) => g.id === groupId)
  const picked = params.get('hosts')?.split(',').filter(Boolean)
  const wanted = picked ?? group?.hosts ?? DEFAULT
  const hosts = wanted.slice(0, MAX)

  const setHosts = (next: string[]) => setParams({ hosts: next.join(',') }, { replace: true })
  const toggle = (h: string) => setHosts(hosts.includes(h) ? hosts.filter((x) => x !== h) : [...hosts, h].slice(0, MAX))
  const pickGroup = (id: string) => setParams({ group: id }, { replace: true })

  const selected = (servers.data ?? []).filter((s) => hosts.includes(s.host))

  const option = useMemo(() => {
    void theme
    const text = cssVar('--chart-text')
    const colors = [cssVar('--series-1'), cssVar('--series-2'), cssVar('--series-3'), cssVar('--series-4')]
    return {
      tooltip: {
        trigger: 'axis',
        backgroundColor: cssVar('--surface'),
        borderColor: cssVar('--border-strong'),
        textStyle: { color: cssVar('--text') },
      },
      grid: { left: 40, right: 12, top: 12, bottom: 28 },
      xAxis: {
        type: 'category',
        data: Array.from({ length: 24 }, (_, h) => `${h}시`),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: text, interval: 3 },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: { color: text, formatter: '{value}%' },
        splitLine: { lineStyle: { color: cssVar('--chart-grid') } },
      },
      series: selected.map((s, i) => ({
        name: s.host,
        type: 'line',
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2.5, color: colors[i % 4] },
        itemStyle: { color: colors[i % 4] },
        data: s.cpuSeries,
      })),
    }
  }, [selected, theme])

  const seriesColor = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)']

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">서버 비교</h1>
        <p className="page-sub">
          같은 알림이 난 서버들의 지표를 나란히 놓고 달라진 점을 찾습니다. 최대 {MAX}대까지 비교합니다.
        </p>
      </div>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">같은 알림이 난 서버 묶음</h2>
          <span className="card-sub">누르면 해당 묶음의 서버가 선택됩니다</span>
        </div>
        <div className="pick">
          {groups.data?.map((g) => (
            <button key={g.id} className={g.id === groupId && !picked ? 'on' : ''} onClick={() => pickGroup(g.id)}>
              {g.name} · {g.serverCount}대
            </button>
          ))}
        </div>
        <div className="card-head" style={{ marginTop: 18 }}>
          <h2 className="card-title">비교할 서버</h2>
          <span className="card-sub">
            {hosts.length}/{MAX}대 선택{wanted.length > MAX ? ` · 묶음 ${wanted.length}대 중 처음 ${MAX}대만 표시` : ''}
          </span>
        </div>
        <div className="pick">
          {servers.data?.map((s) => (
            <button
              key={s.host}
              className={hosts.includes(s.host) ? 'on' : ''}
              disabled={!hosts.includes(s.host) && hosts.length >= MAX}
              onClick={() => toggle(s.host)}
            >
              {s.host}
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">지표 비교</h2>
          <span className="card-sub">{selected[0]?.collectedAt} 수집 · 색이 진한 값은 기준을 넘은 값</span>
        </div>
        {!servers.data ? (
          <div className="skeleton" />
        ) : selected.length === 0 ? (
          <p className="card-sub">비교할 서버를 선택해 주세요.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>지표</th>
                  {selected.map((s) => (
                    <th key={s.host} className="num">
                      <span className="mono">{s.host}</span> <span className="chip neutral">{s.project}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.label}>
                    <td>{r.label}</td>
                    {selected.map((s) => {
                      const v = r.get(s)
                      const lv = v === null ? null : r.level(v, s)
                      return (
                        <td
                          key={s.host}
                          className={`num ${lv === 'bad' ? 'cell-bad' : lv === 'warn' ? 'cell-warn' : ''}`}
                        >
                          {v === null ? <UnknownValue /> : `${v}${r.unit}`}
                        </td>
                      )
                    })}
                  </tr>
                ))}
                <tr className="hl">
                  <td>CPU 평소 최대</td>
                  {selected.map((s) => (
                    <td key={s.host} className="num">
                      {s.cpuBaselineMax === null ? <UnknownValue /> : `${s.cpuBaselineMax}%`}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">CPU 사용률, 최근 24시간</h2>
          <span className="legend">
            {selected.map((s, i) => (
              <span key={s.host}>
                <i style={{ background: seriesColor[i % 4] }} />
                {s.host}
              </span>
            ))}
          </span>
        </div>
        {selected.length === 0 ? (
          <p className="card-sub">서버를 선택하면 추이가 나타납니다.</p>
        ) : (
          <EChart option={option} />
        )}
        {selected.some((s) => s.cpu === null) && (
          <p className="card-sub" style={{ marginTop: 8 }}>
            CPU 지표를 수집하지 않은 서버는 선이 그려지지 않습니다. (확인할 수 없음)
          </p>
        )}
      </section>
    </div>
  )
}
