import { useMemo, useState } from 'react'
import {
  Card,
  Chip,
  DataTable,
  EmptyState,
  Notice,
  PageHeader,
  StatCard,
  UnknownValue,
  cssVar,
  useThemeVersion,
  type Column,
} from '@dejafix/common-frontend'
import { EChart } from '@dejafix/common-frontend/charts'
import { useOrchestratorDepartments, useOrchestratorIncidents } from '../lib/queries'
import type {
  OrchestratorDepartment,
  OrchestratorIncident,
  OrchestratorSeriesPoint,
  OrchestratorStep,
  OrchestratorStepStatus,
} from '../lib/types'
import { usePrefs } from '../state/prefs'
import { useAuth } from '../state/auth'
import '../styles/orchestrator.css'

// 총괄 에이전트 화면 (관리자 > 총괄 에이전트). 읽기 전용: 승인·실행·장애 주입 버튼이 없다(SAFE-04).
// 사건 흐름과 부서별 사용량은 Backend 가 총괄의 읽기 API 를 그대로 중계한 값이다(contracts/api.md 6장).
// 분석 문장·원인·티어는 여기서 만들지 않는다. 값이 없으면 0 이 아니라 '확인할 수 없음'.

const DEPT_LABEL: Record<string, { title: string; desc: string }> = {
  infra: { title: '인프라 (DejaFix)', desc: '장애 진단 · 롤백 · 복구 검증' },
  data: { title: '데이터분석', desc: '이상 탐지 · 영향 분석' },
  planning: { title: '기획개발', desc: '관련 PR 찾기 · 사건 연결' },
  marketing: { title: '마케팅', desc: '점검·정상화 공지 초안과 게시' },
  support: { title: '고객지원', desc: '문의 응대 · 보상 판정' },
  finance: { title: '재무/정산', desc: '손실 리포트 · 금액 검증' },
  hr: { title: '인사운영', desc: '사건 기록 · 인수인계' },
}
const deptTitle = (name: string) => DEPT_LABEL[name]?.title ?? name

const STEP_STATUS: Record<OrchestratorStepStatus, { label: string; chip: string }> = {
  pending: { label: '대기', chip: 'neutral' },
  running: { label: '진행 중', chip: 'info' },
  completed: { label: '완료', chip: 'green' },
  failed: { label: '실패', chip: 'high' },
  held: { label: '승인 대기', chip: 'amber' },
  skipped: { label: '건너뜀', chip: 'neutral' },
  rejected_by_human: { label: '거절', chip: 'high' },
  transfer_queued: { label: '이관 큐', chip: 'amber' },
}
const INCIDENT_STATUS = {
  open: { label: '진행 중', chip: 'info' },
  resolved: { label: '해결됨', chip: 'green' },
  degraded: { label: '일부 미완료로 종료', chip: 'amber' },
} as const

const pct = (v: number | null | undefined) => (typeof v === 'number' ? Math.round(v * 100) : null)

function useClock() {
  const { tz } = usePrefs()
  return (iso: string | null | undefined) =>
    iso ? new Date(iso).toLocaleTimeString('en-GB', { timeZone: tz === 'KST' ? 'Asia/Seoul' : 'UTC' }) : '-'
}

/** 호출 수를 작은 선으로 (부서 카드·skill 표). 값이 모두 0이면 선을 그리지 않는다 */
function Sparkline({
  points,
  width = 84,
  height = 24,
}: {
  points: OrchestratorSeriesPoint[]
  width?: number
  height?: number
}) {
  const values = points.map((p) => p.calls)
  const max = Math.max(...values, 1)
  const step = width / Math.max(values.length - 1, 1)
  const y = (v: number) => height - 2 - (v / max) * (height - 4)
  const d = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return (
    <svg
      className="orch-spark"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="호출 수 추이"
    >
      <line x1="0" y1={height - 1} x2={width} y2={height - 1} stroke="var(--border-strong)" />
      {values.some((v) => v > 0) && <path d={d} fill="none" stroke="var(--primary)" strokeWidth="1.6" />}
    </svg>
  )
}

