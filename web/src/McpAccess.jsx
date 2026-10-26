import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'

const TOOLS = [
  ['list_tables', null, 'See the tables you can access'],
  ['describe_table', null, 'Columns and sample rows'],
  ['ask_analyst', null, 'Ask the agent team a question'],
  ['list_reports', 'reports', 'List weekly reports'],
  ['get_report', 'reports', 'Read a weekly report'],
  ['list_connections', 'upload', 'See saved data connections'],
  ['sync_connection', 'upload', 'Refresh a connection'],
  ['add_data_from_link', 'upload', 'Import a file from a link'],
  ['create_report_now', 'reports.manage', 'Start this week\'s report'],
  ['list_members', 'users', 'List members and roles'],
  ['activity_log', 'users', 'Read the activity log'],
]
const READ = ['reports']
const APPS = [
  { key: 'claude', name: 'Claude', where: 'claude.ai, Claude Desktop and Claude Code', match: /claude|anthropic/i },
  { key: 'chatgpt', name: 'ChatGPT', where: 'ChatGPT Plugins, Add custom MCP', match: /chatgpt|openai/i },
  { key: 'gemini', name: 'Gemini', where: 'Gemini CLI', match: /gemini|google/i },
]
const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'never')
const appOf = (name) => APPS.find((a) => a.match.test(name))

function Copy({ text, label = 'Copy', dark }) {
  const [done, setDone] = useState(false)
  return (
    <button type="button" className={`btn btn-ghost copy-btn ${dark ? 'on-dark' : ''}`}
      onClick={() => navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500) })}>
      {done ? 'Copied' : label}
    </button>
  )
}

function Code({ text }) {
  return <div className="mcp-snippet"><pre>{text}</pre><Copy text={text} dark /></div>
}

function Steps({ app, url }) {
  if (app === 'claude') {
    return (
      <ol className="app-steps">
        <li>In <b>claude.ai</b> or Claude Desktop, open <b>Settings → Connectors</b> and click <b>Add custom connector</b>.</li>
        <li>Name it <b>Analyst Buddy</b> and paste this URL: <Code text={url} /></li>
        <li>Click <b>Continue</b>. Analyst Buddy opens: sign in, pick the workspace and <b>Read only</b> or <b>Full</b>, then <b>Approve</b>.</li>
        <li>In a chat, turn on <b>Analyst Buddy</b> in the tools menu and ask: “list my tables, then tell me why orders dropped”.</li>
        <li className="app-alt">Claude Code (terminal) works too: <Code text={`claude mcp add --transport http analyst-buddy ${url}`} />then run <code>/mcp</code> in Claude Code and choose <b>Authenticate</b>.</li>
      </ol>
    )
  }
  if (app === 'chatgpt') {
    return (
      <ol className="app-steps">
        <li>In ChatGPT, open <b>Plugins</b> and click <b>Add custom MCP</b>. Availability depends on your ChatGPT plan.</li>
        <li>Name it <b>Analyst Buddy</b> and paste this MCP server URL: <Code text={url} /></li>
        <li>Choose <b>OAuth</b> for authentication and leave Client ID and Secret empty; ChatGPT registers itself.</li>
        <li>Click <b>Add</b>. Analyst Buddy opens: sign in, pick the workspace and access, then <b>Approve</b>.</li>
        <li>In a new chat, open the <b>+</b> menu and switch on <b>Analyst Buddy</b> under Plugins.</li>
      </ol>
    )
  }
  return (
    <ol className="app-steps">
      <li>Install Gemini CLI if needed: <Code text="npm install -g @google/gemini-cli" /></li>
      <li>Add Analyst Buddy to <code>~/.gemini/settings.json</code> (inside <code>mcpServers</code>): <Code text={JSON.stringify({ mcpServers: { 'analyst-buddy': { httpUrl: url, oauth: { enabled: true } } } }, null, 2)} /></li>
      <li>Start <code>gemini</code> and run <Code text="/mcp auth analyst-buddy" />Your browser opens Analyst Buddy: sign in, pick the workspace and access, then <b>Approve</b>.</li>
      <li>Run <code>/mcp</code> to see the tools, then ask: “use analyst-buddy to explain last week's revenue”.</li>
      <li className="app-alt">The Gemini web and phone apps do not support custom MCP servers yet; Gemini CLI does.</li>
    </ol>
  )
}

