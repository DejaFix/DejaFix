import { delay, http, HttpResponse, type HttpHandler } from 'msw'
import { dashboardSummary, health, incidentDetails, incidentList, problems } from '../lib/mock'
import type { AuthUser, ChatEvent, DashboardSummary, Health, Incident, Measured } from '../lib/types'
import { passthroughGroups, type ApiGroup } from './passthrough'

// 개발용 목(mock). 응답 형식은 plan.md 7장·노션 요청서 3장: 성공 {data, meta}, 실패 {error:{code, message}}.
// 필수 API 8개(#1·#3·#4·#5·#6·#10·#11·#18)를 흉내 낸다. 묶음별로 실제 백엔드에 넘기려면 passthrough.ts 참고.
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
// - agent_down: health.agent='down', #18 채팅은 error 이벤트 AGENT_UNAVAILABLE(실제 백엔드가 Agent 없이 주는 응답과 같음)
// - stale: health.scheduler='stale', #10 meta.stale=true(수집 지연 배너 확인용, 기본은 정상 ok·stale=false)
const SCENARIOS = ['normal', 'zabbix_down', 'agent_down', 'stale'] as const
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

/** 실제 백엔드 JWT의 role만 읽는다(서명 검증 없음 — 개발용 목이 역할을 흉내 내기 위한 것). */
function roleFromJwt(token: string): AuthUser['role'] | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))) as { role?: unknown }
    return users.some((u) => u.role === payload.role) ? (payload.role as AuthUser['role']) : null
  } catch {
    return null
  }
}

function userFromRequest(request: Request): AuthUser | null {
  const token = request.headers.get('Authorization')?.replace(/^Bearer\s+/i, '') ?? ''
  if (token.startsWith(TOKEN_PREFIX)) return users.find((u) => u.username === token.slice(TOKEN_PREFIX.length)) ?? null
  // 로그인만 실제 백엔드로 통과시킨 경우(VITE_MSW_PASSTHROUGH=auth,…): 나머지 목 API는 실제 토큰의 역할로 응답한다.
  if (token && passthroughGroups.has('auth')) {
    const role = roleFromJwt(token)
    return users.find((u) => u.role === role) ?? null
  }
  return null
}

const unauthorized = () => error(401, 'UNAUTHORIZED', '로그인이 필요합니다')

// ---- 시나리오별 데이터 ----
const STALE_AS_OF = '2026-10-16T01:10:00Z' // 지연 시나리오의 마지막 수집 성공 시각
const NORMAL_AS_OF = health.scheduler_last_ok
function currentHealth(): Health {
  if (SCENARIO === 'zabbix_down') return { ...health, zabbix: 'down' }
  if (SCENARIO === 'agent_down') return { ...health, agent: 'down' }
  if (SCENARIO === 'stale') return { ...health, scheduler: 'stale', scheduler_last_ok: STALE_AS_OF }
  return health
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

// ---- #18 채팅 스트림: agent-api.md 1장 SSE 이벤트 순서(meta → tool_call/tool_result → token → final) ----
const TOKEN_DELAY_MS = 40
const sseFrame = (e: ChatEvent) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`

function mockChatEvents(message: string, incidentId: number | undefined): ChatEvent[] {
  if (SCENARIO === 'agent_down') {
    return [{ event: 'error', data: { code: 'AGENT_UNAVAILABLE', message: 'Agent에 연결할 수 없습니다' } }]
  }
  const head: ChatEvent = {
    event: 'meta',
    data: { conversation_id: 'mock-conv-1', run_id: 'mock-run-1', message_id: 1 },
  }
  // 데모 D-UNKNOWN: 수집하지 않는 정보를 물으면 지어내지 않고 "확인할 수 없음 · NOT_COLLECTED"
  if (message.includes('백업')) {
    const content =
      '백업 작업 여부는 수집하지 않는 정보라 원인인지 확인할 수 없습니다. 백업 스케줄을 직접 확인해 주세요.'
    return [
      head,
      ...content.match(/.{1,12}/gsu)!.map((text): ChatEvent => ({ event: 'token', data: { text } })),
      {
        event: 'final',
        data: {
          message_id: 1,
          content,
          evidence_ids: [],
          unknowns: [{ label: '백업 작업 여부', reason: 'NOT_COLLECTED' }],
        },
      },
    ]
  }
  const target = incidentId ? `장애 #${incidentId}` : '현재 활성 장애'
  const content = `${target} 기준으로 최근 Problem을 조회했습니다. 자세한 원인 후보는 장애 상세의 분석 리포트를 확인해 주세요. (목 응답)`
  const called = now()
  return [
    head,
    {
      event: 'tool_call',
      data: { id: 'ev_mock1', tool: 'zabbix_list_problems', args: { severity_min: 2 }, started_at: called },
    },
    {
      event: 'tool_result',
      data: { id: 'ev_mock1', ok: true, duration_ms: 180, summary: '활성 Problem 2건', data_clock: called },
    },
    ...content.match(/.{1,12}/gsu)!.map((text): ChatEvent => ({ event: 'token', data: { text } })),
    { event: 'final', data: { message_id: 1, content, evidence_ids: ['ev_mock1'], unknowns: [] } },
  ]
}

