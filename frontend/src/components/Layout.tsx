import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { roleLabel } from '../lib/format'
import { useHealth, useIncidents } from '../lib/queries'
import { useAssistant } from '../state/assistant'
import { useAuth } from '../state/auth'
import { usePrefs } from '../state/prefs'
import { AssistantPanel } from './AssistantPanel'
import { ConnectionStatus, ZabbixBanner } from './ConnectionStatus'
import { Icon, type IconName } from './Icon'
import { kstShort } from './incidentFormat'

interface NavDef {
  to: string
  label: string
  icon: IconName
  badge?: number
  end?: boolean
  adminOnly?: boolean
}

const nav: NavDef[] = [
  { to: '/', label: '현황 · 장애 대응', icon: 'dashboard', badge: 4, end: true },
  { to: '/cost', label: '비용 절감', icon: 'cost' },
  { to: '/compare', label: '서버 비교', icon: 'compare' },
  { to: '/reports', label: '리포트', icon: 'report' },
  { to: '/plans', label: '변경 계획', icon: 'plan', badge: 2 },
  { to: '/alerts', label: '알림', icon: 'bell' },
  { to: '/admin', label: '관리자', icon: 'admin', adminOnly: true },
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
  const baseTime = checkedAt ? (tz === 'KST' ? kstShort(checkedAt) : checkedAt.slice(5, 16).replace('T', ' ')) : null
  const items = nav.filter((n) => !n.adminOnly || role === 'admin')

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
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <Icon name="logo" size={18} />
          </span>
          <span>
            DejaFix
            <small className="brand-sub">Zabbix AI</small>
          </span>
        </div>
        {items.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <Icon name={n.icon} />
            {n.label}
            {n.badge ? <span className="nav-badge">{n.badge}</span> : null}
          </NavLink>
        ))}
        <div className="sidebar-foot">
          조회 전용 · Zabbix에 쓰지 않음
          <br />
          (변경 계획은 승인까지만)
          <br />
          <br />
          {user?.display_name ?? user?.username} · {roleLabel[role]}
        </div>
      </aside>
      <div className={`main ${open ? 'panel-open' : ''}`}>
        <header className="topbar">
          <span className="topbar-time">{baseTime ? `확인 ${baseTime}` : '확인 시각 확인할 수 없음'}</span>
          <ConnectionStatus health={health.data?.data} />
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
          <button className="btn dark" onClick={() => setOpen(!open)}>
            <Icon name="sparkle" size={16} />
            AI 어시스턴트
          </button>
          <button className="btn" onClick={logout}>
            로그아웃
          </button>
        </header>
        <nav className="mobile-nav" aria-label="메뉴">
          {items.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {n.label}
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
