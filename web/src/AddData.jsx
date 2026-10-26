import { useCallback, useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, apiStream } from './api.js'
import Icon from './Icon.jsx'

const SOURCES = [
  { kind: 'upload', name: 'Upload a file', blurb: 'CSV, Excel, JSON or Parquet from your computer, up to 50 MB.' },
  { kind: 'sheets', name: 'Google Sheets', blurb: 'Sign in with Google and pick any sheet you can open. Refreshes daily.', google: true,
    fields: [{ id: 'sheet_url', label: 'Sheet link', placeholder: 'https://docs.google.com/spreadsheets/d/...' }] },
  { kind: 'ga4', name: 'Google Analytics 4', blurb: 'Sign in with Google and pick a property. Daily traffic, key events and revenue.', google: true },
  { kind: 'shopify', name: 'Shopify', blurb: 'Orders with line items and the products in them, last 12 months. Refreshes daily.',
    fields: [{ id: 'shop', label: 'Store domain', placeholder: 'yourstore.myshopify.com' }],
    secrets: [{ id: 'client_id', label: 'Client ID' }, { id: 'client_secret', label: 'Client secret', placeholder: 'shpss_...' }],
    steps: ['In Shopify admin, open Settings, then Apps, then Develop apps (it opens the Dev Dashboard).',
      'Create an app named Analyst Buddy and give it the read_orders and read_products scopes.', 'Install the app on your store.',
      'Copy the Client ID and Client secret from the app settings and paste them here.',
      'Shopify tokens expire every 24 hours; Analyst Buddy gets a fresh one by itself before every sync.'] },
  { kind: 'mcp', name: 'MCP server', blurb: 'Any MCP server: pick its read-only tools and their results become tables. Refreshes daily.', mcp: true },
  { kind: 'url', name: 'File link', blurb: 'A public link to a file. The data agent fetches and cleans it once.', agent: true,
    fields: [{ id: 'url', label: 'Link to the file', placeholder: 'https://example.com/sales.csv' }] },
  { kind: 'database', name: 'Database', blurb: 'Postgres or MySQL with a read-only user. Describe the data you need; the data agent writes the SQL and pulls it once.', agent: true,
    fields: [{ id: 'request', label: 'What data do you need?', optional: true, multiline: true, placeholder: 'e.g. paid orders from the North region in Q3 with customer names. Empty = the most useful tables.' }],
    secrets: [{ id: 'DATABASE_URL', label: 'Connection URL', placeholder: 'postgresql://readonly:password@host:5432/shop' }] },
  { kind: 'other', name: 'Something else', blurb: 'Describe any source in plain words; the data agent works out how to pull it.', agent: true,
    fields: [{ id: 'description', label: 'What should it pull, and from where?', multiline: true, placeholder: 'e.g. daily order counts from https://api.example.com/orders' }],
    secrets: [{ id: 'SOURCE_SECRET', label: 'Password, key or token', optional: true }] },
]
const firstLine = (text = '') => text.split('\n').find((l) => l.trim() && !/^(STDOUT|STDERR|RESULT):$/.test(l.trim())) ?? ''
const ago = (iso) => {
  if (!iso) return 'never'
  const min = Math.round((Date.now() - new Date(iso)) / 60000)
  return min < 1 ? 'just now' : min < 60 ? `${min} min ago` : min < 1440 ? `${Math.round(min / 60)} h ago` : `${Math.round(min / 1440)} d ago`
}

