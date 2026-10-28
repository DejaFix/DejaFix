import { delay, http, HttpResponse, type HttpHandler } from 'msw'
import { NOTE_MAX_LENGTH, type ResolutionNote } from '../lib/notesApi'

// 이슈 #153 제안 형식의 해결 메모 목. 새로고침 전까지 메모리에만 유지한다.
const notes: ResolutionNote[] = [
  {
    id: 1,
    incident_id: 2,
    author_user_id: 2,
    author_name: '당직자',
    root_cause: '배치 작업이 임시 파일을 지우지 않아 디스크가 찼음',
    action_taken: '임시 폴더 정리(사람이 직접), 배치 스크립트에 정리 단계 추가 요청',
    result: '사용률 정상 복귀',
    created_at: '2026-10-16T00:10:00Z',
  },
]
let nextId = 2

const err = (status: number, code: string, message: string) =>
  HttpResponse.json({ error: { code, message } }, { status })

type MockUser = { id: number; role: string; display_name: string | null; username: string }

export function notesHandlers(userFromRequest: (r: Request) => MockUser | null): HttpHandler[] {
  return [
    http.get('/api/incidents/:id/notes', async ({ request, params }) => {
      if (!userFromRequest(request)) return err(401, 'UNAUTHORIZED', '로그인이 필요합니다')
      await delay(150)
      const id = Number(params.id)
      return HttpResponse.json({ data: notes.filter((n) => n.incident_id === id), meta: {} })
    }),
    http.post('/api/incidents/:id/notes', async ({ request, params }) => {
      const user = userFromRequest(request)
      if (!user) return err(401, 'UNAUTHORIZED', '로그인이 필요합니다')
      if (user.role === 'viewer') return err(403, 'FORBIDDEN', '권한이 없습니다')
      await delay(150)
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
        author_user_id: user.id,
        author_name: user.display_name ?? user.username,
        root_cause: root_cause.trim(),
        action_taken: action_taken.trim(),
        result: result.trim(),
        created_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
      }
      notes.push(note)
      return HttpResponse.json({ data: note, meta: {} }, { status: 201 })
    }),
  ]
}
