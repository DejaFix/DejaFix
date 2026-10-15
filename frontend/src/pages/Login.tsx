import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/authApi'
import { useAuth } from '../state/auth'

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [id, setId] = useState('')
  const [pw, setPw] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  if (user) return <Navigate to="/" replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!id.trim() || !pw || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await login(id.trim(), pw)
      navigate('/', { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'INVALID_CREDENTIALS'
          ? '아이디 또는 비밀번호가 틀렸습니다'
          : err instanceof Error
            ? err.message
            : '로그인에 실패했습니다',
      )
      setSubmitting(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand" style={{ padding: 0, marginBottom: 6 }}>
          DejaFix
        </div>
        <h1 className="page-title" style={{ fontSize: 22 }}>
          사내 계정으로 로그인
        </h1>
        <p className="page-sub">데모 계정으로 로그인합니다.</p>
        <label className="field" htmlFor="login-id">
          아이디
          <input id="login-id" value={id} onChange={(e) => setId(e.target.value)} autoFocus autoComplete="username" />
        </label>
        <label className="field" htmlFor="login-pw">
          비밀번호
          <input
            id="login-pw"
            type="password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error ? (
          <p role="alert" style={{ color: 'var(--sev-high)', marginTop: 12 }}>
            {error}
          </p>
        ) : null}
        <button
          className="btn primary"
          style={{ width: '100%', marginTop: 20, height: 42 }}
          type="submit"
          disabled={!id.trim() || !pw || submitting}
        >
          {submitting ? '로그인 중…' : '로그인'}
        </button>
      </form>
    </div>
  )
}
