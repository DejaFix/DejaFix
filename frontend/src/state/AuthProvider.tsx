import { useCallback, useMemo, useState, type ReactNode } from 'react'
import type { Role } from '../lib/types'
import { AuthContext } from './auth'

const KEY = 'dejafix.session'
interface Session {
  id: string
  role: Role
}

function readSession(): Session | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}

// 목업 로그인: 입력만 있으면 통과한다. 실제 사내 계정·권한은 Backend 인증 API로 교체한다.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(readSession)
  const login = useCallback((id: string, role: Role) => {
    const next = { id, role }
    try {
      localStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      /* 저장 실패해도 세션 내에서는 동작 */
    }
    setSession(next)
  }, [])
  const logout = useCallback(() => {
    try {
      localStorage.removeItem(KEY)
    } catch {
      /* 무시 */
    }
    setSession(null)
  }, [])
  const value = useMemo(
    () => ({ user: session?.id ?? null, role: session?.role ?? 'viewer', login, logout }),
    [session, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
