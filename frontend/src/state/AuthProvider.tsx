import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, authApi } from '../lib/authApi'
import { setUnauthorizedHandler } from '../lib/http'
import { tokenStorage, type StoredAuth } from '../lib/tokenStorage'
import { AuthContext, type AuthState } from './auth'

// 로그인: POST /api/auth/login → {token, user} 저장. 새로고침: 저장된 토큰으로 GET /api/auth/me 복원.
// 401이면 토큰을 지우고 로그아웃 상태로 둔다(RequireAuth가 /login으로 보냄).
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<StoredAuth | null>(() => tokenStorage.get())
  const [status, setStatus] = useState<AuthState['status']>(() => (tokenStorage.get() ? 'restoring' : 'anonymous'))

  useEffect(() => {
    const stored = tokenStorage.get()
    if (!stored) return
    let cancelled = false
    authApi
      .me(stored.token)
      .then((user) => {
        if (cancelled) return
        const next = { token: stored.token, user }
        tokenStorage.set(next)
        setSession(next)
        setStatus('authenticated')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          tokenStorage.clear()
          setSession(null)
          setStatus('anonymous')
          return
        }
        // 서버에 일시적으로 닿지 않을 때는 저장된 세션을 유지한다. 토큰이 무효면 이후 API의 401에서 정리된다.
        setStatus('authenticated')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const next = await authApi.login(username, password)
    tokenStorage.set(next)
    setSession(next)
    setStatus('authenticated')
  }, [])

  const queryClient = useQueryClient()
  const logout = useCallback(() => {
    tokenStorage.clear()
    setSession(null)
    setStatus('anonymous')
    // 다음 사용자에게 이전 사용자의 화면 데이터가 보이지 않게 캐시를 비운다.
    queryClient.clear()
  }, [queryClient])

  // 어떤 API든 401이 나면(토큰 만료·무효) 공통 래퍼가 토큰을 지우고 여기로 알린다 → RequireAuth가 /login으로 보냄.
  useEffect(() => {
    setUnauthorizedHandler(logout)
    return () => setUnauthorizedHandler(null)
  }, [logout])

  const value = useMemo<AuthState>(
    () => ({
      status,
      user: status === 'anonymous' ? null : (session?.user ?? null),
      role: (status === 'anonymous' ? null : session?.user.role) ?? 'viewer',
      login,
      logout,
    }),
    [status, session, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
