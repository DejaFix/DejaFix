import { apiData } from './http'
import type { AuthUser, LoginResult } from './types'

// 인증 API(#1 login, #3 me). 요청은 공통 래퍼(http.ts)로 보낸다.
// ApiError는 http.ts로 옮겼고, 기존 import(pages/Login.tsx 등)를 위해 여기서도 내보낸다.
export { ApiError } from './http'

export const authApi = {
  // 로그인은 토큰을 붙이지 않고, 401(INVALID_CREDENTIALS)에도 로그아웃 처리를 하지 않는다.
  login: (username: string, password: string) =>
    apiData<LoginResult>('/api/auth/login', { method: 'POST', json: { username, password }, auth: false }),
  // 세션 복원용: 저장 직전 토큰을 직접 넘긴다. 401이면 래퍼가 토큰을 지우고 로그아웃 처리기를 부른다.
  me: (token: string) => apiData<AuthUser>('/api/auth/me', { token }),
}
