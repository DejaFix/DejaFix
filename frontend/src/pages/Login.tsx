import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../state/auth'

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [id, setId] = useState('')
  const [pw, setPw] = useState('')
  if (user) return <Navigate to="/" replace />

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!id.trim() || !pw) return
    login(id.trim())
    navigate('/', { replace: true })
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand" style={{ padding: 0, marginBottom: 6 }}>DejaFix</div>
        <h1 className="page-title" style={{ fontSize: 22 }}>사내 계정으로 로그인</h1>
        <p className="page-sub">목업 화면입니다. 입력만 있으면 로그인됩니다.</p>
        <label className="field">아이디<input value={id} onChange={(e) => setId(e.target.value)} autoFocus autoComplete="username" /></label>
        <label className="field">비밀번호<input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" /></label>
        <button className="btn primary" style={{ width: '100%', marginTop: 20, height: 42 }} type="submit" disabled={!id.trim() || !pw}>로그인</button>
      </form>
    </div>
  )
}
