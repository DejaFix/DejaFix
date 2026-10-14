import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { alerts, BASE_TIME_KST, oldAlerts } from '../lib/mock'
import { toUtc } from '../lib/format'
import { useAssistant } from '../state/assistant'
import { useAuth } from '../state/auth'
import { usePrefs } from '../state/prefs'
import { AssistantPanel } from './AssistantPanel'
import { Icon, type IconName } from './Icon'

const nav: { to: string; label: string; icon: IconName; badge?: number; end?: boolean }[] = [
  { to: '/', label: '현황 · 장애 대응', icon: 'dashboard', badge: 4, end: true },
  { to: '/cost', label: '비용 절감', icon: 'cost' },
  { to: '/compare', label: '서버 비교', icon: 'compare' },
  { to: '/reports', label: '리포트', icon: 'report' },
  { to: '/plans', label: '변경 계획', icon: 'plan', badge: 2 },
  { to: '/alerts', label: '알림', icon: 'bell' },
  { to: '/admin', label: '관리자', icon: 'admin' },
]

export function Layout() {
  const { open, setOpen } = useAssistant()
  const { logout, user } = useAuth()
  const { tz, setTz } = usePrefs()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); searchRef.current?.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const onSearch = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter' || !query.trim()) return
    const q = query.trim().toLowerCase()
    const hit = [...alerts, ...oldAlerts].find((a) => a.host.toLowerCase().includes(q) || a.name.toLowerCase().includes(q))
    if (hit && hit.group === 'new') navigate(`/incidents/${hit.id}`)
    else window.alert(hit ? '이 장애는 상세 화면이 아직 없습니다.' : '일치하는 호스트·장애를 찾지 못했습니다.')
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 16l4-9 3 6 2-4 5 7" /></svg></span>DejaFix</div>
        {nav.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Icon name={n.icon} />{n.label}{n.badge ? <span className="nav-badge">{n.badge}</span> : null}
          </NavLink>
        ))}
        <div className="sidebar-foot">조회 전용 · Zabbix에 쓰지 않음<br />(변경 계획은 승인까지만)<br /><br />{user}</div>
      </aside>
      <div className={`main ${open ? 'panel-open' : ''}`}>
        <header className="topbar">
          <span className="topbar-time">기준 {tz === 'KST' ? BASE_TIME_KST : toUtc(BASE_TIME_KST)}</span>
          <div className="seg" role="group" aria-label="시간대">
            {(['KST', 'UTC'] as const).map((z) => <button key={z} className={tz === z ? 'on' : ''} onClick={() => setTz(z)}>{z}</button>)}
          </div>
          <span className="mock-chip">목업 데이터</span>
          <label className="search">
            <Icon name="search" size={16} />
            <input ref={searchRef} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onSearch} placeholder="호스트 · 그룹 · 장애 찾기" aria-label="검색" />
            <span className="kbd">Ctrl K</span>
          </label>
          <button className="btn dark" onClick={() => setOpen(!open)}><Icon name="sparkle" size={16} />AI 어시스턴트</button>
          <button className="btn" onClick={logout}>로그아웃</button>
        </header>
        <Outlet />
      </div>
      <AssistantPanel />
    </div>
  )
}
