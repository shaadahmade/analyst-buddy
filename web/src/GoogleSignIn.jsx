import { useEffect, useRef, useState } from 'react'
import { api, saveToken } from './api.js'

let configPromise = null
let scriptPromise = null

function googleClientId() {
  configPromise ??= api('/api/config').then((c) => c.google_client_id).catch(() => null)
  return configPromise
}

function loadGoogle() {
  scriptPromise ??= new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://accounts.google.com/gsi/client'
    s.async = true
    s.onload = () => resolve(window.google)
    s.onerror = () => { scriptPromise = null; reject(new Error('Could not load Google sign-in')) }
    document.head.appendChild(s)
  })
  return scriptPromise
}

export default function GoogleSignIn({ workspace = '', onLogin, onBusy }) {
  const slot = useRef(null)
  const latest = useRef({ workspace, finish: null })
  const [shown, setShown] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(null)
  const [name, setName] = useState('')

  async function finish(credential, ws) {
    setBusy(true)
    setError('')
    try {
      const res = await api('/api/auth/google', { method: 'POST', body: { credential, workspace: ws } })
      if (res.needs_workspace) {
        setPending({ credential, email: res.email })
        setBusy(false)
        return
      }
      const { token, ...session } = res
      saveToken(token)
      onLogin(session)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  useEffect(() => { latest.current = { workspace, finish } })
  useEffect(() => { onBusy?.(busy) }, [busy, onBusy])

  useEffect(() => {
    let live = true
    googleClientId().then((id) => id && loadGoogle().then((google) => {
      if (!live || !slot.current) return
      google.accounts.id.initialize({ client_id: id, callback: (r) => latest.current.finish(r.credential, latest.current.workspace.trim()) })
      google.accounts.id.renderButton(slot.current, {
        theme: 'outline', size: 'large', shape: 'pill', text: 'continue_with', width: Math.min(400, slot.current.offsetWidth || 320),
      })
      setShown(true)
    })).catch((err) => live && setError(err.message))
    return () => { live = false }
  }, [])

  return (
    <div className="google-signin">
      {shown && <p className="or-line"><span>or</span></p>}
      <div ref={slot} className="google-slot" />
      {pending && !busy && (
        <form className="google-name" onSubmit={(e) => { e.preventDefault(); if (name.trim()) finish(pending.credential, name.trim()) }}>
          <label className="field">
            <span>Name your workspace <em>({pending.email})</em></span>
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required autoFocus placeholder="Your company or team" />
          </label>
          <button className="btn btn-outline btn-block" disabled={!name.trim()}>Create workspace</button>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  )
}
