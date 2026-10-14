import { useMemo, useState, type ReactNode } from 'react'
import { PrefsContext, type Tz } from './prefs'

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [tz, setTz] = useState<Tz>('KST')
  const value = useMemo(() => ({ tz, setTz }), [tz])
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>
}