export default function McpAccess({ session, onAuthError }) {
  const [data, setData] = useState(null)
  const [openApp, setOpenApp] = useState(null)
  const [name, setName] = useState('')
  const [access, setAccess] = useState('read')
  const [fresh, setFresh] = useState(null)
  const [error, setError] = useState('')
  const fail = useCallback((err) => (err.status === 401 ? onAuthError(err.message) : setError(err.message)), [onAuthError])
  const load = useCallback(() => api('/api/mcp/tokens').then(setData).catch(fail), [fail])
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { load() }, [load])

  const perms = access === 'read' ? session.permissions.filter((p) => READ.includes(p)) : session.permissions
  const usable = TOOLS.filter(([, perm]) => perm === null || perms.includes(perm))

  async function create(e) {
    e.preventDefault()
    setError('')
    try {
      setFresh(await api('/api/mcp/tokens', { method: 'POST', body: { name, access } }))
      setName('')
      load()
    } catch (err) {
      fail(err)
    }
  }

  async function revoke(t) {
    if (!window.confirm(`Disconnect "${t.name}"? It stops working right away.`)) return
    try {
      await api(`/api/mcp/tokens/${t.id}`, { method: 'DELETE' })
      if (fresh?.id === t.id) setFresh(null)
      load()
    } catch (err) {
      fail(err)
    }
  }

  if (!data) return <div className="reports"><p className="rail-empty" role="status">{error || 'Loading'}</p></div>
  const mine = data.tokens.filter((t) => t.u === session.user)
  const json = fresh && JSON.stringify({ mcpServers: { 'analyst-buddy': { url: data.url, headers: { Authorization: `Bearer ${fresh.token}` } } } }, null, 2)

  return (
    <div className="reports mcp-page">
      <header className="members-head">
        <div>
          <h2>Connect AI apps</h2>
          <p className="lead">Ask Analyst Buddy from Claude, ChatGPT or Gemini. You sign in once and approve; your role ({session.role}) and data limits always apply.</p>
        </div>
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      <section className="mcp-url" aria-label="Server URL">
        <span className="team-phase">MCP server URL</span>
        <div className="mcp-url-row"><code>{data.url}</code><Copy text={data.url} /></div>
      </section>

      <ul className="app-grid">
        {APPS.map((app) => {
          const links = mine.filter((t) => app.match.test(t.name))
          const isOpen = openApp === app.key
          return (
            <li key={app.key} className={`app-card ${isOpen ? 'is-open' : ''}`}>
              <img className="app-logo" src={`/icons/ai/${app.key}.png`} alt="" width="48" height="48" />
              <div className="app-text">
                <h3>{app.name}</h3>
                <p>{app.where}</p>
              </div>
              <span className={`app-status ${links.length ? 'on' : ''}`}>{links.length ? `Connected${links.length > 1 ? ` ×${links.length}` : ''}` : 'Not connected'}</span>
              <button className={`btn ${isOpen ? 'btn-outline' : 'btn-blue'} app-btn`} aria-expanded={isOpen} onClick={() => setOpenApp(isOpen ? null : app.key)}>
                {isOpen ? 'Hide steps' : links.length ? 'Connect again' : 'Connect'}
              </button>
            </li>
          )
        })}
      </ul>

      {openApp && (
        <section className="members-table app-guide" aria-label={`Connect ${APPS.find((a) => a.key === openApp).name}`}>
          <h3 className="app-guide-title">
            <img src={`/icons/ai/${openApp}.png`} alt="" width="28" height="28" />Connect {APPS.find((a) => a.key === openApp).name}
          </h3>
          <Steps app={openApp} url={data.url} />
          <p className="note">On the Approve screen, <b>Read only</b> gives: list tables, describe tables, ask the analyst and read weekly reports. <b>Full</b> gives everything your role allows.</p>
        </section>
      )}

      <section className="members-table" aria-labelledby="tok-h">
        <div className="members-tools"><h3 id="tok-h" className="rail-h">{data.can_manage_all ? 'Connected apps and tokens in this workspace' : 'Your connected apps and tokens'} <em>{data.tokens.length}</em></h3></div>
        {data.tokens.length ? (
          <ul className="mcp-list">
            {data.tokens.map((t) => {
              const app = appOf(t.name)
              return (
                <li key={t.id}>
                  <span className="mcp-name">
                    {app ? <img src={`/icons/ai/${app.key}.png`} alt="" width="26" height="26" /> : <span className="mcp-key" aria-hidden="true">⌘</span>}
                    <span><b>{t.name}</b>{data.can_manage_all && <em>{t.u}</em>}</span>
                  </span>
                  <span className={`chip ${t.access === 'read' ? 'chip-all' : ''}`}>{t.access === 'read' ? 'Read only' : 'Full role'}</span>
                  <span className="mcp-when">{t.kind === 'pat' ? 'Token' : 'Signed in'} {when(t.created)} · last used {when(t.last_used)}</span>
                  <button className="btn btn-ghost danger" onClick={() => revoke(t)}>Disconnect</button>
                </li>
              )
            })}
          </ul>
        ) : <p className="rail-empty">Nothing connected yet. Pick an app above.</p>}
      </section>

      <details className="members-table mcp-advanced">
        <summary>Other MCP clients (Cursor, VS Code, scripts): use a personal token</summary>
        <div className="mcp-grid">
          <form className="mcp-create" onSubmit={create}>
            <label className="field"><span>Token name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder="e.g. Cursor on my laptop" />
            </label>
            <fieldset className="mcp-access">
              <legend>Access</legend>
              <label className="check"><input type="radio" checked={access === 'read'} onChange={() => setAccess('read')} />Read only <em>(recommended)</em></label>
              <label className="check"><input type="radio" checked={access === 'full'} onChange={() => setAccess('full')} />Everything my role allows</label>
            </fieldset>
            <div className="mcp-tools">
              <span className="team-phase">This token gets {usable.length} tools</span>
              <ul>{usable.map(([tool, , what]) => <li key={tool}><code>{tool}</code>{what}</li>)}</ul>
            </div>
            <button className="btn btn-outline btn-block">Create token</button>
          </form>
          {fresh && (
            <div className="mcp-fresh" aria-live="polite">
              <p className="note">Copy it now. It is shown only once.</p>
              <Code text={fresh.token} />
              <span className="team-phase">JSON config (Cursor and most clients)</span>
              <Code text={json} />
            </div>
          )}
        </div>
      </details>
    </div>
  )
}
