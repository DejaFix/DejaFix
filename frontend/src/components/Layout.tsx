import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { roleLabel } from '../lib/format'
import { useHealth, useIncidents } from '../lib/queries'
import { useAssistant } from '../state/assistant'
import { useAuth } from '../state/auth'
import { usePrefs } from '../state/prefs'
import { AssistantPanel } from './AssistantPanel'
import { ZabbixBanner } from './ConnectionStatus'
import { SystemList, UrgentBanner } from './TopStatus'
import { UserMenu } from './UserMenu'
import { Icon, type IconName } from './Icon'

interface NavDef {
  to: string
  label: string
  icon: IconName
  end?: boolean
  adminOnly?: boolean
  soon?: boolean // L1 예정 메뉴: '준비 중' 표시(FR-FE-013)
  sub?: boolean // 위 메뉴 아래에 들여 쓴 하위 메뉴(관리자 > 총괄 에이전트)
}

const nav: NavDef[] = [
  { to: '/', label: '현황 · 장애 대응', icon: 'dashboard', end: true },
  { to: '/cost', label: '비용 절감', icon: 'cost', soon: true },
  { to: '/compare', label: '서버 비교', icon: 'compare', soon: true },
  { to: '/reports', label: '리포트', icon: 'report' },
  { to: '/plans', label: '변경 계획', icon: 'plan' },
  { to: '/alerts', label: '알림', icon: 'bell' },
  { to: '/admin', label: '관리자', icon: 'admin', end: true, adminOnly: true },
  { to: '/admin/orchestrator', label: '총괄 에이전트', icon: 'agent', adminOnly: true, sub: true },
]

export function Layout() {
  const { open, setOpen } = useAssistant()
  const { logout, user, role } = useAuth()
  const { tz, setTz } = usePrefs()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const health = useHealth()
  const incidents = useIncidents({ limit: 50 })
  const checkedAt = health.data?.meta.checked_at
  // 현황 배지: 진행 중 장애 건수. 목록을 다 받지 못했으면 '+'를 붙이고, 못 받았거나 갱신에 실패했으면 숨긴다(오래된 숫자 금지, SAFE-09).
  const openIncidents = useIncidents({ status: 'problem', limit: 100 })
  const openCount = openIncidents.isError ? undefined : openIncidents.data?.data.length
  const openBadge = openCount ? `${openCount}${openIncidents.data?.meta.next_cursor ? '+' : ''}` : null
  const items = nav.filter((n) => !n.adminOnly || role === 'admin')
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem('dejafix.sidebar') === 'collapsed'
    } catch {
      return false
    }
  })
  const toggleSidebar = () =>
    setCollapsed((v) => {
      try {
        localStorage.setItem('dejafix.sidebar', v ? 'open' : 'collapsed')
      } catch {
        /* 저장이 막혀도 화면은 동작한다 */
      }
      return !v
    })

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (!message) return
    const t = setTimeout(() => setMessage(''), 3000)
    return () => clearTimeout(t)
  }, [message])

  const onSearch = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter' || !query.trim()) return
    const q = query.trim().toLowerCase()
    const hit = incidents.data?.data.find(
      (i) => (i.host.name ?? '').toLowerCase().includes(q) || i.title.toLowerCase().includes(q),
    )
    if (hit) navigate(`/incidents/${hit.id}`)
    else setMessage('일치하는 호스트·장애가 없습니다')
  }

  return (
    <div className={`shell${collapsed ? ' collapsed' : ''}`}>
      <aside className="sidebar">
        <div className="side-top">
          <button
            type="button"
            className="hamburger"
            aria-label={collapsed ? '메뉴 펼치기' : '메뉴 접기'}
            aria-expanded={!collapsed}
            onClick={toggleSidebar}
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <img className="brand-logo" src="/logo-mark.png" alt="" width={32} height={32} />
          <span className="brand-name">DejaFix</span>
        </div>
        {items.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) => `nav-item ${n.sub ? 'sub' : ''} ${isActive ? 'active' : ''}`}
          >
            <Icon name={n.icon} />
            <span className="nav-label">{n.label}</span>
            {n.soon ? <span className="nav-soon">준비 중</span> : null}
            {n.to === '/' && openBadge ? <span className="nav-badge">{openBadge}</span> : null}
          </NavLink>
        ))}
        <SystemList health={health.data?.data} checkedAt={checkedAt} />
      </aside>
      <div className={`main ${open ? 'panel-open' : ''}`}>
        <header className="topbar">
          <UrgentBanner
            incidents={openIncidents.isError ? undefined : openIncidents.data?.data}
            failed={openIncidents.isError}
          />
          <div className="seg" role="group" aria-label="시간대">
            {(['KST', 'UTC'] as const).map((z) => (
              <button key={z} className={tz === z ? 'on' : ''} onClick={() => setTz(z)}>
                {z}
              </button>
            ))}
          </div>
          {import.meta.env.DEV && import.meta.env.VITE_MSW !== 'off' && <span className="mock-chip">목업 데이터</span>}
          {message && (
            <span className="toast" role="status">
              {message}
            </span>
          )}
          <label className="search">
            <Icon name="search" size={16} />
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onSearch}
              placeholder="호스트 · 그룹 · 장애 찾기"
              aria-label="검색"
            />
            <span className="kbd">Ctrl K</span>
          </label>
          <UserMenu name={user?.display_name ?? user?.username ?? ''} role={roleLabel[role]} onLogout={logout} />
          <NavLink to="/alerts" className="bell" aria-label="알림">
            <Icon name="bell" size={20} />
            {openCount ? <i className="bell-dot" /> : null}
          </NavLink>
          <button className="btn dark" onClick={() => setOpen(!open)}>
            <Icon name="sparkle" size={16} />
            AI 어시스턴트
          </button>
        </header>
        <nav className="mobile-nav" aria-label="메뉴">
          {items.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {n.label}
              {n.soon ? ' (준비 중)' : ''}
            </NavLink>
          ))}
        </nav>
        <ZabbixBanner health={health.data?.data} />
        <Outlet />
      </div>
      <AssistantPanel />
    </div>
  )
}
