import { createContext, useContext } from 'react'
import type { AuthUser, Role } from '../lib/types'

export interface AuthState {
  // restoring: 새로고침 직후 저장된 토큰을 GET /api/auth/me로 확인하는 중
  status: 'restoring' | 'authenticated' | 'anonymous'
  user: AuthUser | null
  // 역할은 로그인·me 응답의 user.role에서만 온다. 로그아웃 상태 기본값은 가장 좁은 viewer.
  role: Role
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (!value) throw new Error('AuthProvider 안에서만 사용할 수 있습니다')
  return value
}
