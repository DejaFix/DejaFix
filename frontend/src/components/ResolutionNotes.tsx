import { useState, type FormEvent } from 'react'
import { useAuth } from '../state/auth'
import { NOTE_MAX_LENGTH, useAddResolutionNote, useResolutionNotes, type NoteInput } from '../lib/notesApi'
import { kstShort } from './incidentFormat'

const FIELDS: { key: keyof NoteInput; label: string }[] = [
  { key: 'root_cause', label: '실제 원인' },
  { key: 'action_taken', label: '한 조치' },
  { key: 'result', label: '결과' },
]
const EMPTY: NoteInput = { root_cause: '', action_taken: '', result: '' }

/** 해결된 장애의 해결 메모(사람이 쓴 것만). 실행 기능 없음 — 저장 버튼만 있다(SAFE-04). */
export function ResolutionNotes({ incidentId }: { incidentId: number }) {
  const { role } = useAuth()
  const canWrite = role === 'operator' || role === 'admin'
  const { data: res, isLoading, isError } = useResolutionNotes(incidentId)
  const add = useAddResolutionNote(incidentId)
  const [form, setForm] = useState<NoteInput>(EMPTY)
  const [message, setMessage] = useState<string | null>(null)

  const allEmpty = FIELDS.every((f) => !form[f.key].trim())
  const tooLong = FIELDS.some((f) => form[f.key].length > NOTE_MAX_LENGTH)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (allEmpty || tooLong || add.isPending) return
    setMessage(null)
    add.mutate(form, {
      onSuccess: () => setForm(EMPTY),
      onError: (err) =>
        setMessage(
          err.status === 422
            ? err.message
            : err.status === 403
              ? '메모를 쓸 권한이 없습니다.'
              : '메모를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.',
        ),
    })
  }

  const notes = res?.data ?? []
  return (
    <section className="card">
      <div className="card-head">
        <h2 className="card-title">해결 메모</h2>
      </div>
      <p className="card-sub">사람이 쓴 메모만 다음 분석의 근거로 쓰입니다. 실행 기능은 없습니다.</p>

      {isLoading && <p className="card-sub">불러오는 중…</p>}
      {isError && <p className="card-sub">메모를 불러오지 못했습니다.</p>}
      {!isLoading && !isError && notes.length === 0 && <p className="card-sub">아직 남긴 해결 메모가 없습니다.</p>}
      {notes.length > 0 && (
        <ul className="bullets">
          {notes.map((n) => (
            <li key={n.id}>
              <strong>
                {n.author.display_name} · {kstShort(n.created_at) ?? '—'}
              </strong>
              {FIELDS.map(
                (f) =>
                  n[f.key] && (
                    <div key={f.key}>
                      {f.label}: {n[f.key]}
                    </div>
                  ),
              )}
            </li>
          ))}
        </ul>
      )}

      {canWrite && (
        <form onSubmit={submit}>
          {FIELDS.map((f) => (
            <label className="field" key={f.key}>
              {f.label}
              <textarea
                rows={2}
                value={form[f.key]}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                style={{ font: 'inherit', padding: 8, border: '1px solid var(--border-strong)', borderRadius: 10 }}
              />
              <span className="card-sub">
                {form[f.key].length}/{NOTE_MAX_LENGTH}
                {form[f.key].length > NOTE_MAX_LENGTH && ' — 1000자를 넘었습니다'}
              </span>
            </label>
          ))}
          {message && <p role="alert">{message}</p>}
          <button
            type="submit"
            className="btn primary"
            style={{ marginTop: 12 }}
            disabled={allEmpty || tooLong || add.isPending}
          >
            메모 저장
          </button>
          {allEmpty && <span className="card-sub"> 한 항목 이상 적어 주세요.</span>}
        </form>
      )}
    </section>
  )
}