function McpSource({ onSaved, fail }) {
  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [grant, setGrant] = useState('')
  const [needsSignin, setNeedsSignin] = useState(false)
  const [found, setFound] = useState(null)
  const [picked, setPicked] = useState({})
  const [busy, setBusy] = useState('')

  async function find(e, withGrant = grant) {
    e?.preventDefault()
    setBusy('find')
    setFound(null)
    setPicked({})
    try {
      const res = await api('/api/connections/mcp/inspect', { method: 'POST', body: { url, token, grant: withGrant } })
      if (res.needs_signin) {
        setNeedsSignin(true)
        return
      }
      setFound(res)
    } catch (err) {
      fail(err)
    } finally {
      setBusy('')
    }
  }

  async function signIn() {
    const popup = window.open('', 'mcp-signin', 'width=520,height=760')
    setBusy('signin')
    try {
      const { grant: id, url: authUrl } = await api('/api/connections/mcp/signin', { method: 'POST', body: { url } })
      if (popup) popup.location.href = authUrl
      else window.open(authUrl, 'mcp-signin')
      for (let i = 0; i < 200; i += 1) {
        await new Promise((r) => setTimeout(r, 1500))
        const s = await api(`/api/connections/mcp/signin/${id}`)
        if (s.status === 'waiting' && popup?.closed) throw new Error('The sign-in window was closed before it finished. If it showed an error, this server does not accept Analyst Buddy.')
        if (s.status === 'error') throw new Error(s.message)
        if (s.status === 'ready') {
          setGrant(id)
          setNeedsSignin(false)
          return find(null, id)
        }
      }
      throw new Error('The sign-in timed out. Try again.')
    } catch (err) {
      popup?.close()
      fail(err)
      setBusy('')
    }
  }

  const toggle = (t) => setPicked((all) => {
    const next = { ...all }
    if (next[t.name]) delete next[t.name]
    else next[t.name] = Object.fromEntries(t.required.map((r) => [r, '']))
    return next
  })
  const setArg = (name, key) => (e) => setPicked((all) => ({ ...all, [name]: { ...all[name], [key]: e.target.value } }))
  const chosen = Object.entries(picked)
  const filled = (v) => typeof v !== 'string' || v.trim()
  const ready = chosen.length > 0 && chosen.length <= 10 && chosen.every(([, args]) => Object.values(args).every(filled))

  async function save() {
    setBusy('save')
    try {
      const tools = chosen.map(([name, args]) => ({ name, args: Object.fromEntries(Object.entries(args).map(([k, v]) => [k, typeof v === 'string' ? v.trim() : v])) }))
      await api('/api/connections', { method: 'POST', body: { kind: 'mcp', config: { url: url.trim(), tools }, secrets: grant ? { grant } : { token: token.trim() } } })
      onSaved()
    } catch (err) {
      fail(err)
      setBusy('')
    }
  }

  const signinButton = (
    <button type="button" className={`btn btn-block ${needsSignin ? 'btn-blue' : 'btn-outline'}`} onClick={signIn} disabled={!url.trim() || !!busy}>
      {busy === 'signin' ? <><span className="mini-spin" aria-hidden="true" />Waiting for you to sign in</> : 'Sign in'}
    </button>
  )

  return (
    <div className="member-form">
      <form className="member-form" onSubmit={find}>
          <label className="field"><span>MCP server URL</span>
            <input value={url} onChange={(e) => { setUrl(e.target.value); setGrant(''); setNeedsSignin(false) }} placeholder="https://mcp.example.com/mcp" disabled={!!busy} required />
          </label>
          {!grant && (
            <label className="field"><span><Icon name="lock" size={14} />API token <em>(optional)</em></span>
              <input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Only if the server needs one" disabled={!!busy} />
            </label>
          )}
          <button className="btn btn-outline btn-block" disabled={!url.trim() || !!busy}>
            {busy === 'find' ? <><span className="mini-spin" aria-hidden="true" />Connecting</> : 'Find tools'}
          </button>
        </form>
      {needsSignin && !grant && <><p className="note">This server needs you to sign in. A window opens; approve there and come back.</p>{signinButton}</>}
      {grant && <p className="note">✓ Signed in. Analyst Buddy only uses the read-only tools you pick.</p>}
      {found && (
        <section className="mcp-tools-pick" aria-label="Tools on this server">
          {found.signin && !grant && <><p className="note">This server also offers sign-in, which some tools need to return your data.</p>{signinButton}</>}
          <p className="mcp-server-name"><b>{found.server}</b> has {found.tools.length} tools. Pick the read-only ones whose results you want as tables.</p>
          <ul>
            {found.tools.map((t) => (
              <li key={t.name} className={t.blocked ? 'is-blocked' : picked[t.name] ? 'is-on' : ''}>
                <label className="check">
                  <input type="checkbox" checked={!!picked[t.name]} disabled={!!t.blocked || !!busy} onChange={() => toggle(t)} />
                  <code>{t.name}</code>
                </label>
                {t.description && <p className="tool-desc">{t.description}</p>}
                {t.blocked && <p className="tool-blocked">Locked: {t.blocked}</p>}
                {picked[t.name] && t.required.map((r) => (
                  <label key={r} className="field tool-arg"><span>{r}</span>
                    <input value={picked[t.name][r] ?? ''} onChange={setArg(t.name, r)} disabled={!!busy} />
                  </label>
                ))}
              </li>
            ))}
          </ul>
          <p className="note">{grant ? 'Your sign-in is saved encrypted and renewed automatically.' : 'The token is tested, then saved encrypted.'} Results become tables, refresh daily, and are treated as data, never as instructions.</p>
          <button type="button" className="btn btn-blue btn-block" onClick={save} disabled={!ready || !!busy}>
            {busy === 'save' ? <><span className="mini-spin" aria-hidden="true" />Testing and importing</> : `Test and connect ${chosen.length || ''} tool${chosen.length === 1 ? '' : 's'}`}
          </button>
        </section>
      )}
    </div>
  )
}

