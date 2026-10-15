import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { askAssistant } from '../lib/api'
import { AssistantContext, type ChatMessage } from './assistant'

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [pending, setPending] = useState(false)
  const seq = useRef(0)

  const ask = useCallback((question: string) => {
    const text = question.trim()
    if (!text) return
    setOpen(true)
    setMessages((m) => [...m, { id: ++seq.current, role: 'user', text }])
    setPending(true)
    askAssistant(text)
      .then((r) =>
        setMessages((m) => [
          ...m,
          { id: ++seq.current, role: 'ai', text: r.text, evidence: r.evidence, unknowns: r.unknowns },
        ]),
      )
      .catch(() =>
        setMessages((m) => [
          ...m,
          { id: ++seq.current, role: 'ai', text: '응답을 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.' },
        ]),
      )
      .finally(() => setPending(false))
  }, [])

  const reset = useCallback(() => setMessages([]), [])
  const value = useMemo(() => ({ open, setOpen, messages, pending, ask, reset }), [open, messages, pending, ask, reset])
  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>
}
