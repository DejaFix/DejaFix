import { ApiError, handleUnauthorized } from './http'
import { tokenStorage } from './tokenStorage'
import type { ApiErrorBody, ApiResponse, ChatEvent, ChatReply, ChatRequest } from './types'

// #18 POST /api/chat 클라이언트 (FR-FE-011·014, agent-api.md 1장).
// - EventSource는 GET만 되고 Authorization 헤더를 못 붙이므로 fetch + ReadableStream으로 SSE를 직접 읽는다.
// - 응답이 JSON이면(탈출 규칙 1, 비스트리밍) 같은 이벤트 순서(meta → tool_call/tool_result → final)로 바꿔 넘긴다.
// - 스트림을 열기 전 오류(401·403·4xx·5xx JSON)는 ApiError로 던지고, 스트림 안의 오류는 error 이벤트로 넘긴다.

/** SSE 본문을 이벤트 단위로 자른다. 빈 줄이 이벤트 경계, data 줄이 여러 개면 줄바꿈으로 잇는다. */
function parseFrame(frame: string): ChatEvent | null {
  let event = ''
  const data: string[] = []
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  if (!event) return null
  try {
    return { event, data: JSON.parse(data.join('\n') || '{}') } as ChatEvent
  } catch {
    return null
  }
}

async function readSse(body: ReadableStream<Uint8Array>, onEvent: (e: ChatEvent) => void): Promise<boolean> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let ended = false
  for (;;) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const frames = buffer.split(/\r?\n\r?\n/)
    buffer = done ? '' : (frames.pop() ?? '')
    for (const frame of frames) {
      const e = frame.trim() ? parseFrame(frame) : null
      if (!e) continue
      if (e.event === 'final' || e.event === 'error') ended = true
      onEvent(e)
    }
    if (done) return ended
  }
}

function replyToEvents(reply: ChatReply): ChatEvent[] {
  const events: ChatEvent[] = [
    { event: 'meta', data: { conversation_id: reply.conversation_id, run_id: '', message_id: reply.message_id } },
  ]
  for (const c of reply.tool_calls) {
    events.push({ event: 'tool_call', data: { id: c.id, tool: c.tool, args: c.args, started_at: '' } })
    events.push({
      event: 'tool_result',
      data: { id: c.id, ok: c.ok, duration_ms: c.duration_ms, summary: c.summary, data_clock: c.data_clock },
    })
  }
  events.push({
    event: 'final',
    data: {
      message_id: reply.message_id,
      content: reply.content,
      evidence_ids: reply.evidence_ids,
      unknowns: reply.unknowns,
    },
  })
  return events
}

/**
 * 질문을 보내고 이벤트가 올 때마다 onEvent를 부른다. final·error 없이 스트림이 끊기면 AGENT_UNAVAILABLE error 이벤트로 닫는다.
 * 스트림을 열기 전 HTTP 오류는 ApiError로 던진다(401이면 로그아웃).
 */
export async function streamChat(
  request: ChatRequest,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = tokenStorage.get()?.token
  if (!token) throw new ApiError(401, 'UNAUTHORIZED', '로그인이 필요합니다')

  let res: Response
  try {
    res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', Authorization: `Bearer ${token}` },
      body: JSON.stringify(request),
      signal,
    })
  } catch (e) {
    if (signal?.aborted) throw e
    throw new ApiError(0, 'NETWORK_ERROR', '서버에 연결할 수 없습니다')
  }

  const type = res.headers.get('Content-Type') ?? ''
  if (res.ok && type.startsWith('text/event-stream') && res.body) {
    const ended = await readSse(res.body, onEvent)
    if (!ended) onEvent({ event: 'error', data: { code: 'AGENT_UNAVAILABLE', message: 'Agent 연결이 끊겼습니다' } })
    return
  }

  const body = (await res.json().catch(() => null)) as (Partial<ApiResponse<ChatReply>> & Partial<ApiErrorBody>) | null
  if (res.ok && body?.data) {
    replyToEvents(body.data).forEach(onEvent)
    return
  }
  if (res.status === 401) handleUnauthorized()
  throw new ApiError(
    res.status,
    body?.error?.code ?? 'UNKNOWN',
    body?.error?.message ?? `요청에 실패했습니다 (${res.status})`,
  )
}
