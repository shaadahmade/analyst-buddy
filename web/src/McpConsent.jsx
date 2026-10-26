import { useEffect, useState } from 'react'
import { api, saveToken } from './api.js'
import Icon from './Icon.jsx'
import ThemeToggle from './ThemeToggle.jsx'

const READ_TOOLS = 'list tables, describe tables, ask the analyst, read weekly reports'

export default function McpConsent({ rid, session, setSession, onFinish, onAuthError }) {
  const [info, setInfo] = useState(null)
  const [error, setError] = useState('')
  const [access, setAccess] = useState('read')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api(`/api/mcp/oauth/${rid}`)
      .then((r) => { setInfo(r); setAccess(r.access) })
      .catch((err) => (err.status === 401 ? onAuthError(err.message) : setError(err.message)))
  }, [rid, onAuthError])

  async function switchTo(id) {
    setBusy(true)
    try {
      const { token, ...next } = await api(`/api/workspaces/${id}/open`, { method: 'POST' })
      saveToken(token)
      setSession(next)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function decide(allow) {
    setBusy(true)
    setError('')
    try {
      const { redirect } = await api(`/api/mcp/oauth/${rid}`, { method: 'POST', body: { allow, access } })
      onFinish()
      window.location.assign(redirect)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="signin-page">
      <nav className="topbar">
        <span className="wordmark"><Icon name="logo" size={22} />Analyst Buddy</span>
        <ThemeToggle />
      </nav>
      <main className="board-frame signin-frame">
        <div className="board consent-board">
          <div className="magnet-card consent-card">
            <span className="magnet" aria-hidden="true" />
            {!info ? (
              <div className="consent-body">
                <h1 className="card-title">Connect an AI app</h1>
                <p className="error" role="alert">{error || 'Loading the request'}</p>
                {error && <button className="btn btn-outline btn-block" onClick={onFinish}>Back to Analyst Buddy</button>}
              </div>
            ) : (
              <div className="consent-body">
                <h1 className="card-title"><b>{info.client_name}</b> wants to use Analyst Buddy</h1>
                <p className="card-text">Signed in as <b>{session.user}</b>. After you approve, you go back to <b>{info.redirect_host}</b>.</p>
                <label className="field"><span>Workspace</span>
                  <select value={session.tenant} disabled={busy} onChange={(e) => switchTo(e.target.value)}>
                    {session.workspaces.map((w) => <option key={w.id} value={w.id}>{w.name} ({w.role})</option>)}
                  </select>
                </label>
                <fieldset className="mcp-access">
                  <legend>What it can do</legend>
                  <label className="check"><input type="radio" checked={access === 'read'} onChange={() => setAccess('read')} disabled={busy} />Read only <em>(recommended)</em></label>
                  <p className="consent-hint">{READ_TOOLS}</p>
                  <label className="check"><input type="radio" checked={access === 'full'} onChange={() => setAccess('full')} disabled={busy} />Everything my role ({session.role}) allows</label>
                </fieldset>
                <p className="note">Your data limits and role always apply. You can disconnect it any time under Connect AI.</p>
                {error && <p className="error" role="alert">{error}</p>}
                <div className="consent-actions">
                  <button className="btn btn-outline" onClick={() => decide(false)} disabled={busy}>Deny</button>
                  <button className="btn btn-blue" onClick={() => decide(true)} disabled={busy}>{busy ? 'Connecting' : 'Approve'}</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
