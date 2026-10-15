import type { AuthUser } from './types'

// 브라우저 저장소는 이 파일에서만 다룬다. JWT는 sessionStorage(탭을 닫으면 삭제)에만 둔다. 영구 저장소에는 두지 않는다.
const KEY = 'dejafix.auth'
// 목업 시절 영구 저장소에 남은 세션 키. 앱 시작 시 한 번 지운다(clearLegacy).
const LEGACY_KEYS = ['dejafix.user', 'dejafix.session']

export interface StoredAuth {
  token: string
  user: AuthUser
}

export const tokenStorage = {
  get(): StoredAuth | null {
    try {
      const raw = sessionStorage.getItem(KEY)
      if (!raw) return null
      const parsed = JSON.parse(raw) as Partial<StoredAuth>
      return typeof parsed.token === 'string' && parsed.user ? (parsed as StoredAuth) : null
    } catch {
      return null
    }
  },
  set(value: StoredAuth): void {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(value))
    } catch {
      /* 저장 실패해도 이 탭의 메모리 세션으로는 동작 */
    }
  },
  clear(): void {
    try {
      sessionStorage.removeItem(KEY)
    } catch {
      /* 무시 */
    }
  },
  clearLegacy(): void {
    try {
      // 예전 목업 키 정리용, 데모 후 삭제
      for (const key of LEGACY_KEYS) localStorage.removeItem(key)
    } catch {
      /* 무시 */
    }
  },
}
