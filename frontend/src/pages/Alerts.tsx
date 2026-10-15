import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { DeliveryStatus } from '../lib/types'
import { useAuth } from '../state/auth'
import { Icon } from '../components/Icon'

const statusChip: Record<DeliveryStatus, { cls: string; label: string }> = {
  sent: { cls: 'green', label: '발송됨' },
  failed: { cls: 'high', label: '실패' },
  pending: { cls: 'amber', label: '대기' },
}

export default function Alerts() {
  const rules = useQuery({ queryKey: ['rules'], queryFn: api.notificationRules })
  const logs = useQuery({ queryKey: ['deliveries'], queryFn: api.deliveries })
  const { role } = useAuth()
  const [toggled, setToggled] = useState<Record<string, boolean>>({})
  const canEdit = role !== 'viewer'
  const isOn = (id: string, base: boolean) => toggled[id] ?? base
  const changed = Object.keys(toggled).length > 0

  const count = (s: DeliveryStatus) => (logs.data ?? []).filter((l) => l.status === s).length

  return (
    <div className="page">
      <div className="page-head"><h1 className="page-title">알림</h1><p className="page-sub">누구에게 어떤 장애를 메일로 알릴지 정하고, 보낸 결과를 확인합니다.</p></div>
      <div className="note" style={{ marginBottom: 16 }}><Icon name="bell" size={16} />메일은 Backend가 보냅니다. 이 화면은 설정과 결과만 보여 줍니다. 수신 주소는 예시입니다.</div>

      <section className="card">
        <div className="card-head"><h2 className="card-title">알림 규칙</h2><span className="card-sub">{canEdit ? '켜고 끄면 저장 전까지 이 화면에만 반영됩니다' : '조회자는 규칙을 볼 수만 있습니다'}</span></div>
        {!rules.data ? <div className="skeleton" /> : (
          <div className="list">
            {rules.data.map((r) => (
              <div className="list-row" key={r.id}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="list-title">{r.name}</div>
                  <div className="list-sub">{r.condition} · 받는 사람 <span className="mono">{r.recipients}</span></div>
                </div>
                <button className="switch" role="switch" aria-checked={isOn(r.id, r.enabled)} aria-label={`${r.name} 켜기`} disabled={!canEdit} onClick={() => setToggled((t) => ({ ...t, [r.id]: !isOn(r.id, r.enabled) }))} />
              </div>
            ))}
          </div>
        )}
        <div className="save-bar">
          <button className="btn primary" disabled title="Backend 연결 후 사용할 수 있습니다">저장</button>
          <span className="card-sub">{changed ? '변경한 내용이 있습니다. 저장은 Backend 연결 후 가능합니다.' : '변경한 내용이 없습니다.'}</span>
        </div>
      </section>

      <section className="card">
        <div className="card-head"><h2 className="card-title">발송 내역</h2><span className="card-sub">발송 {count('sent')}건 · 실패 {count('failed')}건 · 대기 {count('pending')}건</span></div>
        {!logs.data ? <div className="skeleton" /> : (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>시각</th><th>규칙</th><th>받는 사람</th><th>결과</th><th>내용</th></tr></thead>
              <tbody>
                {logs.data.map((l) => (
                  <tr key={l.id}>
                    <td className="mono" style={{ whiteSpace: 'nowrap' }}>{l.at}</td>
                    <td>{l.rule}</td>
                    <td className="mono">{l.recipient}</td>
                    <td><span className={`chip ${statusChip[l.status].cls}`}>{statusChip[l.status].label}</span></td>
                    <td>{l.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
