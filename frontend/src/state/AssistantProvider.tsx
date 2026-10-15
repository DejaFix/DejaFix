import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { streamChat } from '../lib/chat'
import { ApiError } from '../lib/http'
import type { ChatEvent, LegacyEvidenceCall } from '../lib/types'
import { AssistantContext, type ChatMessage } from './assistant'

// 채팅(#18)은 lib/chat.ts로 POST /api/chat 스트림을 읽는다. 패널(components/AssistantPanel)이 쓰는 ChatMessage 모양은 그대로 둔다.
// - token은 받은 순서대로 이어 붙이고, final이 오면 content로 바꾼다(meta → final만 와도 정상).
// - tool_call·tool_result는 EvidenceTrace 행으로, final.unknowns는 "확인할 수 없음 · 이름 · 사유" 칩으로 보인다.
// - 장애 상세(/incidents/:id)에서 물으면 context.incident_id를 붙인다.

const ERROR_TEXT: Record<string, string> = {
  AGENT_UNAVAILABLE:
    'Agent 연결 안 됨 — AI 어시스턴트가 지금 응답할 수 없습니다. 장애 상세의 리포트·근거는 그대로 볼 수 있습니다.',
  FORBIDDEN: '이 계정은 AI 어시스턴트를 쓸 수 없습니다(operator 이상).',
  NETWORK_ERROR: '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.',
}
const errorText = (code: string) =>
  ERROR_TEXT[code] ?? `응답을 가져오지 못했습니다 (${code}). 잠시 후 다시 시도해 주세요.`

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [pending, setPending] = useState(false)
  const seq = useRef(0)
  const conversationId = useRef<string | undefined>(undefined)
  const { pathname } = useLocation()
  const incidentId = Number(/^\/incidents\/(\d+)/.exec(pathname)?.[1]) || undefined

  const ask = useCallback(
    (question: string) => {
      const text = question.trim()
      if (!text) return
      setOpen(true)
      setMessages((m) => [...m, { id: ++seq.current, role: 'user', text }])
      setPending(true)

      const aiId = ++seq.current
      const calls = new Map<string, LegacyEvidenceCall>()
      // 같은 id의 AI 말풍선 하나를 만들거나 고친다
      const patch = (change: Partial<ChatMessage>) =>
        setMessages((m) =>
          m.some((x) => x.id === aiId)
            ? m.map((x) => (x.id === aiId ? { ...x, ...change } : x))
            : [...m, { id: aiId, role: 'ai', text: '', ...change }],
        )
      let streamed = ''

      const onEvent = (e: ChatEvent) => {
        switch (e.event) {
          case 'meta':
            conversationId.current = e.data.conversation_id || conversationId.current
            break
          case 'tool_call':
            calls.set(e.data.id, { tool: e.data.tool, command: JSON.stringify(e.data.args), result: '조회 중…', ms: 0 })
            patch({ evidence: [...calls.values()] })
            break
          case 'tool_result': {
            const call = calls.get(e.data.id) ?? { tool: e.data.id, command: '', result: '', ms: 0 }
            calls.set(e.data.id, {
              ...call,
              result: e.data.ok ? e.data.summary : `실패 · ${e.data.summary}`,
              ms: e.data.duration_ms,
            })
            patch({ evidence: [...calls.values()] })
            break
          }
          case 'token':
            streamed += e.data.text
            patch({ text: streamed })
            break
          case 'final':
            patch({
              text: e.data.content,
              unknowns: e.data.unknowns.map((u) => `${u.label} · ${u.reason}`),
              evidence: calls.size > 0 ? [...calls.values()] : undefined,
            })
            break
          case 'error':
            patch({ text: errorText(e.data.code) })
            break
        }
      }

      streamChat(
        { conversation_id: conversationId.current, message: text, context: { incident_id: incidentId } },
        onEvent,
      )
        .catch((err: unknown) => patch({ text: errorText(err instanceof ApiError ? err.code : 'UNKNOWN') }))
        .finally(() => setPending(false))
    },
    [incidentId],
  )

  const reset = useCallback(() => {
    conversationId.current = undefined
    setMessages([])
  }, [])
  const value = useMemo(() => ({ open, setOpen, messages, pending, ask, reset }), [open, messages, pending, ask, reset])
  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>
}
