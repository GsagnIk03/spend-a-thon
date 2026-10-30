import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { ErrorNote } from '../components/ui'
import { useAuth } from '../hooks'

export default function AuthPage() {
  const { signIn } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = mode === 'login'
        ? await api.login({ email, password })
        : await api.register({ name, email, password })
      signIn(res.token, res.user)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  const switchTo = (m: 'login' | 'register') => { setMode(m); setError(null) }

  return (
    <div className="auth">
      <section className="auth-hero">
        <div className="brand big"><span className="brand-mark">₹</span> spend-a-thon</div>
        <h1>Know where every rupee goes.</h1>
        <p>Log expenses in seconds, set monthly budgets, let rent and subscriptions add themselves,
          and see your month at a glance.</p>
        <ul className="auth-points">
          <li>📊 Monthly dashboard & trends</li>
          <li>🎯 Category budgets with alerts</li>
          <li>🔁 Recurring bills on autopilot</li>
          <li>💳 Cards, loans & CSV export</li>
        </ul>
      </section>

      <section className="auth-card">
        <div className="seg">
          <button className={mode === 'login' ? 'active' : ''} onClick={() => switchTo('login')}>Log in</button>
          <button className={mode === 'register' ? 'active' : ''} onClick={() => switchTo('register')}>Sign up</button>
        </div>
        <form onSubmit={submit} className="form">
          {mode === 'register' && (
            <label className="field">
              <span className="field-label">Your name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required maxLength={60} />
            </label>
          )}
          <label className="field">
            <span className="field-label">Email</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
          </label>
          <label className="field">
            <span className="field-label">Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              minLength={mode === 'register' ? 8 : undefined} required />
            {mode === 'register' && <span className="hint">At least 8 characters</span>}
          </label>
          <ErrorNote message={error} />
          <button className="btn primary block" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
          </button>
        </form>
        <p className="muted center small-text">
          {mode === 'login' ? "New here? " : 'Already have an account? '}
          <button className="link-btn" onClick={() => switchTo(mode === 'login' ? 'register' : 'login')}>
            {mode === 'login' ? 'Create an account' : 'Log in'}
          </button>
        </p>
      </section>
    </div>
  )
}
