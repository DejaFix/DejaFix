import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useAssistant } from '../state/assistant'
import { EvidenceTrace } from './EvidenceTrace'
import { Icon } from './Icon'

const suggestions = ['어떤 질문 할 수 있어?', '지금 확인해야 할 장애 뭐 있어?', 'CPU 피크 높은 서버 10대', '통신 끊긴 서버 있어?']

export function AssistantPanel() {
  const { open, setOpen, messages, pending, ask, reset } = useAssistant()
  const [text, setText] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, pending])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setOpen])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!text.trim() || pending) return
    ask(text)
    setText('')
  }

  return (
    <aside className={`assistant ${open ? 'open' : ''}`} aria-label="AI 어시스턴트" aria-hidden={!open}>
      <div className="assistant-head">
        <div style={{ flex: 1 }}>
          <div className="assistant-title">AI 어시스턴트</div>
          <div className="assistant-sub">조회 전용 · 변경은 계획까지만</div>
        </div>
        <button className="btn small" onClick={reset}>새 대화</button>
        <button className="btn small" onClick={() => setOpen(false)} aria-label="닫기"><Icon name="close" size={14} /></button>
      </div>
      <div className="assistant-body">
        <div className="bubble ai">운영 Zabbix 데이터를 조회해서 답합니다. 확인되지 않은 값은 추정하지 않고 '확인할 수 없음'으로 알려 드립니다.</div>
        {messages.length === 0 && (
          <div className="chips">{suggestions.map((s) => <button key={s} className="q-chip" onClick={() => ask(s)}>{s}</button>)}</div>
        )}
        {messages.map((m) => (
          <div key={m.id} style={{ display: 'flex', flexDirection: 'column', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div className={`bubble ${m.role}`}>{m.text}</div>
            {m.unknowns && m.unknowns.length > 0 && (
              <div className="chips" style={{ marginTop: 6 }}>{m.unknowns.map((u) => <span key={u} className="chip amber">확인할 수 없음 · {u}</span>)}</div>
            )}
            {m.evidence && <div style={{ width: '92%' }}><EvidenceTrace calls={m.evidence} /></div>}
          </div>
        ))}
        {pending && <div className="bubble ai"><span className="typing"><i /><i /><i /></span></div>}
        <div ref={endRef} />
      </div>
      <form className="assistant-foot" onSubmit={submit}>
        <div className="composer">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="질문을 입력하세요" aria-label="질문 입력" />
          <button className="send" type="submit" disabled={!text.trim() || pending} aria-label="보내기"><Icon name="send" size={16} /></button>
        </div>
        <div className="assistant-note">Enter 보내기 · Esc 닫기 · 목업 응답입니다</div>
      </form>
    </aside>
  )
}
