import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import Icon from './Icon.jsx'
import Sheet from './Sheet.jsx'

const ROLES = {
  owner: 'Everything, including owners and company data',
  admin: 'Manages members, data, reports and schedule',
  analyst: 'Asks, uploads data and teaches the analyst',
  viewer: 'Asks and reads reports; what they teach stays personal',
}
const list = (text) => text.split(',').map((s) => s.trim()).filter(Boolean)
const canScope = (role) => role === 'analyst' || role === 'viewer'

function toRules(scope, files) {
  return Object.fromEntries(files.map((f) => {
    const rule = scope?.[f]
    const [column = '', values = []] = Object.entries(rule?.rows ?? {})[0] ?? []
    return [f, { on: Boolean(rule), column, values: values.join(', '), hide: (rule?.hide ?? []).join(', ') }]
  }))
}

function toScope(limited, rules) {
  if (!limited) return null
  return Object.fromEntries(Object.entries(rules).filter(([, r]) => r.on).map(([f, r]) => [f, {
    rows: r.column.trim() && list(r.values).length ? { [r.column.trim()]: list(r.values) } : {},
    hide: list(r.hide),
  }]))
}

function MemberForm({ member, files, me, onSaved, onError }) {
  const isNew = !member
  const [email, setEmail] = useState(member?.email ?? '')
  const [role, setRole] = useState(member?.role ?? 'analyst')
  const [password, setPassword] = useState('')
  const [limited, setLimited] = useState(Boolean(member?.scope))
  const [rules, setRules] = useState(() => toRules(member?.scope, files))
  const [msg, setMsg] = useState('')
  const roles = Object.keys(ROLES).filter((r) => me.role === 'owner' || r !== 'owner')
  const setRule = (f, k) => (e) => setRules({ ...rules, [f]: { ...rules[f], [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value } })

  async function save(e) {
    e.preventDefault()
    setMsg('')
    const body = { email, role, scope: canScope(role) ? toScope(limited, rules) : null, password: isNew ? password || null : null }
    try {
      const saved = await api(isNew ? '/api/users' : `/api/users/${encodeURIComponent(member.email)}`, { method: isNew ? 'POST' : 'PUT', body })
      onSaved(isNew ? `${saved.email} is in. ${{ password: 'Share the first password with them privately.', google: 'They sign in with Google using that email.', existing: 'They see this workspace next time they sign in.' }[saved.joins]}` : `Saved ${saved.email}. They were signed out so the change applies now.`)
    } catch (err) {
      onError(err, setMsg)
    }
  }

  return (
    <form className="member-form" onSubmit={save}>
      {isNew && (
        <label className="field"><span>Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="name@yourcompany.com" />
        </label>
      )}
      <label className="field"><span>Role</span>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          {roles.map((r) => <option key={r} value={r}>{r[0].toUpperCase() + r.slice(1)}</option>)}
        </select>
        <em>{ROLES[role]}</em>
      </label>
      {isNew && (
        <label className="field"><span>First password <em>(only for new people who won't use Google)</em></span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} autoComplete="new-password" />
        </label>
      )}
      {canScope(role) && (
        <fieldset className="scope">
          <legend>Data access</legend>
          <label className="check"><input type="radio" checked={!limited} onChange={() => setLimited(false)} />All company data</label>
          <label className="check"><input type="radio" checked={limited} onChange={() => setLimited(true)} />Only the data I choose</label>
          {limited && (files.length ? files.map((f) => (
            <div className="scope-file" key={f}>
              <label className="check"><input type="checkbox" checked={rules[f].on} onChange={setRule(f, 'on')} /><Icon name="file" size={16} />{f}</label>
              {rules[f].on && (
                <div className="scope-rule">
                  <label className="field"><span>Only rows where column</span><input value={rules[f].column} onChange={setRule(f, 'column')} placeholder="region" /></label>
                  <label className="field"><span>is one of <em>(comma separated)</em></span><input value={rules[f].values} onChange={setRule(f, 'values')} placeholder="North, East" /></label>
                  <label className="field wide"><span>Hide columns <em>(comma separated)</em></span><input value={rules[f].hide} onChange={setRule(f, 'hide')} placeholder="customer_email, cost" /></label>
                </div>
              )}
            </div>
          )) : <p className="rail-empty">No data files yet.</p>)}
          {limited && <p className="note">Limited members can't upload, read company reports or see what others taught the analyst, because those are built from all the data.</p>}
        </fieldset>
      )}
      <button className="btn btn-blue btn-block">{isNew ? 'Add member' : 'Save changes'}</button>
      {msg && <p className="feedback-msg" role="status">{msg}</p>}
    </form>
  )
}

const KINDS = {
  all: { label: 'All', test: () => true },
  access: { label: 'Sign-ins', test: (e) => e.action.startsWith('login') },
  ask: { label: 'Questions', test: (e) => e.action === 'ask' },
  change: { label: 'Changes', test: (e) => /member|upload|report|workspace/.test(e.action) },
  denied: { label: 'Denied', test: (e) => e.action === 'denied' || e.action === 'login failed' },
}
const TINTS = ['tint-a', 'tint-b', 'tint-c', 'tint-d']
const tint = (email) => TINTS[[...email].reduce((n, c) => n + c.charCodeAt(0), 0) % TINTS.length]
const when = (at) => new Date(at).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

function Avatar({ email }) {
  return <span className={`avatar ${tint(email)}`} aria-hidden="true">{email.slice(0, 1).toUpperCase()}</span>
}

function AccessChips({ scope }) {
  if (!scope) return <span className="chip chip-all">All data</span>
  const files = Object.keys(scope)
  if (!files.length) return <span className="chip chip-none">No data</span>
  return files.map((f) => {
    const rows = Object.entries(scope[f].rows).map(([c, v]) => `${c}: ${v.join(', ')}`)
    const hide = scope[f].hide.length ? [`hides ${scope[f].hide.join(', ')}`] : []
    return (
      <span key={f} className="chip" title={[f, ...rows, ...hide].join(' · ')}>
        <Icon name="file" size={14} />{f}{rows.length + hide.length > 0 && <em>limited</em>}
      </span>
    )
  })
}

export default function Members({ me, onAuthError }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState('all')
  const [sheet, setSheet] = useState(null)
  const handle = useCallback((err, show) => (err.status === 401 ? onAuthError(err.message) : show(err.message)), [onAuthError])

  const load = useCallback(() => api('/api/users').then(setData).catch((err) => handle(err, setError)), [handle])
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { load() }, [load])

  function saved(message) {
    setSheet(null)
    setNotice(message)
    load()
  }

  async function changeRole(u, role) {
    setError('')
    try {
      await api(`/api/users/${encodeURIComponent(u.email)}`, { method: 'PUT', body: { email: u.email, role, scope: canScope(role) ? u.scope : null } })
      setNotice(`${u.email} is now ${/^[aeiou]/.test(role) ? 'an' : 'a'} ${role}. They were signed out so it applies now.`)
      load()
    } catch (err) {
      handle(err, setError)
    }
  }

  async function remove(email) {
    if (!window.confirm(`Remove ${email} from ${me.workspace}? They are signed out right away.`)) return
    try {
      await api(`/api/users/${encodeURIComponent(email)}`, { method: 'DELETE' })
      setNotice(`${email} was removed.`)
      load()
    } catch (err) {
      handle(err, setError)
    }
  }

  if (!data) return <div className="reports"><p className="rail-empty" role="status">{error || 'Loading members'}</p></div>

  const q = query.trim().toLowerCase()
  const people = data.users.filter((u) => u.email.includes(q))
  const counts = Object.keys(ROLES).map((r) => [r, data.users.filter((u) => u.role === r).length]).filter(([, n]) => n)
  const roles = Object.keys(ROLES).filter((r) => me.role === 'owner' || r !== 'owner')
  const log = data.audit.filter((e) => KINDS[kind].test(e) && (!q || (e.user ?? '').includes(q) || (e.member ?? '').includes(q)))

  return (
    <div className="reports members">
      <header className="members-head">
        <div>
          <h2>Members</h2>
          <p className="lead">Who is in {me.workspace}, what each person may do, and which data the analyst can see for them.</p>
          <p className="role-counts">{counts.map(([r, n]) => <span key={r} className={`role-chip role-${r}`}>{n} {r}{n > 1 ? 's' : ''}</span>)}</p>
        </div>
        <button className="btn btn-blue" onClick={() => setSheet({ kind: 'invite' })}><Icon name="user" size={18} />Invite member</button>
      </header>

      {notice && <p className="members-notice" role="status">{notice} <button className="link" onClick={() => setNotice('')}>Dismiss</button></p>}
      {error && <p className="error" role="alert">{error}</p>}

      <section className="members-table" aria-labelledby="team-h">
        <div className="members-tools">
          <h3 id="team-h" className="rail-h">Team <em>{data.users.length}</em></h3>
          <input type="search" className="members-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by email" aria-label="Search members and activity" />
        </div>
        <div role="table" aria-label="Members">
          <div role="row" className="mt-row mt-head">
            <span role="columnheader">Member</span>
            <span role="columnheader">Role</span>
            <span role="columnheader">Data access</span>
            <span role="columnheader" className="sr-only">Actions</span>
          </div>
          {people.map((u) => {
            const locked = u.email === me.user || (me.role !== 'owner' && u.role === 'owner')
            return (
              <div role="row" key={u.email} className="mt-row">
                <span role="cell" className="mt-member"><Avatar email={u.email} /><span className="mt-email">{u.email}{u.email === me.user && <em>you</em>}</span></span>
                <span role="cell" className="mt-role">
                  {locked ? <span className={`role-chip role-${u.role}`}>{u.role}</span> : (
                    <select className="role-select" value={u.role} onChange={(e) => changeRole(u, e.target.value)} aria-label={`Role of ${u.email}`}>
                      {roles.map((r) => <option key={r} value={r}>{r[0].toUpperCase() + r.slice(1)}</option>)}
                    </select>
                  )}
                </span>
                <span role="cell" className="mt-access"><AccessChips scope={u.scope} /></span>
                <span role="cell" className="mt-actions">
                  {!locked && <>
                    <button className="btn btn-ghost" onClick={() => setSheet({ kind: 'edit', member: u })}>Edit access</button>
                    <button className="btn btn-ghost danger" onClick={() => remove(u.email)} aria-label={`Remove ${u.email}`}>Remove</button>
                  </>}
                </span>
              </div>
            )
          })}
          {!people.length && <p className="rail-empty mt-empty">No member matches “{query}”.</p>}
        </div>
      </section>

      <section className="activity-panel" aria-labelledby="log-h">
        <div className="members-tools">
          <h3 id="log-h" className="rail-h">Activity</h3>
          <div className="filter-pills" role="group" aria-label="Filter activity">
            {Object.entries(KINDS).map(([k, v]) => <button key={k} className={kind === k ? 'on' : ''} aria-pressed={kind === k} onClick={() => setKind(k)}>{v.label}</button>)}
          </div>
        </div>
        {log.length ? (
          <ol className="audit">
            {log.map((e, i) => (
              <li key={i} className={KINDS.denied.test(e) ? 'warn' : ''}>
                <Avatar email={e.user ?? '?'} />
                <span><b>{e.user ?? 'system'}</b> {e.action}{e.member ? ` ${e.member}` : ''}{e.file ? ` ${e.file}` : ''}{e.permission ? ` (${e.permission})` : ''}{e.question ? `: “${e.question}”` : ''}</span>
                <time dateTime={e.at}>{when(e.at)}</time>
              </li>
            ))}
          </ol>
        ) : <p className="rail-empty">Nothing here yet.</p>}
      </section>

      {sheet && (
        <Sheet title={sheet.kind === 'invite' ? 'Invite a member' : `Edit ${sheet.member.email}`} onClose={() => setSheet(null)}>
          <MemberForm member={sheet.member} files={data.files} me={me} onSaved={saved} onError={handle} />
        </Sheet>
      )}
    </div>
  )
}