const handlerGroups: Record<ApiGroup, HttpHandler[]> = {
  auth: [
    // #1 로그인
    http.post('/api/auth/login', async ({ request }) => {
      const body = (await request.json().catch(() => null)) as { username?: string; password?: string } | null
      const user = users.find((u) => u.username === body?.username)
      if (!user || body?.password !== MOCK_PASSWORD) {
        return error(401, 'INVALID_CREDENTIALS', '아이디 또는 비밀번호가 틀렸습니다')
      }
      const { id, username, role, display_name } = user
      const expiresAt = new Date(Date.now() + 8 * 3600_000).toISOString().replace(/\.\d{3}Z$/, 'Z')
      return ok(
        { token: `${TOKEN_PREFIX}${username}`, user: { id, username, role, display_name } },
        { expires_at: expiresAt },
      )
    }),

    // #3 현재 사용자
    http.get('/api/auth/me', ({ request }) => {
      const user = userFromRequest(request)
      return user ? ok(user) : unauthorized()
    }),
  ],

  health: [
    // #4 연결 상태 — 구성요소가 죽어도 200으로 상태만 알린다(요청서 #4)
    http.get('/api/health', async ({ request }) => {
      if (!userFromRequest(request)) return unauthorized()
      await delay(RESPONSE_DELAY_MS)
      return ok(currentHealth(), { checked_at: now() })
    }),
  ],

  dashboard: [
    // #5 KPI 4종
    http.get('/api/dashboard/summary', async ({ request }) => {
      if (!userFromRequest(request)) return unauthorized()
      await delay(RESPONSE_DELAY_MS)
      return ok(currentSummary(), { generated_at: now() })
    }),
  ],

  problems: [
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
  ],

  incidents: [
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
        .filter(
          (i) => (!status || i.status === status) && (severityMin === undefined || i.severity.level >= severityMin),
        )
        .sort((a, b) => b.started_at.localeCompare(a.started_at))
      const page = filtered.slice(offset, offset + limit)
      const next = offset + limit < filtered.length ? encodeCursor(offset + limit) : null
      const stale = SCENARIO === 'stale'
      return ok(page, { next_cursor: next, data_as_of: stale ? STALE_AS_OF : NORMAL_AS_OF, stale })
    }),

    // #11 장애 상세 — 없으면 404 NOT_FOUND
    http.get('/api/incidents/:id', async ({ request, params }) => {
      if (!userFromRequest(request)) return unauthorized()
      await delay(RESPONSE_DELAY_MS)
      const detail = incidentDetails[Number(params.id)]
      return detail ? ok(detail) : error(404, 'NOT_FOUND', '장애를 찾을 수 없습니다')
    }),
  ],

  chat: [
    // #18 채팅 — operator 이상. 실제 백엔드처럼 text/event-stream으로 이벤트를 하나씩 흘린다.
    http.post('/api/chat', async ({ request }) => {
      const user = userFromRequest(request)
      if (!user) return unauthorized()
      if (user.role === 'viewer') return error(403, 'FORBIDDEN', '권한이 없습니다')
      const body = (await request.json().catch(() => null)) as {
        message?: string
        context?: { incident_id?: number }
      } | null
      if (!body?.message) return error(422, 'VALIDATION_ERROR', 'message가 필요합니다')
      const events = mockChatEvents(body.message, body.context?.incident_id)
      const encoder = new TextEncoder()
      const stream = new ReadableStream<Uint8Array>({
        async start(controller) {
          for (const e of events) {
            await delay(e.event === 'token' ? TOKEN_DELAY_MS : RESPONSE_DELAY_MS)
            controller.enqueue(encoder.encode(sseFrame(e)))
          }
          controller.close()
        },
      })
      return new HttpResponse(stream, {
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-cache' },
      })
    }),
  ],
}

/** 목으로 처리할 핸들러. VITE_MSW_PASSTHROUGH에 적힌 묶음은 빠지고 실제 백엔드(Vite 프록시)로 간다. */
export const handlers: HttpHandler[] = Object.entries(handlerGroups)
  .filter(([group]) => !passthroughGroups.has(group as ApiGroup))
  .flatMap(([, list]) => list)
