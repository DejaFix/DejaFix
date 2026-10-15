import type { AuthUser, LoginResult } from './types'

// 인증 API(#1 login, #3 me)만 fetch로 부른다. 나머지 API의 fetch 전환은 api.ts에서 다음 단계에 한다.
export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...init.headers } })
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', '서버에 연결할 수 없습니다')
  }
  const body = (await res.json().catch(() => null)) as { data?: T; error?: { code: string; message: string } } | null
  if (!res.ok || !body || body.data === undefined) {
    throw new ApiError(
      res.status,
      body?.error?.code ?? 'UNKNOWN',
      body?.error?.message ?? `요청에 실패했습니다 (${res.status})`,
    )
  }
  return body.data
}

export const authApi = {
  login: (username: string, password: string) =>
    request<LoginResult>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  me: (token: string) => request<AuthUser>('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } }),
}
