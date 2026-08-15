import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const DEMO = [
  { role: 'Platform Admin',     email: 'platform@admin.uz',           color: '#a34444' },
  { role: 'Company Admin',      email: 'admin@alphacorp.uz',           color: '#145c63' },
  { role: 'Employee STANDARD',  email: 'alice@alphacorp.uz',           color: '#657284' },
  { role: 'Employee PLUS',      email: 'bob@alphacorp.uz',             color: '#657284' },
  { role: 'Employee PRO',       email: 'charlie@alphacorp.uz',         color: '#145c63' },
  { role: 'Merchant FitZone',   email: 'merchant.user@fitzone.uz',     color: '#966b19' },
  { role: 'Merchant Cinema',    email: 'merchant.user@cinemaplus.uz',  color: '#966b19' },
]

export default function Login() {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [busy, setBusy]         = useState(false)
  const { login, user, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!authLoading && user) navigate('/dashboard', { replace: true })
  }, [user, authLoading, navigate])

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setError(''); setBusy(true)
    try { await login(email, password); navigate('/dashboard') }
    catch (err: any) { setError(err.response?.data?.error?.message || err.message || 'Не удалось войти') }
    finally { setBusy(false) }
  }

  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: '1.5rem', background: '#e7edef' }}>
      <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start', flexWrap: 'wrap', justifyContent: 'center', width: '100%', maxWidth: 920 }}>

        {/* ── LOGIN FORM ─────────────────────────────────── */}
        <section className="login-panel" style={{ flex: '1 1 360px', maxWidth: 440 }}>
          <p className="eyebrow">Наггетсы30</p>
          <h1>Корпоративные льготы</h1>
          <p className="muted" style={{ marginBottom: '1.6rem' }}>Войдите, чтобы открыть персональный кабинет.</p>
          <form onSubmit={submit} className="login-form">
            <label>Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            </label>
            <label>Пароль
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
            </label>
            {error && <div className="notice error">{error}</div>}
            <button className="button" disabled={busy}>{busy ? 'Входим…' : 'Войти'}</button>
          </form>
        </section>

        {/* ── DEMO CREDENTIALS ──────────────────────────── */}
        <section style={{ flex: '1 1 320px', maxWidth: 400, background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 6, padding: '1.6rem', boxShadow: '0 18px 50px rgba(24,33,47,.08)' }}>
          <p className="eyebrow" style={{ marginBottom: '.4rem' }}>Демо-доступ</p>
          <p style={{ color: 'var(--muted)', fontSize: '.82rem', marginBottom: '1.2rem', lineHeight: 1.5 }}>
            Нажмите на аккаунт — данные подставятся автоматически.<br />
            Пароль для всех: <code>Demo1234!</code>
          </p>
          <div style={{ display: 'grid', gap: '.45rem' }}>
            {DEMO.map((acc) => (
              <button key={acc.email}
                style={{ display: 'flex', alignItems: 'center', gap: '.65rem', textAlign: 'left', background: email === acc.email ? 'var(--accent-soft)' : '#f4f6f8', border: `1px solid ${email === acc.email ? 'var(--accent)' : 'var(--line)'}`, borderRadius: 4, padding: '.52rem .75rem', cursor: 'pointer', transition: 'all .15s' }}
                onClick={() => { setEmail(acc.email); setPassword('Demo1234!') }}>
                <span style={{ fontSize: '.68rem', fontWeight: 800, color: acc.color, minWidth: 118, letterSpacing: '.01em' }}>{acc.role}</span>
                <span style={{ color: 'var(--muted)', fontSize: '.76rem', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{acc.email}</span>
              </button>
            ))}
          </div>
        </section>

      </div>
    </main>
  )
}
