import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { AuthContext } from './auth'

const KEY = 'dejafix.user'

function readUser(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

// 목업 로그인: 입력만 있으면 통과한다. 실제 사내 계정 연동은 Backend 인증 API로 교체한다.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null>(readUser)
  const login = useCallback((id: string) => {
    try { localStorage.setItem(KEY, id) } catch { /* 저장 실패해도 세션 내에서는 동작 */ }
    setUser(id)
  }, [])
  const logout = useCallback(() => {
    try { localStorage.removeItem(KEY) } catch { /* 무시 */ }
    setUser(null)
  }, [])
  const value = useMemo(() => ({ user, login, logout }), [user, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
