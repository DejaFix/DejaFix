import type { ComponentStatus, Health } from '../lib/types'
import { kstShort } from './incidentFormat'

// 상단 연결 상태(#4). 값을 받지 못했으면(health가 undefined) 추정하지 않고 '확인할 수 없음'으로 표시한다(SAFE-09).
const parts: { key: 'zabbix' | 'agent' | 'mcp_zabbix' | 'shared_db'; label: string }[] = [
  { key: 'zabbix', label: 'Zabbix' },
  { key: 'agent', label: 'Agent' },
  { key: 'mcp_zabbix', label: 'MCP' },
  { key: 'shared_db', label: 'DB' },
]

const cls = (s: ComponentStatus | 'waiting') => (s === 'ok' ? 'green' : s === 'waiting' ? 'amber' : 'riskhigh')
const text = (s: ComponentStatus | 'waiting') => (s === 'ok' ? '정상' : s === 'waiting' ? '대기' : '끊김')

export function ConnectionStatus({ health }: { health: Health | undefined }) {
  if (!health) return <span className="chip neutral">연결 상태 확인할 수 없음</span>
  return (
    <span className="chips" role="status" aria-label="연결 상태">
      {parts.map((p) => (
        <span key={p.key} className={`chip ${cls(health[p.key])}`}>
          {p.label} {text(health[p.key])}
        </span>
      ))}
      <SchedulerChip lastOk={health.scheduler_last_ok} />
    </span>
  )
}

// Scheduler 마지막 수집 시각(NFR-OBS-004). 기록이 없거나 해석할 수 없으면 지어내지 않고 '확인할 수 없음'(SAFE-09·10).
function SchedulerChip({ lastOk }: { lastOk: string | null | undefined }) {
  const t = kstShort(lastOk)
  return t ? (
    <span className="chip neutral" title="Scheduler 마지막 수집 시각(KST)">
      수집 {t}
    </span>
  ) : (
    <span className="chip neutral">수집 확인할 수 없음</span>
  )
}

/** Zabbix가 down이면 15초 폴링 안에 뜨는 경고 배너(FR-FE-002). */
export function ZabbixBanner({ health }: { health: Health | undefined }) {
  if (health?.zabbix !== 'down') return null
  return (
    <div className="note warn" role="alert" style={{ margin: '12px 24px 0' }}>
      Zabbix 연결이 끊겼습니다. 실시간 값은 확인할 수 없고, 저장된 장애와 리포트만 볼 수 있습니다.
    </div>
  )
}
