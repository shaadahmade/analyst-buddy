import { useEffect, useRef, useState } from 'react'
import { api, saveToken } from './api.js'
import GoogleSignIn from './GoogleSignIn.jsx'
import Icon from './Icon.jsx'
import Starting from './Starting.jsx'
import ThemeToggle from './ThemeToggle.jsx'
import MarkerButton from './MarkerButton.jsx'
import { useMarkerStroke } from './markers.js'

const EXAMPLES = {
  sales: {
    label: 'Sales',
    figure: '-12%', tone: 'red', figureNote: 'Revenue against the last 4 weeks', source: 'orders.csv: 11,238 rows read, 3 code runs',
    notes: [
      { tone: 'red', text: 'Pro Plan sales in the South region stopped 3 weeks ago', source: 'orders.csv, 312 rows' },
      { tone: 'ink', text: 'Paid Ads now bring in 30% of all orders', source: 'orders.csv, channel column' },
      { tone: 'green', text: 'Q4 revenue goal is 82% reached and on pace', source: 'your Q4 goal' },
    ],
  },
  support: {
    label: 'Support tickets',
    figure: '+38%', tone: 'red', figureNote: 'Time to close a ticket, against the last 4 weeks', source: 'tickets.csv: 4,812 rows read, 3 code runs',
    notes: [
      { tone: 'red', text: 'Billing tickets now wait 2.4 days, twice as long as the rest', source: 'tickets.csv, category column' },
      { tone: 'ink', text: "Mondays bring 31% of the week's new tickets", source: 'tickets.csv, created_at column' },
      { tone: 'green', text: 'Customer satisfaction held at 4.6 out of 5', source: 'tickets.csv, csat column' },
    ],
  },
  website: {
    label: 'Website',
    figure: '+18%', tone: 'green', figureNote: 'Sign-ups against the last 4 weeks', source: 'visits.csv: 92,406 rows read, 2 code runs',
    notes: [
      { tone: 'red', text: 'Half of mobile visitors now leave at checkout, up from a third', source: 'visits.csv, device and step columns' },
      { tone: 'green', text: 'The new pricing page turns 6.1% of visitors into sign-ups', source: 'visits.csv, page column' },
      { tone: 'ink', text: 'Search brings 44% of visits, social 12%', source: 'visits.csv, source column' },
    ],
  },
}

const STEPS = [
  { title: 'Upload your data', text: 'Any spreadsheet: sales, customers, support tickets, stock, website visits. CSV, Excel, JSON or Parquet.' },
  { title: 'Tell it your goals', text: 'Your targets and how you define them. It keeps them.' },
  { title: 'Ask in plain words', text: 'Get the answer, the numbers behind it and what to do.' },
]

const TRUST = [
  { icon: 'code', tone: 'ink', title: 'Every number is computed', text: 'It writes and runs real code on your data. Nothing is guessed.' },
  { icon: 'brain', tone: 'ink', title: 'It learns your business', text: 'Goals, definitions and your corrections carry into every answer.' },
  { icon: 'shield', tone: 'ink', title: 'Your data stays yours', text: 'Each company gets its own private workspace and sandbox.' },
]

const SAMPLE_BARS = [62, 66, 64, 71, 74, 69, 77, 75, 81, 70, 63, 58]