function Logo({ kind, size = 34 }) {
  return <img className="source-logo" src={`/icons/sources/${kind}.png`} alt="" width={size} height={size} style={{ width: size, height: size }} />
}

export default function AddData({ onPickFile, onSession, onAuthError, googleResult }) {
  const [source, setSource] = useState(null)
  const [values, setValues] = useState({})
  const [conns, setConns] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(googleResult === 'failed' ? 'Google did not connect. Try again and allow both permissions.' : '')
  const [properties, setProperties] = useState(null)
  const [steps, setSteps] = useState([])
  const [tables, setTables] = useState([])
  const [result, setResult] = useState(null)

  const fail = useCallback((err) => (err.status === 401 ? onAuthError(err.message) : setError(err.message)), [onAuthError])
  const load = useCallback(() => api('/api/connections').then(setConns).catch(fail), [fail])
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { load() }, [load])
  const syncing = conns?.items.some((c) => c.syncing || c.status === 'syncing')
  useEffect(() => {
    if (!syncing) return
    const id = setInterval(() => {
      load()
      api('/api/me').then(onSession).catch(() => {})
    }, 3000)
    return () => clearInterval(id)
  }, [syncing, load, onSession])
  const wantsProperties = source?.kind === 'ga4' && Boolean(conns?.google) && !properties
  useEffect(() => {
    if (!wantsProperties) return
    api('/api/connections/ga4/properties').then((r) => setProperties(r.properties)).catch(fail)
  }, [wantsProperties, fail])

  const set = (id) => (e) => setValues({ ...values, [id]: e.target.value })
  const fields = source?.kind === 'ga4' ? [{ id: 'property_id', label: 'Property' }] : (source?.fields ?? [])
  const secrets = source?.secrets ?? []
  const ready = source && [...fields, ...secrets].every((f) => f.optional || values[f.id]?.trim())

  function choose(s) {
    if (s.kind === 'upload') return onPickFile()
    setSource(s)
    setValues({})
    setError('')
    setSteps([])
    setTables([])
    setResult(null)
  }

  async function connectGoogle() {
    try {
      const { url } = await api('/api/connections/google/start')
      window.location.assign(url)
    } catch (err) {
      fail(err)
    }
  }

  async function act(fn) {
    setError('')
    try {
      await fn()
      await load()
    } catch (err) {
      fail(err)
    }
  }

  async function save(e) {
    e.preventDefault()
    if (!ready || busy) return
    setBusy(true)
    setError('')
    if (!source.agent) {
      const pick = (list) => Object.fromEntries(list.map((f) => [f.id, values[f.id]?.trim() ?? '']))
      try {
        await api('/api/connections', { method: 'POST', body: { kind: source.kind, config: pick(fields), secrets: pick(secrets) } })
        setSource(null)
        await load()
      } catch (err) {
        fail(err)
      } finally {
        setBusy(false)
      }
      return
    }
    const details = fields.filter((f) => values[f.id]?.trim()).map((f) => `${f.label}: ${values[f.id].trim()}`).join('\n')
    const keys = Object.fromEntries(secrets.filter((f) => values[f.id]?.trim()).map((f) => [f.id, values[f.id].trim()]))
    setSteps([])
    setTables([])
    setResult(null)
    try {
      await apiStream('/api/sources', { kind: source.kind, details, secrets: keys }, (ev) => {
        if (ev.type === 'call') setSteps((all) => [...all, { id: ev.id, tool: ev.tool, code: ev.args.code ?? `${ev.args.name ?? ''}`, output: null }])
        else if (ev.type === 'output') setSteps((all) => all.map((st) => (st.id === ev.id ? { ...st, output: ev.output } : st)))
        else if (ev.type === 'table') setTables((all) => [...all, ev])
        else if (ev.type === 'done' || ev.type === 'error') {
          onSession(ev.session)
          setResult(ev.type === 'done' ? { ok: ev.tables.length > 0, note: ev.note } : { ok: false, note: ev.message })
        }
      })
      setValues({})
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  if (!source) {
    return (
      <div className="add-data">
        {googleResult === 'connected' && conns?.google && <p className="members-notice" role="status">Google connected as {conns.google.email}. Pick Google Sheets or Google Analytics below.</p>}
        {error && <p className="error" role="alert">{error}</p>}
        {conns?.items.length > 0 && (
          <section aria-labelledby="conn-h" className="conn-list">
            <h3 id="conn-h" className="rail-h">Connected sources</h3>
            <ul>
              {conns.items.map((c) => {
                const running = c.syncing || c.status === 'syncing'
                return (
                  <li key={c.id} className={`conn conn-${running ? 'syncing' : c.status}`}>
                    <Logo kind={c.kind} size={28} />
                    <span className="conn-main">
                      <span><b>{c.name}</b> <span className="conn-label">{c.label}</span></span>
                      <span className="conn-meta">
                        {running ? 'Syncing now' : c.status === 'error' ? c.message
                          : c.last_sync ? `${c.rows.toLocaleString()} rows in ${c.tables.length} table${c.tables.length === 1 ? '' : 's'} · synced ${ago(c.last_sync)} · refreshes daily`
                          : 'Connected. First sync starting.'}
                      </span>
                    </span>
                    <span className="conn-actions">
                      <button className="btn btn-ghost" disabled={running} onClick={() => act(() => api(`/api/connections/${c.id}/sync`, { method: 'POST' }))}>
                        {running ? <span className="mini-spin" aria-label="Syncing" /> : 'Refresh'}
                      </button>
                      <button className="btn btn-ghost danger" aria-label={`Disconnect ${c.name} ${c.label}`}
                        onClick={() => window.confirm(`Disconnect ${c.name} (${c.label})? Its saved keys are deleted; tables already imported stay.`) && act(() => api(`/api/connections/${c.id}`, { method: 'DELETE' }))}>
                        Disconnect
                      </button>
                    </span>
                  </li>
                )
              })}
            </ul>
          </section>
        )}
        <p className="lead">Pick where your data lives. App connections are saved and refresh every day; the <b>data agent</b> handles one-off files, databases and anything else.</p>
        <ul className="source-grid">
          {SOURCES.map((s) => (
            <li key={s.kind}>
              <button className="source-card" onClick={() => choose(s)}>
                <Logo kind={s.kind} />
                <span className="source-name">{s.name}</span>
                <span className="source-blurb">{s.blurb}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    )
  }

  const needsGoogle = source.google && conns && !conns.google
  return (
    <div className="add-data">
      <button className="link back-link" onClick={() => !busy && setSource(null)} disabled={busy}>← All sources</button>
      <h3 className="source-title"><Logo kind={source.kind} />{source.name}</h3>
      <p className="lead">{source.blurb}</p>
      {error && <p className="error" role="alert">{error}</p>}
      {source.mcp ? <McpSource fail={fail} onSaved={() => { setSource(null); load() }} /> : needsGoogle ? (
        conns.google_ready ? (
          <div className="google-connect">
            <p className="note">You sign in with Google and allow read-only access to Sheets and Analytics. Remove it any time at myaccount.google.com/permissions.</p>
            <button className="btn btn-blue btn-block" onClick={connectGoogle}>Connect Google</button>
          </div>
        ) : <p className="note">Google connections need GOOGLE_CLIENT_SECRET on the server. Ask whoever runs Analyst Buddy to add it.</p>
      ) : (
        <form className="member-form" onSubmit={save}>
          {source.google && conns?.google && (
            <p className="conn-google">Google account: <b>{conns.google.email}</b>{' '}
              <button type="button" className="link" onClick={() => window.confirm('Disconnect Google? Its Sheets and Analytics sources are removed too.') && act(() => api('/api/connections/google', { method: 'DELETE' }))}>Disconnect</button>
            </p>
          )}
          {source.steps && (
            <details className="setup-steps" open>
              <summary>How to get this (2 minutes)</summary>
              <ol>{source.steps.map((st) => <li key={st}>{st}</li>)}</ol>
            </details>
          )}
          {fields.map((f) => (
            <label key={f.id} className="field"><span>{f.label}{f.optional && <em> (optional)</em>}</span>
              {f.id === 'property_id' ? (
                <select value={values.property_id ?? ''} onChange={set('property_id')} disabled={busy || !properties}>
                  <option value="">{properties ? (properties.length ? 'Pick a property' : 'No properties on this Google account') : 'Loading properties'}</option>
                  {properties?.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.id})</option>)}
                </select>
              ) : f.multiline ? <textarea rows={3} value={values[f.id] ?? ''} onChange={set(f.id)} placeholder={f.placeholder} disabled={busy} />
                : <input value={values[f.id] ?? ''} onChange={set(f.id)} placeholder={f.placeholder} disabled={busy} />}
            </label>
          ))}
          {secrets.map((f) => (
            <label key={f.id} className="field"><span><Icon name="lock" size={14} />{f.label}{f.optional && <em> (optional)</em>}</span>
              <input type="password" autoComplete="off" value={values[f.id] ?? ''} onChange={set(f.id)} placeholder={f.placeholder} disabled={busy} />
            </label>
          ))}
          {secrets.length > 0 && (
            <p className="note">{source.agent
              ? 'Keys go only to the data agent\'s private sandbox for this one import. The AI never sees them, and they are not saved.'
              : 'Keys are tested first, then saved encrypted on the server so the daily refresh works. The AI never sees them, and Disconnect deletes them.'}</p>
          )}
          <button className="btn btn-blue btn-block" disabled={!ready || busy}>
            {busy ? <><span className="mini-spin" aria-hidden="true" />{source.agent ? 'Data agent is working' : 'Testing the connection'}</>
              : source.agent ? 'Import with the data agent' : 'Test and connect'}
          </button>
        </form>
      )}

      {(steps.length > 0 || (busy && source.agent)) && (
        <ol className="agent-steps" aria-label="Data agent steps" aria-live="polite">
          {steps.map((st, i) => (
            <li key={st.id}>
              <b>{i + 1}. {st.tool === 'save_table' ? 'Handing a table to the analyst' : 'Running code'}</b>
              <code>{firstLine(st.code)}</code>
              <span className="step-out">{st.output != null ? firstLine(st.output) : 'working'}</span>
            </li>
          ))}
        </ol>
      )}
      {tables.length > 0 && <p className="tables-added">{tables.map((t) => <span key={t.name} className="chip chip-all"><Icon name="file" size={14} />{t.name}</span>)}</p>}
      {result && (
        <div className={`agent-note ${result.ok ? '' : 'is-error'}`} role="status">
          <b>{result.ok ? 'Data agent to analyst' : 'Not connected'}</b>
          <div className="agent-note-body"><Markdown remarkPlugins={[remarkGfm]}>{result.note}</Markdown></div>
        </div>
      )}
    </div>
  )
}
