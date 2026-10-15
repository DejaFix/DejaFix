import { delay, http, HttpResponse } from 'msw'
import { dashboardSummary, health, incidentDetails, incidentList, problems } from '../lib/mock'
import type { AuthUser, DashboardSummary, Health, Incident, Measured } from '../lib/types'

// 개발용 목(mock). 응답 형식은 plan.md 7장·노션 요청서 3장: 성공 {data, meta}, 실패 {error:{code, message}}.
// 백엔드 전까지 인증(#1·#3)과 필수 조회 API(#4·#5·#6·#10·#11)를 흉내 낸다. 채팅(#18)은 다음 PR.
// 시드 계정 비밀번호는 목 전용 고정값이다. 실제 비밀번호는 백엔드가 .env DEMO_*_PASSWORD로 만든다.
const MOCK_PASSWORD = 'dejafix'

const users: AuthUser[] = [
  { id: 1, username: 'admin', role: 'admin', display_name: '관리자', email: 'admin@example.com' },
  { id: 2, username: 'oncall', role: 'operator', display_name: '당직자', email: 'oncall@example.com' },
  { id: 3, username: 'viewer', role: 'viewer', display_name: '조회자', email: 'viewer@example.com' },
]

const TOKEN_PREFIX = 'mock-jwt.'

// 개발 중 확인용 시나리오. 페이지를 열 때 주소에 ?scenario=zabbix_down 을 붙이거나 VITE_MOCK_SCENARIO로 켠다.
// 페이지를 다시 불러오기 전까지 유지된다.
// - zabbix_down: health.zabbix='down', #5 호스트 KPI는 unknown(TOOL_ERROR), #6은 503 ZABBIX_UNAVAILABLE
const SCENARIOS = ['normal', 'zabbix_down'] as const
export type MockScenario = (typeof SCENARIOS)[number]
const requested: unknown =
  new URLSearchParams(globalThis.location?.search ?? '').get('scenario') ?? import.meta.env.VITE_MOCK_SCENARIO
const SCENARIO: MockScenario = SCENARIOS.includes(requested as MockScenario) ? (requested as MockScenario) : 'normal'
if (SCENARIO !== 'normal') console.info(`[msw] 목 시나리오: ${SCENARIO}`)

const RESPONSE_DELAY_MS = 150
const now = () => new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')

const error = (status: number, code: string, message: string) =>
  HttpResponse.json({ error: { code, message } }, { status })

const ok = <T, M extends object = Record<string, never>>(data: T, meta?: M) =>
  HttpResponse.json({ data, meta: meta ?? {} })

function userFromRequest(request: Request): AuthUser | null {
  const token = request.headers.get('Authorization')?.replace(/^Bearer\s+/i, '') ?? ''
  if (!token.startsWith(TOKEN_PREFIX)) return null
  return users.find((u) => u.username === token.slice(TOKEN_PREFIX.length)) ?? null
}

const unauthorized = () => error(401, 'UNAUTHORIZED', '로그인이 필요합니다')

// ---- 시나리오별 데이터 ----
function currentHealth(): Health {
  return SCENARIO === 'zabbix_down' ? { ...health, zabbix: 'down' } : health
}

function currentSummary(): DashboardSummary {
  if (SCENARIO !== 'zabbix_down') return dashboardSummary
  const unknownHost = (m: Measured): Measured => ({
    ...m,
    value: null,
    unknown: true,
    unknown_reason: 'TOOL_ERROR',
  })
  // Zabbix가 끊기면 호스트 KPI만 확인할 수 없음, 장애 수는 shared.db 기준이라 그대로(요청서 #5)
  return {
    ...dashboardSummary,
    hosts: {
      ok: unknownHost(dashboardSummary.hosts.ok),
      total: unknownHost(dashboardSummary.hosts.total),
      unknown: unknownHost(dashboardSummary.hosts.unknown),
    },
  }
}

