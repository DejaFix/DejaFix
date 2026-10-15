import { createContext, useContext } from 'react'

export type Tz = 'KST' | 'UTC'
export interface Prefs {
  tz: Tz
  setTz: (tz: Tz) => void
}

export const PrefsContext = createContext<Prefs | null>(null)

export function usePrefs(): Prefs {
  const value = useContext(PrefsContext)
  if (!value) throw new Error('PrefsProvider 안에서만 사용할 수 있습니다')
  return value
}
