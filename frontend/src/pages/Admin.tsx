import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { roleLabel } from '../lib/format'
import type { Role } from '../lib/types'
import { useAuth } from '../state/auth'
import { Icon } from '../components/Icon'

const perms: [string, boolean, boolean, boolean][] = [
  ['현황·장애 조회', true, true, true],
  ['AI 어시스턴트에 질문', true, true, true],
  ['비용 절감 보기', true, true, true],
  ['변경 계획 검토(승인)', true, true, false],
  ['알림 규칙 변경', true, true, false],
  ['사용자·권한 관리', true, false, false],
]

export default function Admin() {
  const { role } = useAuth()
  const users = useQuery({ queryKey: ['users'], queryFn: api.users, enabled: role === 'admin' })
  const [roles, setRoles] = useState<Record<string, Role>>({})
  const [active, setActive] = useState<Record<string, boolean>>({})

  if (role !== 'admin') {
    return (
      <div className="page">
        <div className="page-head"><h1 className="page-title">관리자</h1></div>
        <div className="card empty"><div style={{ marginBottom: 12 }}><Icon name="admin" size={32} /></div><h2>관리자만 볼 수 있습니다</h2><p>사용자와 권한은 관리자 역할로 로그인했을 때만 열립니다.</p></div>
      </div>
    )
  }

  const mark = (v: boolean) => (v ? <span className="perm-yes">가능</span> : <span className="perm-no">불가</span>)

  return (
    <div className="page">
      <div className="page-head"><h1 className="page-title">관리자</h1><p className="page-sub">사용자의 역할과 상태를 확인합니다.</p></div>
      <div className="note warn" style={{ marginBottom: 16 }}><Icon name="admin" size={16} />역할과 상태 변경은 이 화면에서만 반영되는 목업입니다. 실제 변경은 Backend 인증 API 연결 후 가능합니다.</div>

      <section className="card">
        <div className="card-head"><h2 className="card-title">사용자</h2><span className="card-sub">{users.data?.length ?? 0}명</span></div>
        {!users.data ? <div className="skeleton" /> : (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>이름</th><th>아이디</th><th>역할</th><th>마지막 접속</th><th>상태</th></tr></thead>
              <tbody>
                {users.data.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 600 }}>{u.name}</td>
                    <td className="mono">{u.id}</td>
                    <td>
                      <select className="select" aria-label={`${u.name} 역할`} value={roles[u.id] ?? u.role} onChange={(e) => setRoles((r) => ({ ...r, [u.id]: e.target.value as Role }))}>
                        {(Object.keys(roleLabel) as Role[]).map((r) => <option key={r} value={r}>{roleLabel[r]}</option>)}
                      </select>
                    </td>
                    <td className="mono" style={{ whiteSpace: 'nowrap' }}>{u.lastLogin}</td>
                    <td><button className="switch" role="switch" aria-checked={active[u.id] ?? u.active} aria-label={`${u.name} 사용`} onClick={() => setActive((a) => ({ ...a, [u.id]: !(a[u.id] ?? u.active) }))} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-head"><h2 className="card-title">역할별 권한</h2></div>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>기능</th><th>{roleLabel.admin}</th><th>{roleLabel.operator}</th><th>{roleLabel.viewer}</th></tr></thead>
            <tbody>{perms.map(([name, a, o, v]) => <tr key={name}><td>{name}</td><td>{mark(a)}</td><td>{mark(o)}</td><td>{mark(v)}</td></tr>)}</tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