// ---- #10 커서: 목에서는 시작 위치를 base64로 감싼다(실제 형식은 백엔드가 정함) ----
const encodeCursor = (offset: number) => btoa(JSON.stringify({ o: offset }))
function decodeCursor(cursor: string | null): number {
  if (!cursor) return 0
  try {
    const parsed = JSON.parse(atob(cursor)) as { o?: unknown }
    return typeof parsed.o === 'number' && parsed.o >= 0 ? parsed.o : 0
  } catch {
    return 0
  }
}

const intParam = (url: URL, name: string): number | undefined => {
  const raw = url.searchParams.get(name)
  if (raw === null || raw === '') return undefined
  const n = Number(raw)
  return Number.isInteger(n) ? n : undefined
}

export const handlers = [
  // #1 로그인
  http.post('/api/auth/login', async ({ request }) => {
    const body = (await request.json().catch(() => null)) as { username?: string; password?: string } | null
    const user = users.find((u) => u.username === body?.username)
    if (!user || body?.password !== MOCK_PASSWORD) {
      return error(401, 'INVALID_CREDENTIALS', '아이디 또는 비밀번호가 틀렸습니다')
    }
    const { id, username, role, display_name } = user
    return ok({ token: `${TOKEN_PREFIX}${username}`, user: { id, username, role, display_name } })
  }),

  // #3 현재 사용자
  http.get('/api/auth/me', ({ request }) => {
    const user = userFromRequest(request)
    return user ? ok(user) : unauthorized()
  }),

  // #4 연결 상태 — 구성요소가 죽어도 200으로 상태만 알린다(요청서 #4)
  http.get('/api/health', async ({ request }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(RESPONSE_DELAY_MS)
    return ok(currentHealth(), { checked_at: now() })
  }),

  // #5 KPI 4종
  http.get('/api/dashboard/summary', async ({ request }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(RESPONSE_DELAY_MS)
    return ok(currentSummary(), { generated_at: now() })
  }),

  // #6 Zabbix 실시간 문제 (severity_min, hostid)
  http.get('/api/problems', async ({ request }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(RESPONSE_DELAY_MS)
    if (SCENARIO === 'zabbix_down') return error(503, 'ZABBIX_UNAVAILABLE', 'Zabbix에 연결할 수 없습니다')
    const url = new URL(request.url)
    const severityMin = intParam(url, 'severity_min')
    const hostid = url.searchParams.get('hostid')
    const data = problems.filter(
      (p) => (severityMin === undefined || p.severity.level >= severityMin) && (!hostid || p.host.id === hostid),
    )
    return ok(data, { collected_at: now(), truncated: false })
  }),

  // #10 수집된 장애 목록 (status, severity_min, limit, cursor) — started_at 내림차순
  http.get('/api/incidents', async ({ request }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(RESPONSE_DELAY_MS)
    const url = new URL(request.url)
    const status = url.searchParams.get('status')
    const severityMin = intParam(url, 'severity_min')
    const limit = Math.min(Math.max(intParam(url, 'limit') ?? 50, 1), 100)
    const offset = decodeCursor(url.searchParams.get('cursor'))
    const filtered: Incident[] = incidentList
      .filter((i) => (!status || i.status === status) && (severityMin === undefined || i.severity.level >= severityMin))
      .sort((a, b) => b.started_at.localeCompare(a.started_at))
    const page = filtered.slice(offset, offset + limit)
    const next = offset + limit < filtered.length ? encodeCursor(offset + limit) : null
    return ok(page, { next_cursor: next })
  }),

  // #11 장애 상세 — 없으면 404 NOT_FOUND
  http.get('/api/incidents/:id', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(RESPONSE_DELAY_MS)
    const detail = incidentDetails[Number(params.id)]
    return detail ? ok(detail) : error(404, 'NOT_FOUND', '장애를 찾을 수 없습니다')
  }),
]
