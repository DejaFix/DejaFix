import { Link } from 'react-router-dom'
import type { ComponentStatus, Health, Incident } from '../lib/types'
import { kstShort } from './incidentFormat'

// 상단 바 상태 요약. 값을 받지 못했으면 추정하지 않고 '확인할 수 없음'으로 표시한다(SAFE-09).

const parts: { key: 'zabbix' | 'agent' | 'mcp_zabbix' | 'shared_db'; label: string }[] = [
  { key: 'zabbix', label: 'Zabbix' },
  { key: 'agent', label: 'Agent' },
  { key: 'mcp_zabbix', label: 'MCP' },
  { key: 'shared_db', label: 'DB' },
]

const STALE_MS = 5 * 60_000 // 수집이 이만큼 멈추면 주의로 올린다

const statusText = (s: ComponentStatus | 'waiting') => (s === 'ok' ? '정상' : s === 'waiting' ? '대기' : '끊김')

const sevName = ['미분류', '정보', '경고', '보통', '높음', '심각']

/** 헤더 왼쪽: 가장 급한 장애 한 건(심각도 높은 순, 같으면 최근 시작). 누르면 그 장애 화면. 목록을 못 받았으면 추정하지 않고 '확인할 수 없음'. */
export function UrgentBanner({ incidents, failed }: { incidents: Incident[] | undefined; failed: boolean }) {
  if (failed || !incidents) {
    return (
      <span className="urgentbar unknown" role="status">
        장애 현황을 확인할 수 없습니다
      </span>
    )
  }
  const top = [...incidents]
    .filter((i) => i.status === 'problem')
    .sort((a, b) => b.severity.level - a.severity.level || Date.parse(b.started_at) - Date.parse(a.started_at))[0]
  if (!top) {
    return (
      <span className="urgentbar calm" role="status">
        지금 급하게 확인할 장애는 없습니다
      </span>
    )
  }
  const urgent = top.severity.level >= 4
  return (
    <Link to={`/incidents/${top.id}`} className={`urgentbar ${urgent ? 'hot' : ''}`} role="status">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M12 3 2.5 20h19L12 3Z" />
        <path d="M12 10v5M12 17.5v.5" />
      </svg>
      <b>
        가장 급한 장애 · {sevName[top.severity.level]}
        {urgent ? ' 즉시 대응' : ''}
      </b>
      <span className="ub-title">
        {top.title}
        {top.host.name ? ` · ${top.host.name}` : ''}
      </span>
      <span className="ub-go" aria-hidden="true">
        ›
      </span>
    </Link>
  )
}
/** 좌측 사이드바 하단에 항상 펼쳐 두는 시스템 상태. 값을 못 받으면 추정하지 않고 '확인할 수 없음'(SAFE-09). */
export function SystemList({ health, checkedAt }: { health: Health | undefined; checkedAt: string | undefined }) {
  if (!health) {
    return (
      <div className="syslist" role="status" aria-label="시스템 상태">
        <div className="syslist-head">시스템 상태</div>
        <div className="syslist-row">
          <span className="syslist-name">연결 상태</span>
          <b className="warn">확인할 수 없음</b>
        </div>
      </div>
    )
  }
  const lastOk = health.scheduler_last_ok
  const lastMs = lastOk ? Date.parse(lastOk) : NaN
  const nowMs = checkedAt ? Date.parse(checkedAt) : NaN
  const stale = Number.isFinite(lastMs) && Number.isFinite(nowMs) && nowMs - lastMs > STALE_MS
  const tone = (s: ComponentStatus | 'waiting') => (s === 'ok' ? 'ok' : s === 'waiting' ? 'warn' : 'bad')
  return (
    <div className="syslist" role="status" aria-label="시스템 상태">
      <div className="syslist-head">시스템 상태</div>
      {parts.map((p) => (
        <div className="syslist-row" key={p.key}>
          <span className="syslist-name">
            <i className={`dot ${tone(health[p.key])}`} />
            {p.label}
          </span>
          <b className={tone(health[p.key])}>{statusText(health[p.key])}</b>
        </div>
      ))}
      <div className="syslist-row">
        <span className="syslist-name">
          <i className={`dot ${stale || !lastOk ? 'warn' : 'ok'}`} />
          수집
        </span>
        <b className={stale || !lastOk ? 'warn' : 'plain'}>{stale ? '지연' : (kstShort(lastOk)?.slice(-5) ?? '확인할 수 없음')}</b>
      </div>
      {checkedAt && <div className="syslist-foot">확인 {kstShort(checkedAt) ?? '—'} (KST)</div>}
    </div>
  )
}