import { delay, http, HttpResponse, type HttpHandler } from 'msw'
import { incidentDetails } from '../lib/mock'
import { NOTE_MAX_LENGTH, type ResolutionNote } from '../lib/notesApi'

// 계약 PR #191(contracts/api.md #26·#27)의 형식을 따르는 해결 메모 목. 새로고침 전까지 메모리에만 유지한다.
// - 응답의 작성자는 author { id, display_name } 객체, 빈 필드는 ''가 아니라 null
// - 목록은 최신 먼저(created_at 내림차순, 같으면 id 내림차순)
// - 목에 없는 장애 ID는 404 NOT_FOUND
const notes: ResolutionNote[] = [
  {
    id: 1,
    incident_id: 9,
    author: { id: 2, display_name: '당직자' },
    root_cause: '배치 작업이 임시 파일을 지우지 않아 디스크가 찼음',
    action_taken: '임시 폴더 정리(사람이 직접), 배치 스크립트에 정리 단계 추가 요청',
    result: '사용률 정상 복귀',
    created_at: '2026-10-16T00:10:00Z',
  },
]
let nextId = 2

const err = (status: number, code: string, message: string) =>
  HttpResponse.json({ error: { code, message } }, { status })

const incidentExists = (id: number) => Number.isInteger(id) && id in incidentDetails
/** 앞뒤 공백을 자르고, 비면 null (서버 저장 규칙) */
const clean = (s: string) => s.trim() || null

type MockUser = { id: number; role: string; display_name: string | null; username: string }

export function notesHandlers(userFromRequest: (r: Request) => MockUser | null): HttpHandler[] {
  return [
    http.get('/api/incidents/:id/notes', async ({ request, params }) => {
      if (!userFromRequest(request)) return err(401, 'UNAUTHORIZED', '로그인이 필요합니다')
      await delay(150)
      const id = Number(params.id)
      if (!incidentExists(id)) return err(404, 'NOT_FOUND', '장애를 찾을 수 없습니다')
      const list = notes
        .filter((n) => n.incident_id === id)
        .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id)
      return HttpResponse.json({ data: list, meta: {} })
    }),
    http.post('/api/incidents/:id/notes', async ({ request, params }) => {
      const user = userFromRequest(request)
      if (!user) return err(401, 'UNAUTHORIZED', '로그인이 필요합니다')
      if (user.role === 'viewer') return err(403, 'FORBIDDEN', '권한이 없습니다')
      await delay(150)
      if (!incidentExists(Number(params.id))) return err(404, 'NOT_FOUND', '장애를 찾을 수 없습니다')
      const b = (await request.json().catch(() => null)) as Record<string, unknown> | null
      const field = (k: string) => (typeof b?.[k] === 'string' ? (b[k] as string) : '')
      const [root_cause, action_taken, result] = [field('root_cause'), field('action_taken'), field('result')]
      if (![root_cause, action_taken, result].some((s) => s.trim())) {
        return err(422, 'VALIDATION_ERROR', '실제 원인·한 조치·결과 중 하나는 적어야 합니다')
      }
      if ([root_cause, action_taken, result].some((s) => s.length > NOTE_MAX_LENGTH)) {
        return err(422, 'VALIDATION_ERROR', `각 항목은 ${NOTE_MAX_LENGTH}자 이하여야 합니다`)
      }
      const note: ResolutionNote = {
        id: nextId++,
        incident_id: Number(params.id),
        author: { id: user.id, display_name: user.display_name ?? user.username },
        root_cause: clean(root_cause),
        action_taken: clean(action_taken),
        result: clean(result),
        created_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
      }
      notes.push(note)
      return HttpResponse.json({ data: note, meta: {} }, { status: 201 })
    }),
  ]
}
