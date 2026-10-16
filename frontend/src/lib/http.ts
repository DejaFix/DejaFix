import { tokenStorage } from './tokenStorage'
import type { ApiErrorBody, ApiResponse } from './types'

// 모든 /api 호출의 공통 fetch 래퍼 (plan.md 7장 공통 규칙).
// - 토큰은 tokenStorage에서 꺼내 Authorization: Bearer로 붙인다.
// - 성공 응답 {data, meta}를 그대로 돌려주고, 실패는 {error:{code,message}}를 ApiError로 던진다.
// - 인증이 필요한 요청이 401이면 토큰을 지우고 로그아웃 처리기를 부른다(AuthProvider가 /login으로 보냄).
export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

type UnauthorizedHandler = () => void
let onUnauthorized: UnauthorizedHandler | null = null

/** 401을 받았을 때 부를 처리기. AuthProvider가 로그아웃(상태 초기화 → /login)을 등록한다. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler
}

/** 인증이 필요한 요청이 401을 받았을 때 토큰을 지우고 로그아웃한다. 채팅 스트림(lib/chat.ts)도 쓴다. */
export function handleUnauthorized(): void {
  // 여러 요청이 동시에 401을 받아도 로그아웃은 한 번만: 이미 토큰이 지워졌으면 아무것도 하지 않는다.
  if (!tokenStorage.get()) return
  tokenStorage.clear()
  if (onUnauthorized) {
    onUnauthorized()
    return
  }
  // 처리기가 없을 때(AuthProvider 밖)만 직접 이동한다.
  window.location.assign(import.meta.env.VITE_ROUTER === 'hash' ? '#/login' : '/login')
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  /** JSON으로 보낼 본문 */
  json?: unknown
  /** 쿼리 문자열. undefined·null·빈 문자열 값은 빠진다 */
  query?: Record<string, string | number | null | undefined>
  /** false면 토큰을 붙이지 않고 401에도 로그아웃하지 않는다(로그인 요청용). 기본 true */
  auth?: boolean
  /** 저장된 토큰 대신 쓸 토큰(세션 복원 시 me 호출용) */
  token?: string
}

function withQuery(path: string, query?: RequestOptions['query']): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

export async function apiRequest<T, M = Record<string, unknown>>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResponse<T, M>> {
  const { json, query, auth = true, token, headers, ...init } = options
  const finalHeaders = new Headers(headers)
  if (json !== undefined) finalHeaders.set('Content-Type', 'application/json')
  const bearer = token ?? (auth ? tokenStorage.get()?.token : undefined)
  // 인증이 필요한데 토큰이 없으면(이미 로그아웃됨) 요청을 보내지 않는다.
  // 401 직후 아직 내려가지 않은 폴링 훅이 토큰 없는 요청을 반복하지 않게 하고, 로그아웃 처리기도 다시 부르지 않는다.
  if (auth && !bearer) throw new ApiError(401, 'UNAUTHORIZED', '로그인이 필요합니다')
  if (bearer) finalHeaders.set('Authorization', `Bearer ${bearer}`)

  let res: Response
  try {
    res = await fetch(withQuery(path, query), {
      ...init,
      headers: finalHeaders,
      body: json !== undefined ? JSON.stringify(json) : undefined,
    })
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', '서버에 연결할 수 없습니다')
  }

  const body = (await res.json().catch(() => null)) as (Partial<ApiResponse<T, M>> & Partial<ApiErrorBody>) | null
  if (!res.ok || !body || body.data === undefined) {
    if (res.status === 401 && auth) handleUnauthorized()
    throw new ApiError(
      res.status,
      body?.error?.code ?? 'UNKNOWN',
      body?.error?.message ?? `요청에 실패했습니다 (${res.status})`,
    )
  }
  return { data: body.data, meta: (body.meta ?? {}) as M }
}

/** 봉투에서 data만 필요할 때 */
export async function apiData<T>(path: string, options?: RequestOptions): Promise<T> {
  return (await apiRequest<T>(path, options)).data
}
