import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'

const pct = (v) => (v == null ? '–' : `${Math.round(v * 100)}%`)
const secs = (v) => (v == null ? '–' : `${v}s`)
const num = (v) => (v == null ? '–' : v.toLocaleString())
const when = (at) => (at ? new Date(at).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'never')
const day = (d) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
const FILTERS = { all: 'All', ask: 'Questions', login: 'Sign-ins', member: 'Members', data: 'Data', denied: 'Denied' }

function matches(filter, action = '') {
  if (filter === 'all') return true
  if (filter === 'data') return /upload|source|connect|delete|sync|data/.test(action)
  return action.includes(filter)
}

function Tile({ label, value, note }) {
  return (
    <div className="admin-tile">
      <span className="admin-tile-label">{label}</span>
      <b>{value}</b>
      {note && <span className="admin-tile-note">{note}</span>}
    </div>
  )
}

function Daily({ days }) {
  const [hover, setHover] = useState(null)
  const top = Math.max(1, ...days.map((d) => d.questions))
  const shown = hover ?? days.length - 1
  const d = days[shown]
  return (
    <figure className="admin-chart">
      <figcaption className="rail-h">Questions per day <em>last {days.length} days</em></figcaption>
      <p className="admin-readout" aria-live="polite">{day(d.day)}: <b>{d.questions}</b> asked, {d.answered} answered, {d.failed} failed</p>
      <div className="admin-bars" onPointerLeave={() => setHover(null)}>
        {days.map((x, i) => (
          <button key={x.day} type="button" className={`admin-bar ${i === shown ? 'on' : ''}`} aria-label={`${day(x.day)}: ${x.questions} questions`}
            onPointerEnter={() => setHover(i)} onFocus={() => setHover(i)} onBlur={() => setHover(null)}>
            <i style={{ height: `${(x.questions / top) * 100}%` }} />
          </button>
        ))}
      </div>
      <div className="admin-axis"><span>{day(days[0].day)}</span><span>{top} max</span><span>{day(days.at(-1).day)}</span></div>
      <details className="admin-table-view">
        <summary>Show as a table</summary>
        <table><thead><tr><th>Day</th><th>Asked</th><th>Answered</th><th>Failed</th></tr></thead>
          <tbody>{days.map((x) => <tr key={x.day}><td>{day(x.day)}</td><td>{x.questions}</td><td>{x.answered}</td><td>{x.failed}</td></tr>)}</tbody>
        </table>
      </details>
    </figure>
  )
}

export default function Admin({ onAuthError }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')

  const load = useCallback(async () => {
    try {
      setData(await api('/api/admin'))
      setError('')
    } catch (err) {
      if (err.status === 401) onAuthError(err.message)
      else setError(err.message)
    }
  }, [onAuthError])

  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { load() }, [load])

  if (!data) return <div className="reports"><p className="rail-empty" role="status">{error || 'Loading product metrics'}</p></div>

  const w = data.week
  const events = data.events.filter((e) => matches(filter, e.action))
  return (
    <div className="reports admin">
      <header className="members-head">
        <div>
          <h2>Product admin</h2>
          <p className="lead">Every workspace, last 7 days. Questions and notes stay private: the log shows what happened, not what was asked.</p>
        </div>
        <button className="btn btn-outline" onClick={load}>Refresh</button>
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      <section className="admin-tiles" aria-label="Key numbers, last 7 days">
        <Tile label="Questions" value={num(w.questions)} note={`${data.active_workspaces} of ${data.workspaces_total} workspaces active`} />
        <Tile label="Answer rate" value={pct(w.answer_rate)} note={`${w.stopped} stopped, ${w.timeouts} timed out, ${w.errors} errors`} />
        <Tile label="Latency p50 / p95" value={`${secs(w.p50_s)} / ${secs(w.p95_s)}`} note={`${w.avg_steps ?? '–'} steps on average`} />
        <Tile label="Numbers grounded" value={pct(w.numbers_grounded)} note="answer figures found in tool output" />
        <Tile label="Tool error rate" value={pct(w.tool_error_rate)} note={`${w.placeholder_leaks} privacy placeholder leaks`} />
        <Tile label="Satisfaction" value={pct(w.satisfaction)} note={`${w.feedback_up} up, ${w.feedback_down} down`} />
        <Tile label="Web research" value={num(w.web_searches)} note={`${w.web_blocked} leaky queries blocked, ${w.web_learned} sources learned`} />
        <Tile label="Accounts" value={num(data.accounts)} note={`${data.members_total} workspace seats`} />
      </section>

      <div className="admin-grid">
        <section className="members-table"><Daily days={data.daily} /></section>
        <section className="members-table" aria-labelledby="fail-h">
          <h3 id="fail-h" className="rail-h">Recent failures</h3>
          {data.failures.length === 0 ? <p className="rail-empty">No errors or timeouts in the last {data.daily.length} days.</p> : (
            <ul className="audit">
              {data.failures.map((f, i) => (
                <li key={i} className="warn"><span className="chip">{f.status}</span><span>{f.workspace}: {f.message || 'no message'}</span><span className="mcp-when">{when(f.at)}</span></li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="members-table" aria-labelledby="ws-h">
        <h3 id="ws-h" className="rail-h">Workspaces</h3>
        <div className="admin-scroll">
          <table className="admin-ws">
            <thead><tr><th>Workspace</th><th>Seats</th><th>Questions</th><th>Answered</th><th>p50</th><th>Grounded</th><th>Web</th><th>Last active</th></tr></thead>
            <tbody>
              {data.workspaces.map((x) => (
                <tr key={x.id}>
                  <td><b>{x.name}</b><em>{x.id}</em></td><td>{x.members}</td><td>{x.questions}</td><td>{pct(x.answer_rate)}</td>
                  <td>{secs(x.p50_s)}</td><td>{pct(x.numbers_grounded)}</td><td>{x.web_searches}</td><td>{when(x.last_active)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="activity-panel" aria-labelledby="plog-h">
        <div className="members-tools">
          <h3 id="plog-h" className="rail-h">Product log <em>{events.length}</em></h3>
          <div className="filter-pills" role="group" aria-label="Filter the product log">
            {Object.entries(FILTERS).map(([k, label]) => (
              <button key={k} type="button" className={filter === k ? 'on' : ''} aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}</button>
            ))}
          </div>
        </div>
        {events.length === 0 ? <p className="rail-empty">Nothing here yet.</p> : (
          <ul className="audit">
            {events.map((e, i) => (
              <li key={i} className={e.action === 'denied' ? 'warn' : ''}>
                <span className="chip">{e.action}</span>
                <span>{e.workspace} · {e.user || 'system'}{Object.keys(e.detail).length > 0 && <em className="admin-detail"> {Object.entries(e.detail).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', ')}</em>}</span>
                <span className="mcp-when">{when(e.at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
