import { createContext, useContext } from 'react'
import type { Role } from '../lib/types'

export interface AuthState {
  user: string | null
  role: Role
  login: (id: string, role: Role) => void
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (!value) throw new Error('AuthProvider 안에서만 사용할 수 있습니다')
  return value
}
