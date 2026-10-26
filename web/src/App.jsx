import { useCallback, useEffect, useState } from 'react'
import { api, loadToken, saveToken } from './api.js'
import Landing from './Landing.jsx'
import McpConsent from './McpConsent.jsx'
import { forgetBoards } from './saved.js'
import SignIn from './SignIn.jsx'
import Workspace from './Workspace.jsx'

const CONSENT_KEY = 'mcp-consent'

function pendingConsent() {
  const fromUrl = new URLSearchParams(window.location.search).get('mcp_consent')
  try {
    if (fromUrl) sessionStorage.setItem(CONSENT_KEY, fromUrl)
    return fromUrl || sessionStorage.getItem(CONSENT_KEY)
  } catch {
    return fromUrl
  }
}

export default function App() {
  const [session, setSession] = useState(null)
  const [checking, setChecking] = useState(() => Boolean(loadToken()))
  const [consent, setConsent] = useState(pendingConsent)
  const [view, setView] = useState(() => (consent && !loadToken() ? 'signin' : 'landing'))
  const [notice, setNotice] = useState(() => (consent ? 'Sign in to connect your AI app to Analyst Buddy.' : ''))

  useEffect(() => {
    if (new URLSearchParams(window.location.search).has('mcp_consent')) window.history.replaceState(null, '', window.location.pathname)
  }, [])

  useEffect(() => {
    if (!loadToken()) return
    api('/api/me')
      .then(setSession)
      .catch(() => { saveToken(null); forgetBoards() })
      .finally(() => setChecking(false))
  }, [])

  useEffect(() => { window.scrollTo(0, 0) }, [view, session])

  const finishConsent = useCallback(() => {
    try { sessionStorage.removeItem(CONSENT_KEY) } catch {}
    setConsent(null)
  }, [])

  function signOut(message = '') {
    api('/api/session', { method: 'DELETE' }).catch(() => {})
    saveToken(null)
    forgetBoards()
    setSession(null)
    setNotice(message)
    setView(message ? 'signin' : 'landing')
  }

  if (checking) return <div className="boot" role="status">Opening your board</div>
  if (session && consent) return <McpConsent rid={consent} session={session} setSession={setSession} onFinish={finishConsent} onAuthError={signOut} />
  if (session) return <Workspace key={`${session.tenant}/${session.user}`} session={session} setSession={setSession} signOut={signOut} />
  if (view === 'signin') {
    return <SignIn notice={notice} onBack={() => setView('landing')} onLogin={(s) => { setNotice(''); setSession(s) }} />
  }
  return <Landing onSignIn={() => setView('signin')} onLogin={(s) => { setNotice(''); setSession(s) }} />
}