/** 최근 10분 사용량: 막대 = 30초당 호출 수(오류는 빨강), 선 = 평균 응답 시간 */
function UsageChart({ points }: { points: OrchestratorSeriesPoint[] }) {
  const theme = useThemeVersion()
  const { tz } = usePrefs()
  const option = useMemo(() => {
    const zone = tz === 'KST' ? 'Asia/Seoul' : 'UTC'
    const labels = points.map((p) =>
      new Date(p.t).toLocaleTimeString('en-GB', { timeZone: zone, hour12: false }).slice(0, 5),
    )
    return {
      grid: { left: 36, right: 44, top: 24, bottom: 26 },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: labels, axisLabel: { color: cssVar('--text-3') } },
      yAxis: [
        {
          type: 'value',
          name: '호출',
          minInterval: 1,
          axisLabel: { color: cssVar('--text-3') },
          splitLine: { lineStyle: { color: cssVar('--border') } },
        },
        { type: 'value', name: 'ms', axisLabel: { color: cssVar('--text-3') }, splitLine: { show: false } },
      ],
      series: [
        {
          name: '정상 호출',
          type: 'bar',
          stack: 'calls',
          data: points.map((p) => p.calls - p.errors),
          itemStyle: { color: cssVar('--primary') },
        },
        {
          name: '오류',
          type: 'bar',
          stack: 'calls',
          data: points.map((p) => p.errors),
          itemStyle: { color: cssVar('--sev-high') },
        },
        {
          name: '평균 응답(ms)',
          type: 'line',
          yAxisIndex: 1,
          connectNulls: false,
          data: points.map((p) => p.avg_ms),
          itemStyle: { color: cssVar('--accent') },
        },
      ],
    }
    // theme: 라이트/다크가 바뀌면 색을 다시 읽는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, tz, theme])
  return <EChart option={option} />
}

function stepColumns(clock: (iso: string | null | undefined) => string): Column<OrchestratorStep>[] {
  return [
    {
      key: 'label',
      header: '단계',
      render: (s) => (
        <>
          {s.label}
          {s.grade && s.grade !== 'read' ? <Chip className="orch-grade">{s.grade}</Chip> : null}
          {s.note ? (
            <div className="card-sub">
              {s.note}
              {s.transferred_to ? ` → ${s.transferred_to}` : ''}
            </div>
          ) : null}
        </>
      ),
    },
    { key: 'dept', header: '부서', render: (s) => (s.dept ? deptTitle(s.dept) : '-') },
    {
      key: 'status',
      header: '상태',
      render: (s) => <Chip className={STEP_STATUS[s.status]?.chip}>{STEP_STATUS[s.status]?.label ?? s.status}</Chip>,
    },
    { key: 'attempts', header: '시도', numeric: true, render: (s) => (s.attempts ? s.attempts : '') },
    { key: 'finished_at', header: '끝난 시각', numeric: true, render: (s) => clock(s.finished_at) },
  ]
}

function IncidentSection({
  incidents,
  current,
  onPick,
}: {
  incidents: OrchestratorIncident[]
  current: OrchestratorIncident | undefined
  onPick: (id: string) => void
}) {
  const clock = useClock()
  const ordered = [...incidents].reverse() // 최신 사건이 위
  if (!current) {
    return <EmptyState title="아직 처리한 사건이 없습니다" />
  }
  const columns = stepColumns(clock)
  const incidentColumns: Column<OrchestratorIncident>[] = [
    {
      key: 'title',
      header: '사건',
      render: (i) => (
        <button type="button" className="orch-link" onClick={() => onPick(i.context_id)}>
          {i.title}
        </button>
      ),
    },
    {
      key: 'status',
      header: '상태',
      render: (i) => <Chip className={INCIDENT_STATUS[i.status].chip}>{INCIDENT_STATUS[i.status].label}</Chip>,
    },
    { key: 'opened', header: '시작', numeric: true, render: (i) => clock(i.opened_at) },
    {
      key: 'mttr',
      header: '걸린 시간',
      numeric: true,
      render: (i) => (i.metrics.mttr_seconds === undefined ? '-' : `${i.metrics.mttr_seconds}초`),
    },
  ]
  return (
    <div className="grid two orch-incident">
      <Card title="사건 목록" sub={`${incidents.length}건`}>
        <DataTable
          columns={incidentColumns}
          rows={ordered}
          rowKey={(i) => i.context_id}
          highlight={(i) => i.context_id === current.context_id}
        />
      </Card>
      <Card title={current.title} sub={current.context_id}>
        <div className="orch-meta">
          <Chip className={INCIDENT_STATUS[current.status].chip}>{INCIDENT_STATUS[current.status].label}</Chip>
          <span className="card-sub">
            시작 {clock(current.opened_at)} · 종료 {clock(current.closed_at)}
          </span>
        </div>
        <DataTable columns={columns} rows={current.steps} rowKey={(s) => s.step_id} />
        {current.pending_holds.length > 0 && (
          <Notice tone="warn">
            사람 승인을 기다리는 단계가 있습니다: {current.pending_holds.map((h) => h.label).join(', ')}. 결정은 안전
            관문 보류 큐에서만 합니다.
          </Notice>
        )}
      </Card>
      <Card title="진행 기록" sub="사건 흐름 로그">
        <div className="orch-log">
          {current.events
            .slice()
            .reverse()
            .map((e, i) => (
              <div key={`${e.at}-${i}`}>
                <span className="t">{clock(e.at)}</span>
                {e.message}
              </div>
            ))}
        </div>
      </Card>
      <Card title="사건 요약" sub="부서 결과를 모은 것">
        {current.summary.length > 0 ? (
          <ul className="orch-summary">
            {current.summary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : (
          <UnknownValue label="사건이 끝나면 정리됩니다" />
        )}
      </Card>
    </div>
  )
}

function DeptCard({
  dept,
  selected,
  onSelect,
}: {
  dept: OrchestratorDepartment
  selected: boolean
  onSelect: () => void
}) {
  return (
    <Card onClick={onSelect} className={`orch-dept${selected ? ' selected' : ''}`}>
      <div className="orch-dept-head">
        <div>
          <div className="orch-dept-title">{deptTitle(dept.name)}</div>
          <div className="card-sub">
            {dept.name} · {dept.owner ?? '담당 미확인'}
          </div>
        </div>
        <i className={`orch-dot ${dept.available ? 'ok' : 'bad'}`} aria-label={dept.available ? '정상' : '카드 없음'} />
      </div>
      <div className="orch-dept-foot">
        <Sparkline points={dept.series} />
        <span className="orch-dept-num">
          {dept.usage.calls}
          <small>건/10분</small>
        </span>
      </div>
    </Card>
  )
}

function DeptDetail({ dept, steps }: { dept: OrchestratorDepartment; steps: OrchestratorStep[] }) {
  const clock = useClock()
  const mine = steps.filter((s) => s.dept === dept.name)
  const u = dept.usage
  const skillColumns: Column<OrchestratorDepartment['skills'][number]>[] = [
    { key: 'id', header: 'skill', render: (s) => <b>{s.id}</b> },
    { key: 'grade', header: '등급', render: (s) => <Chip className="orch-grade">{s.grade}</Chip> },
    {
      key: 'calls',
      header: '호출 (10분)',
      render: (s) => (
        <span className="orch-spark-cell">
          <Sparkline points={s.series} width={96} />
          {s.calls}건
        </span>
      ),
    },
    {
      key: 'rate',
      header: '성공률',
      numeric: true,
      render: (s) => (pct(s.success_rate) === null ? <UnknownValue /> : `${pct(s.success_rate)}%`),
    },
    { key: 'ms', header: '평균 응답', numeric: true, render: (s) => (s.avg_ms === null ? '-' : `${s.avg_ms}ms`) },
    { key: 'retries', header: '재시도', numeric: true, render: (s) => s.retries || '' },
  ]
  return (
    <div className="orch-detail">
      <div className="orch-detail-head">
        <div>
          <h2 className="orch-detail-title">
            {deptTitle(dept.name)}{' '}
            <Chip tone={dept.mode === 'real' ? 'green' : 'neutral'}>{dept.mode === 'real' ? '실제' : '목'}</Chip>
          </h2>
          <div className="card-sub">
            {DEPT_LABEL[dept.name]?.desc ?? ''} · 담당 {dept.owner ?? '미확인'}
          </div>
        </div>
        <Chip tone={dept.available ? 'green' : 'amber'}>{dept.available ? '정상' : '카드 없음'}</Chip>
      </div>
      {!dept.available && (
        <Notice tone="warn">
          확인할 수 없음: {dept.unavailable_reason}. 이 부서의 Agent Card 에 skill 이 없으면 총괄은 그 단계를 건너뛰고
          "확인할 수 없음"으로 보고합니다.
        </Notice>
      )}
      <div className="grid kpi">
        <StatCard label="호출 (최근 10분)" value={u.calls} unit="건" />
        <StatCard label="성공률" value={pct(u.success_rate)} unit="%" hint="사람·부서 입력 대기는 뺀 값" />
        <StatCard
          label="평균 응답 · p95"
          value={u.avg_ms}
          unit="ms"
          hint={u.p95_ms === null ? undefined : `p95 ${u.p95_ms}ms`}
        />
        <StatCard label="재시도 · 승인 대기" value={u.retries} unit="회" hint={`승인 대기 ${u.waiting}건`} />
      </div>
      <Card
        title="호출 사용량"
        sub="막대: 30초당 호출 수(빨강=오류) · 선: 평균 응답 시간 · 총괄이 이 부서를 부른 호출을 센 값"
      >
        <UsageChart points={dept.series} />
      </Card>
      <Card title="skill별 사용 현황">
        {dept.skills.length > 0 ? (
          <DataTable columns={skillColumns} rows={dept.skills.filter((s) => s.orchestrator)} rowKey={(s) => s.id} />
        ) : (
          <UnknownValue label="표시할 skill 이 없습니다" />
        )}
      </Card>
      <Card title="이번 사건에서 맡은 일" sub="선택한 사건 기준">
        {mine.length > 0 ? (
          <DataTable columns={stepColumns(clock)} rows={mine} rowKey={(s) => s.step_id} />
        ) : (
          <UnknownValue label="이 부서가 맡은 단계가 없습니다" />
        )}
      </Card>
      <Card title="최근 호출 기록">
        <div className="orch-log">
          {dept.recent.length > 0 ? (
            dept.recent.map((r, i) => (
              <div key={`${r.at}-${i}`}>
                <span className="t">{clock(r.at)}</span>
                <span className={`lv ${r.status === 'completed' ? 'info' : 'warn'}`}>
                  {r.status === 'completed' ? 'INFO' : 'WARN'}
                </span>
                {r.skill} · {r.status}
                {r.outcome ? ` (${r.outcome})` : ''} · {r.duration_ms}ms
              </div>
            ))
          ) : (
            <span className="card-sub">아직 호출이 없습니다</span>
          )}
        </div>
      </Card>
    </div>
  )
}

function DepartmentSection({ depts, steps }: { depts: OrchestratorDepartment[]; steps: OrchestratorStep[] }) {
  const [picked, setPicked] = useState<string | null>(null)
  const current = depts.find((d) => d.name === picked) ?? depts[0]
  if (!current) return <EmptyState title="부서 정보를 확인할 수 없습니다" />
  return (
    <div className="orch-dept-layout">
      <div className="orch-dept-list">
        {depts.map((d) => (
          <DeptCard key={d.name} dept={d} selected={d.name === current.name} onSelect={() => setPicked(d.name)} />
        ))}
      </div>
      <DeptDetail dept={current} steps={steps} />
    </div>
  )
}

export default function Orchestrator() {
  const { role } = useAuth()
  const admin = role === 'admin'
  const incidents = useOrchestratorIncidents(admin)
  const departments = useOrchestratorDepartments(admin)
  const [pickedIncident, setPickedIncident] = useState<string | null>(null)

  if (!admin) {
    return (
      <div className="page">
        <PageHeader title="총괄 에이전트" />
        <EmptyState title="관리자만 볼 수 있습니다" />
      </div>
    )
  }

  const list = incidents.data?.data
  const deptList = departments.data?.data
  const unavailable = incidents.isError || departments.isError
  const mock = incidents.data?.meta.mock || departments.data?.meta.mock
  const done = list?.filter((i) => i.status !== 'open') ?? []
  const resolved = done.filter((i) => i.status === 'resolved').length
  const mttr = done.map((i) => i.metrics.mttr_seconds).filter((v): v is number => typeof v === 'number')
  const auto = done.map((i) => i.metrics.auto_rate).filter((v): v is number => typeof v === 'number')
  const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null)
  const latest = list?.[list.length - 1]
  // 사건을 고르지 않았으면 가장 최근 사건. 사건 흐름과 부서 상세의 '이번 사건에서 맡은 일'이 같은 사건을 본다
  const selected = list?.find((i) => i.context_id === pickedIncident) ?? latest

  return (
    <div className="page">
      <PageHeader
        crumbs={[{ label: '관리자', href: '/admin' }, { label: '총괄 에이전트' }]}
        title="총괄 에이전트"
        sub="DejaFix 장애 대응에서 부서 에이전트들이 한 일을 모아서 보여 줍니다. 읽기 전용이며, 값은 총괄이 기록한 그대로입니다."
      />
      {unavailable && (
        <Notice tone="warn" icon="bell">
          총괄(orchestrator)을 확인할 수 없습니다 · ORCHESTRATOR_UNAVAILABLE. 지어낸 값은 보여 주지 않습니다. 백엔드의
          ORCHESTRATOR_URL 과 총괄 서버를 확인하세요.
        </Notice>
      )}
      {mock && !unavailable && <Notice icon="bell">총괄이 목 모드입니다 (가짜 부서로 돌린 값).</Notice>}

      <div className="grid kpi">
        <StatCard
          label="처리한 사건"
          value={list?.length}
          unit="건"
          hint={latest ? `최근: ${latest.title}` : undefined}
        />
        <StatCard
          label="해결된 사건"
          value={list ? resolved : undefined}
          unit={`/ ${done.length}건`}
          hint="종료된 사건 중 모든 필수 단계가 끝난 것"
        />
        <StatCard
          label="평균 처리 시간"
          value={avg(mttr) === null ? null : Math.round((avg(mttr) as number) * 10) / 10}
          unit="초"
          hint="감지부터 종료까지"
        />
        <StatCard
          label="자동 처리율"
          value={avg(auto) === null ? null : Math.round((avg(auto) as number) * 100)}
          unit="%"
          hint="사람·부서 입력 없이 끝난 단계 비율"
        />
      </div>

      <h2 className="orch-section">사건 흐름</h2>
      {list ? (
        <IncidentSection incidents={list} current={selected} onPick={setPickedIncident} />
      ) : (
        <Card>
          <UnknownValue />
        </Card>
      )}

      <h2 className="orch-section">부서 에이전트</h2>
      {deptList ? (
        <DepartmentSection depts={deptList} steps={selected?.steps ?? []} />
      ) : (
        <Card>
          <UnknownValue />
        </Card>
      )}
    </div>
  )
}