export default function Landing({ onSignIn, onLogin }) {
  const [example, setExample] = useState('sales')
  const [erasing, setErasing] = useState(false)
  const flowRef = useWriteOnWhenVisible()
  const heroRef = useRef(null)
  useMarkerStroke(heroRef, '.circle-stroke path', EXAMPLES[example].tone, [example])

  function switchExample(next) {
    if (next === example || erasing) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) return setExample(next)
    setErasing(true)
    setTimeout(() => { setExample(next); setErasing(false) }, 420)
  }

  const data = EXAMPLES[example]

  return (
    <div className="landing">
      <nav className="topbar">
        <a className="wordmark" href="#top"><Icon name="logo" size={22} />Analyst Buddy</a>
        <div className="topbar-links">
          <a href="#how">How it works</a>
          <a href="#access">Create a workspace</a>
          <ThemeToggle />
          <button className="btn btn-outline" onClick={onSignIn}>Sign in</button>
        </div>
      </nav>

      <header className="board-frame hero" id="top" ref={heroRef}>
        <div className="board">
          <div className="hero-grid">
            <div className="hero-main">
              <h1>Know what changed in your business this week, and why.</h1>
              <p className="lead">
                Analyst Buddy reads whatever data your business keeps in spreadsheets, runs the numbers and tells you what moved, why it moved and what to do on Monday.
              </p>

              <div className="board-meta">
                <div className="week-switch" role="group" aria-label="Example data">
                  {Object.entries(EXAMPLES).map(([key, ex]) => (
                    <button key={key} className={`magnet-btn ${example === key ? 'on' : ''}`} aria-pressed={example === key} onClick={() => switchExample(key)}>
                      {ex.label}
                    </button>
                  ))}
                </div>
                <span className="example-tag">Examples from sample data</span>
              </div>

              <div className={`writing ${erasing ? 'erasing' : ''}`} key={example}>
                <div className="figure-block">
                  <div className={`figure ink tone-${data.tone}`} style={{ '--i': 0 }}>
                    {data.figure}
                    <svg className="circle-stroke" viewBox="0 0 300 140" preserveAspectRatio="none" aria-hidden="true">
                      <path pathLength="900" d="M150 8 C 255 6, 296 40, 290 76 C 283 118, 206 134, 140 132 C 60 130, 6 110, 10 70 C 14 34, 64 12, 132 9 C 168 7, 196 10, 214 16" />
                    </svg>
                  </div>
                  <p className="ink figure-note" style={{ '--i': 1 }}>{data.figureNote}</p>
                  <span className="ink source-tag" style={{ '--i': 1 }}>{data.source}</span>
                </div>
                <ol className="notes" aria-label="Findings ranked by urgency">
                  {data.notes.map((n, i) => (
                    <li key={n.text} className="ink" style={{ '--i': i + 2 }}>
                      <span className={`rank tone-${n.tone}`}>{i + 1}</span>
                      <span>
                        <span className="note-text">{n.text}</span>
                        <span className="source-tag">{n.source}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            </div>

            <aside className="hero-side" id="access">
              <WorkspaceCard onLogin={onLogin} />
            </aside>
          </div>
        </div>
        <div className="tray" aria-hidden="true"><i className="cap blue" /><i className="cap red" /><i className="cap green" /></div>
      </header>

      <section className="section" id="how">
        <h2>From your spreadsheet to Monday's answers</h2>
        <ol className="flow" ref={flowRef}>
          {STEPS.map((s, i) => (
            <li key={s.title} style={{ '--s': i }}>
              <div className="flow-step">
                <span className="flow-n">{i + 1}</span>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
              </div>
              {i < STEPS.length - 1 && (
                <svg className="flow-arrow" viewBox="0 0 120 40" aria-hidden="true">
                  <path d="M4 24 C 40 8, 76 34, 112 18 M96 8 L113 18 L99 32" />
                </svg>
              )}
            </li>
          ))}
        </ol>
      </section>

      <section className="section proof">
        <div className="proof-copy">
          <h2>Answers you can check, not guesses you have to trust</h2>
          <ul className="trust">
            {TRUST.map((t) => (
              <li key={t.title}>
                <span className={`trust-icon tone-${t.tone}`}><Icon name={t.icon} size={22} /></span>
                <span><strong>{t.title}</strong><span>{t.text}</span></span>
              </li>
            ))}
          </ul>
        </div>

        <figure className="printout">
          <span className="magnet" aria-hidden="true" />
          <figcaption className="printout-q"><Icon name="user" size={16} />Why did revenue drop over the last 3 weeks?</figcaption>
          <div className="printout-a">
            <p><strong>Revenue is down 12% against the previous 4 weeks.</strong> Almost all of the drop comes from one place: Pro Plan sales in the South region went from about 9 a week to zero, starting 3 weeks ago.</p>
            <div className="mini-chart" aria-label="Weekly revenue, last 12 weeks, sample data">
              {SAMPLE_BARS.map((h, i) => <span key={i} className={i >= 9 ? 'dip' : ''} style={{ height: `${h}%` }} />)}
            </div>
            <p><strong>Do this week:</strong> check the South sales team and the Pro Plan checkout for that region.</p>
          </div>
          <p className="printout-foot">Computed from orders.csv: 11,238 rows, 3 code runs. Example from a sample company.</p>
        </figure>
      </section>

      <section className="board-frame closing">
        <div className="board closing-board">
          <h2>Your first Monday review is one upload away.</h2>
          <p className="lead">Create a workspace, add your data and invite your team. No waiting list.</p>
          <WorkspaceCard compact onLogin={onLogin} />
        </div>
        <div className="tray" aria-hidden="true"><i className="cap blue" /><i className="cap red" /><i className="cap green" /></div>
      </section>

      <footer className="footer">
        <span>© 2026 Analyst Buddy</span>
        <button className="link" onClick={onSignIn}>Sign in</button>
        <a href="https://icons8.com" target="_blank" rel="noreferrer">Icons by Icons8</a>
      </footer>
    </div>
  )
}

function useWriteOnWhenVisible() {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el || !('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const box = el.getBoundingClientRect()
    if (box.top < window.innerHeight && box.bottom > 0) return
    el.classList.add('armed')
    const io = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return
      el.classList.add('drawn')
      io.disconnect()
    }, { threshold: 0.2 })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return ref
}

function WorkspaceCard({ compact = false, onLogin }) {
  const [workspace, setWorkspace] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [googleBusy, setGoogleBusy] = useState(false)
  const [error, setError] = useState('')
  const ready = workspace.trim() !== '' && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim()) && password.length >= 8

  async function submit(e) {
    e.preventDefault()
    if (!ready) return
    setBusy(true)
    setError('')
    try {
      const { token, ...session } = await api('/api/signup', { method: 'POST', body: { workspace, email, password } })
      saveToken(token)
      onLogin(session)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className={`magnet-card ${compact ? 'compact' : ''}`}>
      <span className="magnet" aria-hidden="true" />
      <form onSubmit={submit}>
        {!compact && <h2 className="card-title">Create your workspace</h2>}
        {!compact && <p className="card-text">Free to start. You are the owner and can add your team right away.</p>}
        <label className="field">
          <span>Workspace name</span>
          <input value={workspace} onChange={(e) => setWorkspace(e.target.value)} autoComplete="organization" required maxLength={60} placeholder="Your company or team" />
        </label>
        <label className="field">
          <span>Work email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required placeholder="you@yourcompany.com" />
        </label>
        <label className="field">
          <span>Password <em>(8+ characters)</em></span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required minLength={8} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <MarkerButton ready={ready} busy={busy}>
          {busy ? 'Creating your workspace' : <>Create workspace <Icon name="arrow" size={18} /></>}
        </MarkerButton>
      </form>
      {!compact && <GoogleSignIn workspace={workspace} onLogin={onLogin} onBusy={setGoogleBusy} />}
      {(busy || googleBusy) && <Starting mode="signup" via={googleBusy ? 'Google' : ''} />}
    </div>
  )
}
