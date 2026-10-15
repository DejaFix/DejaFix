import { http, HttpResponse } from 'msw'
import type { AuthUser } from '../lib/types'

// 개발용 목(mock): 백엔드 전까지 인증 API(#1 login, #3 me)만 흉내 낸다. 응답 형식은 plan.md 7-1.
// 시드 계정 비밀번호는 목 전용 고정값이다. 실제 비밀번호는 백엔드가 .env DEMO_*_PASSWORD로 만든다.
const MOCK_PASSWORD = 'dejafix'

const users: AuthUser[] = [
  { id: 1, username: 'admin', role: 'admin', display_name: '관리자', email: 'admin@example.com' },
  { id: 2, username: 'oncall', role: 'operator', display_name: '당직자', email: 'oncall@example.com' },
  { id: 3, username: 'viewer', role: 'viewer', display_name: '조회자', email: 'viewer@example.com' },
]

const TOKEN_PREFIX = 'mock-jwt.'
const error = (status: number, code: string, message: string) =>
  HttpResponse.json({ error: { code, message } }, { status })

export const handlers = [
  http.post('/api/auth/login', async ({ request }) => {
    const body = (await request.json().catch(() => null)) as { username?: string; password?: string } | null
    const user = users.find((u) => u.username === body?.username)
    if (!user || body?.password !== MOCK_PASSWORD) {
      return error(401, 'INVALID_CREDENTIALS', '아이디 또는 비밀번호가 틀렸습니다')
    }
    const { id, username, role, display_name } = user
    return HttpResponse.json({
      data: { token: `${TOKEN_PREFIX}${username}`, user: { id, username, role, display_name } },
      meta: {},
    })
  }),

  http.get('/api/auth/me', ({ request }) => {
    const token = request.headers.get('Authorization')?.replace(/^Bearer\s+/i, '') ?? ''
    const user = token.startsWith(TOKEN_PREFIX)
      ? users.find((u) => u.username === token.slice(TOKEN_PREFIX.length))
      : null
    if (!user) return error(401, 'UNAUTHORIZED', '로그인이 필요합니다')
    return HttpResponse.json({ data: user, meta: {} })
  }),
]
