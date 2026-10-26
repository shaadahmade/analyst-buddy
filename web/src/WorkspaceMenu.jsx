import { useEffect, useRef, useState } from 'react'
import Icon from './Icon.jsx'

const initial = (name) => name.trim().slice(0, 1).toUpperCase() || '?'

export default function WorkspaceMenu({ session, switching, message, onSwitch, onCreate, signOut }) {
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const box = useRef(null)

  useEffect(() => {
    if (!open) return
    const away = (e) => { if (!box.current?.contains(e.target)) setOpen(false) }
    const esc = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('pointerdown', away)
    window.addEventListener('keydown', esc)
    return () => { window.removeEventListener('pointerdown', away); window.removeEventListener('keydown', esc) }
  }, [open])

  function create(e) {
    e.preventDefault()
    if (!name.trim()) return
    setOpen(false)
    setCreating(false)
    onCreate(name.trim())
    setName('')
  }

  return (
    <div className="ws-menu" ref={box}>
      <button className="ws-current" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)} disabled={switching}>
        <span className="ws-avatar">{initial(session.workspace)}</span>
        <span className="ws-label">
          <b>{switching ? 'Opening workspace' : session.workspace}</b>
          <small>{session.role[0].toUpperCase() + session.role.slice(1)} · {session.workspaces.length} workspace{session.workspaces.length > 1 ? 's' : ''}</small>
        </span>
        {switching ? <span className="mini-spin" aria-hidden="true" /> : <span className="ws-chevron" aria-hidden="true" />}
      </button>
      {message && <p className="error ws-error" role="alert">{message}</p>}
      {open && (
        <div className="ws-pop" role="menu" aria-label="Workspaces">
          <p className="ws-pop-email">{session.user}</p>
          {session.workspaces.map((w) => (
            <button key={w.id} role="menuitemradio" aria-checked={w.id === session.tenant} className="ws-item"
              onClick={() => { setOpen(false); if (w.id !== session.tenant) onSwitch(w.id) }}>
              <span className="ws-avatar sm">{initial(w.name)}</span>
              <span className="ws-item-name">{w.name}</span>
              <span className={`role-chip role-${w.role}`}>{w.role}</span>
              <span className="ws-check" aria-hidden="true">{w.id === session.tenant ? '✓' : ''}</span>
            </button>
          ))}
          <hr />
          {creating ? (
            <form className="ws-new" onSubmit={create}>
              <input aria-label="New workspace name" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder="Workspace name" autoFocus />
              <button className="btn btn-blue" disabled={!name.trim()}>Create</button>
            </form>
          ) : (
            <button role="menuitem" className="ws-item ws-action" onClick={() => setCreating(true)}>
              <span className="ws-plus" aria-hidden="true">+</span>New workspace
            </button>
          )}
          <button role="menuitem" className="ws-item ws-action" onClick={() => signOut()}>
            <Icon name="logout" size={16} />Sign out
          </button>
        </div>
      )}
    </div>
  )
}
