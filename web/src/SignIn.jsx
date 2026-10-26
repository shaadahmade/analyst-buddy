import { useRef, useState } from 'react'
import { api, saveToken } from './api.js'
import GoogleSignIn from './GoogleSignIn.jsx'
import Icon from './Icon.jsx'
import MarkerButton from './MarkerButton.jsx'
import Starting from './Starting.jsx'
import ThemeToggle from './ThemeToggle.jsx'
import { useMarkerStroke } from './markers.js'

const CIRCLE = 'M165 6 C 280 6, 326 14, 319 24 C 311 35, 227 39, 154 38 C 66 38, 7 33, 11 22 C 15 13, 70 7, 145 6 C 185 6, 216 7, 235 8'

export default function SignIn({ notice, onBack, onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(notice)
  const [busy, setBusy] = useState(false)
  const [googleBusy, setGoogleBusy] = useState(false)
  const [errors, setErrors] = useState(0)
  const copyRef = useRef(null)
  const formRef = useRef(null)
  const ready = email.trim() !== '' && password !== ''
  useMarkerStroke(copyRef, '.underline-stroke path', 'green', [])
  useMarkerStroke(formRef, '.error .circle-stroke path', 'red', [errors])

  async function submit(e) {
    e.preventDefault()
    if (!ready) return
    setBusy(true)
    setError('')
    try {
      const { token, ...session } = await api('/api/login', { method: 'POST', body: { email, password } })
      saveToken(token)
      onLogin(session)
    } catch (err) {
      setError(err.message)
      setErrors((n) => n + 1)
      setBusy(false)
    }
  }

  return (
    <div className="signin-page">
      <nav className="topbar">
        <button className="wordmark link" onClick={onBack}><Icon name="logo" size={22} />Analyst Buddy</button>
        <ThemeToggle />
      </nav>
      <main className="board-frame signin-frame">
        <div className="board signin-board">
          <div className="signin-copy" ref={copyRef}>
            <h1>
              Open your{' '}
              <span className="underlined">
                team's workspace.
                <svg className="circle-stroke underline-stroke" viewBox="0 0 600 16" preserveAspectRatio="none" aria-hidden="true">
                  <path pathLength="900" d="M8 11 C 120 5, 236 14, 356 8 S 536 5, 592 10" />
                </svg>
              </span>
            </h1>
            <p className="lead">Your goals, your data and everything your analyst has learned are waiting.</p>
          </div>
          <div className="magnet-card">
            <span className="magnet" aria-hidden="true" />
            <form onSubmit={submit} ref={formRef}>
              <h2 className="card-title">Sign in</h2>
              <label className="field">
                <span><Icon name="user" size={16} />Email</span>
                <input inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required autoFocus />
              </label>
              <label className="field">
                <span><Icon name="lock" size={16} />Password</span>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
              </label>
              {error && (
                <p className="error marked" role="alert" key={errors}>
                  {error}
                  <svg className="circle-stroke" viewBox="0 0 330 44" preserveAspectRatio="none" aria-hidden="true">
                    <path pathLength="900" d={CIRCLE} />
                  </svg>
                </p>
              )}
              <MarkerButton ready={ready} busy={busy}>
                {busy ? 'Signing in' : <>Sign in <Icon name="arrow" size={18} /></>}
              </MarkerButton>
            </form>
            <GoogleSignIn onLogin={onLogin} onBusy={setGoogleBusy} />
            {(busy || googleBusy) && <Starting mode="signin" via={googleBusy ? 'Google' : ''} />}
            <p className="card-text small">New here? <button type="button" className="link" onClick={onBack}>Create a workspace</button></p>
          </div>
        </div>
        <div className="tray" aria-hidden="true"><i className="cap blue" /><i className="cap red" /><i className="cap green" /></div>
      </main>
    </div>
  )
}
