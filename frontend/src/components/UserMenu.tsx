import { useEffect, useRef, useState } from 'react'

/** 헤더 오른쪽 사용자 칸: 역할(작게) 위에 이름, 누르면 로그아웃 메뉴. */
export function UserMenu({ name, role, onLogout }: { name: string; role: string; onLogout: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <div className="usermenu" ref={ref}>
      <button type="button" className="usermenu-btn" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen((v) => !v)}>
        <span className="user-avatar" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 21c1-4 4-6 8-6s7 2 8 6" />
          </svg>
        </span>
        <span className="user-text">
          <small>{role}</small>
          <b>{name}</b>
        </span>
        <span className="user-caret" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && (
        <div className="usermenu-pop" role="menu">
          <button type="button" role="menuitem" className="btn" onClick={onLogout}>
            로그아웃
          </button>
        </div>
      )}
    </div>
  )
}