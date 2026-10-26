import { useCallback, useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, apiStream, saveToken } from './api.js'
import InkLayer from './InkLayer.jsx'
import { captureArea } from './capture.js'
import { MAX_CONTEXT, markedText } from './marker.js'
import { loadBoard, saveBoard } from './saved.js'
import { canLend, canLendEraser, lendEraser, lendMarker } from './markers.js'
import Icon from './Icon.jsx'
import AddData from './AddData.jsx'
import McpAccess from './McpAccess.jsx'
import { GoalSuggestions, GoalsNote } from './Goals.jsx'
import Members from './Members.jsx'
import Sheet from './Sheet.jsx'
import TeamBoard from './TeamBoard.jsx'
import WorkspaceMenu from './WorkspaceMenu.jsx'
import Reports from './Reports.jsx'
import ThemeToggle from './ThemeToggle.jsx'

const MAX_CIRCLES = 5

const STARTERS = [
  { icon: 'file', title: 'Profile my data', q: 'Profile my data: what is in it and how clean is it?' },
  { icon: 'goal', title: 'Check my goals', q: 'How are we tracking against our goals?' },
  { icon: 'logo', title: 'Find what changed', q: 'What changed in the last 4 weeks, and why?' },
]

function restoreTurns(saved) {
  return (saved?.turns ?? []).map((t) => ({
    ...t,
    played: true,
    streamed: true,
    ...(t.live && { live: false, error: t.error ?? 'Interrupted by a page reload. Ask again to run it.', retry: true }),
  }))
}

export default function Workspace({ session, setSession, signOut }) {
  const [restored] = useState(() => loadBoard(`${session.tenant}/${session.user}`))
  const [turns, setTurns] = useState(() => restoreTurns(restored))
  const [stopping, setStopping] = useState(false)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState('chat')
  const [uploadMsg, setUploadMsg] = useState('')
  const [switching, setSwitching] = useState(false)
  const [switchMsg, setSwitchMsg] = useState('')
  const [googleResult] = useState(() => new URLSearchParams(window.location.search).get('google'))
  const [adding, setAdding] = useState(Boolean(googleResult))
  const [teamMode, setTeamMode] = useState(true)
  const [railOpen, setRailOpen] = useState(() => !window.matchMedia('(max-width: 640px)').matches)
  const endRef = useRef(null)
  const fileRef = useRef(null)
  const inputRef = useRef(null)
  const nextId = useRef(Math.max(0, ...turns.map((t) => t.id)) + 1)
  const { knowledge } = session
  const can = (p) => session.permissions.includes(p)
  const feedRef = useRef(null)
  const boardRef = useRef(null)
  const hand = useRef(null)
  const pointer = useRef(null)
  const [marking, setMarking] = useState(null)
  const strokes = useRef(restored?.strokes ?? [])
  const inkRef = useRef(null)
  const [ink, setInk] = useState({ hasInk: false, canUndo: false, canRedo: false })
  const turnsNow = useRef(turns)
  const saveTimer = useRef(null)
  const saveSoon = useCallback(() => {
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => saveBoard(`${session.tenant}/${session.user}`, { turns: turnsNow.current, strokes: strokes.current }), 400)
  }, [session.tenant, session.user])
  const keepStrokes = useCallback((all) => {
    strokes.current = all
    saveSoon()
  }, [saveSoon])
  useEffect(() => {
    turnsNow.current = turns
    saveSoon()
  }, [turns, saveSoon])
  const [layerHeight, setLayerHeight] = useState(0)
  const [marks, setMarks] = useState([])
  const markId = useRef(0)
  const capturing = marks.some((m) => m.capturing)
  const full = marks.length >= MAX_CIRCLES

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [turns, busy, tab])

  useEffect(() => {
    if (!marking) return
    const onKey = (e) => { if (e.key === 'Escape') putMarkerDown() }
    const onDown = (e) => { if (!boardRef.current?.contains(e.target) && !e.target.closest?.('.mark-chip')) putMarkerDown() }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onDown)
    }
  }, [marking])

  useEffect(() => () => hand.current?.pen.cancel(), [])

  useEffect(() => {
    if (tab !== 'chat') return
    const onKey = (e) => {
      if (!(e.ctrlKey || e.metaKey) || e.target.closest?.('input, textarea, [contenteditable]')) return
      const key = e.key.toLowerCase()
      if (key === 'z' && !e.shiftKey) inkRef.current?.undo()
      else if ((key === 'z' && e.shiftKey) || key === 'y') inkRef.current?.redo()
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tab])

  function pickMarker(tone) {
    const wasHolding = marking
    putMarkerDown()
    if (wasHolding === tone) return
    if (tone === 'magic' && full) return
    setLayerHeight(feedRef.current.scrollHeight)
    setMarking(tone)
    const eraser = tone === 'eraser'
    if (!(eraser ? canLendEraser(boardRef.current) : canLend(boardRef.current, tone))) return
    const pen = eraser ? lendEraser(boardRef.current) : lendMarker(boardRef.current, tone)
    const held = { pen, ready: false }
    hand.current = held
    const f = feedRef.current.getBoundingClientRect()
    pen.takeOut(() => pointer.current ?? { x: f.left + f.width / 2, y: f.top + f.height * 0.6 })
      .then(() => {
        held.ready = true
        if (pointer.current) pen.hold(pointer.current)
      })
      .catch(() => {})
  }

  function putMarkerDown() {
    const held = hand.current
    hand.current = null
    setMarking(null)
    if (!held) return
    if (held.ready) held.pen.putBack().catch(() => {})
    else held.pen.cancel()
  }

  function trackPointer(e) {
    pointer.current = { x: e.clientX, y: e.clientY }
    if (hand.current?.ready) hand.current.pen.hold(pointer.current)
  }

  function clearMarks() {
    setMarks([])
  }

  function removeMark(id) {
    setMarks((all) => all.filter((m) => m.id !== id))
  }

  function letGo(tone, box) {
    putMarkerDown()
    if (tone !== 'magic' || !box) return
    if (full) return
    const id = ++markId.current
    const picked = markedText(feedRef.current, box)
    setMarks((all) => (all.length >= MAX_CIRCLES ? all : [...all, { id, ...picked, image: null, capturing: true }]))
    inputRef.current?.focus()
    const settle = (patch) => setMarks((all) => all.map((m) => (m.id === id ? { ...m, ...patch } : m))
      .filter((m) => m.capturing || m.image || m.count))
    return captureArea(feedRef.current, box).then((image) => settle({ image, capturing: false }), () => settle({ capturing: false }))
  }

  useEffect(() => {
    if (googleResult) window.history.replaceState(null, '', window.location.pathname)
  }, [googleResult])

  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [draft])

  function update(id, patch) {
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch } : t)))
  }

  async function send(text, reuseId = null) {
    const question = text.trim()
    if (!question || busy || (!reuseId && capturing)) return
    const id = reuseId ?? nextId.current++
    const before = reuseId && turns.find((t) => t.id === reuseId)
    const context = before ? (before.context ?? '') : marks.filter((m) => m.count)
      .map((m) => (marks.length > 1 ? `Circle ${marks.indexOf(m) + 1}:\n${m.text}` : m.text)).join('\n\n').slice(0, MAX_CONTEXT)
    const images = before ? (before.images ?? []) : marks.map((m) => m.image).filter(Boolean)
    const edit = (fn) => setTurns((all) => all.map((t) => (t.id === id ? fn(t) : t)))
    const fresh = { steps: [], live: true, played: false, error: null, retry: false, stopped: false }
    if (reuseId) edit((t) => ({ ...t, ...fresh, attempt: (t.attempt ?? 0) + 1 }))
    else setTurns((all) => [...all, { id, question, context, images, ...fresh }])
    setDraft('')
    if (!reuseId) clearMarks()
    setBusy(true)
    let ended = false
    try {
      await apiStream('/api/ask', { question, context, images, mode: teamMode ? 'auto' : 'single' }, (e) => {
        if (e.type === 'stage') {
          edit((t) => ({ ...t, steps: [...t.steps, { id: e.id, tool: 'stage', agent: e.agent, args: { text: e.text }, output: '' }] }))
        } else if (e.type === 'call') {
          edit((t) => ({ ...t, steps: [...t.steps, { id: e.id, tool: e.tool, agent: e.agent, args: e.args, output: null }] }))
        } else if (e.type === 'output') {
          edit((t) => ({ ...t, steps: t.steps.map((st) => (st.id === e.id ? { ...st, output: e.output } : st)) }))
        } else if (e.type === 'done') {
          ended = true
          update(id, { answer: e.answer, charts: e.charts, calls: e.calls, trace: e.trace })
        } else if (e.type === 'error') {
          ended = true
          update(id, { error: e.message, retry: e.retry })
        } else if (e.type === 'stopped') {
          ended = true
          update(id, { error: 'Stopped. Nothing from this question was kept, so the analyst can pick up from before it.', retry: true, stopped: true })
        }
      })
      if (!ended) update(id, { error: 'The answer stopped before it finished.', retry: true })
    } catch (err) {
      if (err.status === 401) return signOut(err.message)
      update(id, { error: err.message, retry: err.status === 0 })
    } finally {
      update(id, { live: false })
      setBusy(false)
      setStopping(false)
      inputRef.current?.focus()
    }
  }

  async function stop() {
    setStopping(true)
    try {
      await api('/api/ask/stop', { method: 'POST' })
    } catch (err) {
      if (err.status === 401) return signOut(err.message)
      setStopping(false)
    }
  }

  async function upload(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploadMsg(`Uploading ${file.name}`)
    const form = new FormData()
    form.append('file', file)
    try {
      setSession(await api('/api/upload', { method: 'POST', form }))
      setUploadMsg(`${file.name} added`)
    } catch (err) {
      if (err.status === 401) return signOut(err.message)
      setUploadMsg(err.message)
    }
  }

  async function saveGoals(goals) {
    try {
      setSession(await api('/api/goals', { method: 'PUT', body: { goals } }))
    } catch (err) {
      if (err.status === 401) return signOut(err.message)
      throw err
    }
  }

  async function deleteFile(name) {
    if (!window.confirm(`Delete ${name}? The analyst stops using it right away. A saved connection that made it can bring it back on its next sync.`)) return
    try {
      setSession(await api(`/api/data/${encodeURIComponent(name)}`, { method: 'DELETE' }))
      setUploadMsg(`${name} deleted`)
    } catch (err) {
      if (err.status === 401) return signOut(err.message)
      setUploadMsg(err.message)
    }
  }

  async function openWorkspace(path, body) {
    setSwitching(true)
    setSwitchMsg('')
    try {
      const { token, ...next } = await api(path, { method: 'POST', body })
      saveToken(token)
      setSession(next)
    } catch (err) {
      if (err.status === 401) return signOut(err.message)
      setSwitchMsg(err.message)
      setSwitching(false)
    }
  }

  return (
    <div className="ws">
      <aside className="rail">
        <div className="rail-top">
          <div className="wordmark"><Icon name="logo" size={22} />Analyst Buddy</div>
          <ThemeToggle />
        </div>

        <WorkspaceMenu session={session} switching={switching} message={switchMsg} signOut={signOut}
          onSwitch={(id) => openWorkspace(`/api/workspaces/${id}/open`)}
          onCreate={(name) => openWorkspace('/api/workspaces', { name })} />

        <details className="rail-details" open={railOpen} onToggle={(e) => setRailOpen(e.currentTarget.open)}>
          <summary>
            <span className="rail-icon"><Icon name="company" size={18} /></span>
            <span className="rail-company-name">Goals and data</span>
          </summary>
          {knowledge.company && <p className="rail-company-desc">{knowledge.company}</p>}

          <section aria-labelledby="goals-h" className="rail-note">
            <span className="magnet sm" aria-hidden="true" />
            <h2 id="goals-h" className="rail-h">Goals</h2>
            <GoalsNote goals={knowledge.goals ?? []} canEdit={can('teach')} onSave={saveGoals} />
          </section>

          <section aria-labelledby="data-h" className="rail-note data">
            <span className="magnet sm" aria-hidden="true" />
            <h2 id="data-h" className="rail-h">Data</h2>
            {session.files.length ? (
              <ul className="rail-files">
                {session.files.map((f) => (
                  <li key={f} className="file-row">
                    <Icon name="file" size={16} /><span className="file-name">{f}</span>
                    {can('upload') && (
                      <button type="button" className="row-btn danger" aria-label={`Delete ${f}`} title="Delete this data" onClick={() => deleteFile(f)}>✕</button>
                    )}
                  </li>
                ))}
              </ul>
            ) : <p className="rail-empty">{can('upload') ? 'No data yet. Add a file, a sheet, a database or an app to start.' : `No data yet. As ${session.role === 'viewer' ? 'a viewer' : 'a limited member'} you can't upload; ask an owner, admin or analyst of this workspace to add files.`}</p>}
            {can('upload') && <>
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.json,.parquet" onChange={upload} hidden />
              <button className="btn btn-outline btn-block" onClick={() => setAdding(true)}>
                <Icon name="upload" size={18} />Add data
              </button>
            </>}
            {adding && (
              <Sheet title="Add data" onClose={() => setAdding(false)}>
                <AddData onPickFile={() => { setAdding(false); fileRef.current.click() }} onSession={setSession} onAuthError={signOut} googleResult={googleResult} />
              </Sheet>
            )}
            {session.scoped && <p className="rail-empty">You see the part of the company data your admin shared with you.</p>}
            {uploadMsg && <p className="rail-empty" role="status">{uploadMsg}</p>}
          </section>
        </details>

        <p className="rail-user"><Icon name="user" size={16} /><span>{session.user}</span><span className={`role-chip role-${session.role}`}>{session.role}</span></p>
        <button className="btn btn-ghost signout" onClick={() => signOut()}><Icon name="logout" size={18} />Sign out</button>
      </aside>

      <main className="desk">
        <header className="desk-top">
          <div className="tabs" role="tablist" aria-label="Workspace">
            <button role="tab" aria-selected={tab === 'chat'} className={tab === 'chat' ? 'on' : ''} onClick={() => setTab('chat')}>Ask your analyst</button>
            {can('reports') && <button role="tab" aria-selected={tab === 'reports'} className={tab === 'reports' ? 'on' : ''} onClick={() => setTab('reports')}>Weekly reports</button>}
            {can('users') && <button role="tab" aria-selected={tab === 'members'} className={tab === 'members' ? 'on' : ''} onClick={() => setTab('members')}>Members</button>}
            <button role="tab" aria-selected={tab === 'mcp'} className={tab === 'mcp' ? 'on' : ''} onClick={() => setTab('mcp')}>Connect AI</button>
          </div>
          <span className="status"><i />Sandbox ready</span>
        </header>

        {tab === 'mcp' ? <McpAccess session={session} onAuthError={signOut} /> : tab === 'members' ? <Members me={session} onAuthError={signOut} /> : tab === 'reports' ? <Reports canManage={can('reports.manage')} onAuthError={signOut} /> : <>
        <div className="ws-board" ref={boardRef} onPointerMove={trackPointer}>
        <div className={`feed ${marking ? 'is-marking' : ''} ${hand.current ? 'pen-in-hand' : ''}`} ref={feedRef} aria-live="polite">
          <InkLayer ref={inkRef} feedRef={feedRef} saved={strokes.current} keep={keepStrokes} tool={marking} height={layerHeight}
            onLetGo={letGo} onInkChange={setInk} />
          {turns.length === 0 && (
            <div className="feed-empty">
              <p className="marker-note big">What do you want to know?</p>
              <p className="lead">Ask about your data in plain words. Every answer is computed from your files, and I remember what you teach me.</p>
              <div className="starters">
                {STARTERS.map((s) => (
                  <button key={s.title} className="starter" onClick={() => send(s.q)} disabled={busy}>
                    <span className="magnet sm" aria-hidden="true" />
                    <span className="starter-h"><Icon name={s.icon} size={18} />{s.title}</span>
                    <span className="starter-q">{s.q}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((t) => (
            <section key={t.id} className="turn" aria-label={`Question: ${t.question}`}>
              <div className="q">
                <span className="magnet sm" aria-hidden="true" /><p>{t.question}</p>
                {t.images?.length > 0 && (
                  <div className="q-shots">
                    {t.images.map((src, i) => <img key={i} className="q-shot" src={src} alt={`Circled area ${i + 1} sent with this question`} />)}
                  </div>
                )}
                {t.context && <details className="marked-tag"><summary>About the circled area</summary><pre>{t.context}</pre></details>}
              </div>
              <div className="turn-work">
                <Monitor key={t.attempt ?? 0} question={t.question} steps={t.steps} live={t.live} done={t.played}
                  onDone={() => update(t.id, { played: true })} />
                <TeamBoard steps={t.steps} live={t.live} stopped={t.stopped} />
              </div>
              {t.answer != null && t.played && <Answer turn={t} onUpdate={(patch) => update(t.id, patch)} signOut={signOut} />}
              {t.answer != null && t.played && t.streamed && <GoalSuggestions steps={t.steps} goals={knowledge.goals ?? []} canEdit={can('teach')} onSave={saveGoals} />}
              {t.error && (
                <div className={`answer is-error ${t.stopped ? 'is-stopped' : ''}`} role={t.stopped ? 'status' : 'alert'}>
                  <p>{t.error}</p>
                  {t.retry && (
                    <button className="btn btn-outline retry" onClick={() => send(t.question, t.id)} disabled={busy}>
                      {t.stopped ? 'Ask again' : 'Try again'}
                    </button>
                  )}
                </div>
              )}
            </section>
          ))}

          <div ref={endRef} />
        </div>
        {(ink.hasInk || ink.canUndo || ink.canRedo) && (
          <div className="board-tools" role="toolbar" aria-label="Drawing">
            <button type="button" onClick={() => inkRef.current.undo()} disabled={!ink.canUndo} title="Undo (Ctrl+Z)">
              <span aria-hidden="true">↶</span>Undo
            </button>
            <button type="button" onClick={() => inkRef.current.redo()} disabled={!ink.canRedo} title="Redo (Ctrl+Shift+Z)">
              <span aria-hidden="true">↷</span>Redo
            </button>
            <button type="button" onClick={() => inkRef.current.clear()} disabled={!ink.hasInk} title="Clear every drawing (undo brings it back)">
              Clear
            </button>
          </div>
        )}
        <div className="tray" role="group" aria-label="Markers: draw on the board, or circle with the AI marker to ask the AI about it">
          {['blue', 'red', 'green', 'magic'].map((tone) => (
            <button key={tone} type="button" className={`cap ${tone}`} aria-pressed={marking === tone}
              aria-label={`${marking === tone ? 'Put back' : 'Pick up'} the ${tone === 'magic' ? 'AI' : tone} marker${tone === 'magic' ? (full ? `, ${MAX_CIRCLES} areas circled already, remove one first` : ', circle anything to ask the AI') : ''}`}
              title={tone === 'magic' ? (full ? `You have ${MAX_CIRCLES} circled areas, the most. Remove one to circle another.` : 'AI marker: circle anything on the board to ask the AI analyst about it') : `Draw on the board in ${tone}`}
              data-full={tone === 'magic' && full ? '' : undefined}
              onClick={() => pickMarker(tone)}>{tone === 'magic' && <b className="ai-tag" aria-hidden="true">AI</b>}</button>
          ))}
          <button type="button" className="eraser" aria-pressed={marking === 'eraser'}
            aria-label={`${marking === 'eraser' ? 'Put back' : 'Pick up'} the eraser`} title="Eraser: rub drawings off the board"
            onClick={() => pickMarker('eraser')} />
        </div>
        </div>

        <form className="composer" onSubmit={(e) => { e.preventDefault(); send(draft) }}>
          {(marking || marks.length > 0) && (
            <div className="mark-chip" role="status">
              {!marking && marks.length > 0 && (
                <ul className="mark-shots" aria-label="Circled areas">
                  {marks.map((m, i) => (
                    <li key={m.id}>
                      {m.capturing ? <span className="mark-shot mark-wait"><span className="mini-spin" aria-hidden="true" /></span>
                        : m.image ? <img className="mark-shot" src={m.image} alt={`Circled area ${i + 1}`} />
                        : <span className="mark-shot mark-wait">Text</span>}
                      <button type="button" className="mark-x" onClick={() => removeMark(m.id)} aria-label={`Remove circled area ${i + 1}`}>×</button>
                    </li>
                  ))}
                </ul>
              )}
              <span className="mark-text">
                {marking === 'eraser' ? 'Rub over drawings to erase them. Let go and the eraser goes back.'
                  : marking === 'magic' ? `AI marker: circle what you want the AI to look at (${marks.length} of ${MAX_CIRCLES}). Let go and it goes back.`
                  : marking ? `Draw with the ${marking} marker. Let go and it goes back.`
                  : capturing ? 'Capturing the circled area'
                  : `${marks.length} circled area${marks.length === 1 ? '' : 's'} go to the AI with your next question. ${full ? `That is the most, ${MAX_CIRCLES}.` : `You can circle up to ${MAX_CIRCLES}.`}`}
              </span>
              {marks.length > 0 && !marking && <button type="button" className="mark-clear" onClick={clearMarks}>Clear all</button>}
              {marking === 'eraser' && ink.hasInk && (
                <button type="button" className="mark-clear" onClick={() => { inkRef.current.clear(); putMarkerDown() }}>Erase everything</button>
              )}
            </div>
          )}
          <div className="composer-box">
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(draft) } }}
              placeholder="Ask a question, or teach me about your business"
              aria-label="Your question"
              aria-describedby="composer-hint"
              rows={1}
              maxLength={4000}
            />
            {busy ? (
              <button type="button" className="btn btn-outline stop-btn" onClick={stop} disabled={stopping}
                title="Stop the analyst after the step it is on">
                <span className="stop-square" aria-hidden="true" />{stopping ? 'Stopping' : 'Stop'}
              </button>
            ) : (
              <button className="btn btn-blue" disabled={!draft.trim() || capturing}>
                <Icon name="send" size={18} />Ask
              </button>
            )}
          </div>
          <div className="composer-foot">
            <p id="composer-hint" className="composer-hint">Enter to send. Shift and Enter for a new line.</p>
            <label className="team-switch" title="On: a supervisor splits hard questions across parallel analysts, a verifier re-checks the numbers and a writer answers. Off: one analyst, faster.">
              <input type="checkbox" checked={teamMode} onChange={(e) => setTeamMode(e.target.checked)} />
              <span className="team-knob" aria-hidden="true" />Agent team
            </label>
          </div>
        </form>
        </>}
      </main>
    </div>
  )
}

const RUN_PAUSE = 40

function AgentTag({ name }) {
  const kind = name.split(' ')[0].toLowerCase()
  return <b className={`agent-tag agent-${kind}`}>{name}</b>
}

function source(step) {
  if (step.tool === 'stage') return step.args.text
  if (step.tool === 'run_python') return step.args.code
  if (step.tool === 'remember') return `remember(${JSON.stringify(step.args.note)})`
  return `${step.tool}(${JSON.stringify(step.args)})`
}

function Monitor({ question, steps, live, done, onDone }) {
  const still = done || window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const sizes = steps.map((s) => source(s).length + RUN_PAUSE)
  const starts = []
  for (let i = 0, at = 0; i < sizes.length; at += sizes[i++]) starts.push(at)
  let reach = 0
  for (const [i, s] of steps.entries()) {
    if (s.output == null) { reach += source(s).length; break }
    reach += sizes[i]
  }
  const [n, setN] = useState(still ? Infinity : 0)
  const termRef = useRef(null)
  const caughtUp = n >= reach
  const finished = !live && caughtUp

  useEffect(() => {
    if (finished) { if (!done) onDone(); return }
    if (caughtUp) return
    const speed = Math.max(3, Math.ceil((reach - n) / 300))
    const t = setTimeout(() => setN((v) => v + speed), 16)
    return () => clearTimeout(t)
  }, [n, reach, finished]) // eslint-disable-line react-hooks/exhaustive-deps -- done and onDone only matter once finished

  useEffect(() => { if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight }, [n, steps])

  const thinking = live && caughtUp && (steps.length === 0 || steps.at(-1).output != null)
  const team = steps.some((s) => s.tool === 'stage')
  const codeNo = []
  for (let i = 0, k = 0; i < steps.length; i++) codeNo.push(steps[i].tool === 'stage' ? 0 : ++k)
  const codeSteps = codeNo.filter(Boolean).length
  return (
    <figure className="monitor" aria-label="How the analyst worked this out">
      <div className="mon-bezel">
        <div className="mon-screen">
          <div className="mon-bar" aria-hidden="true"><i /><i /><i /><span>{team ? 'analyst team — supervisor, data agent, analysts, verifier, writer' : 'analyst-sandbox — python 3'}</span></div>
          <div className="mon-term" ref={termRef} aria-busy={!finished}>
            <p className="mon-line"><b>$</b> analyst ask {JSON.stringify(question)}</p>
            {steps.map((s, i) => {
              const code = source(s)
              const avail = n - starts[i]
              if (avail <= 0) return null
              const shown = Math.min(code.length, avail)
              const typing = shown < code.length
              const ran = s.output != null && avail >= sizes[i]
              if (s.tool === 'stage') {
                return (
                  <p key={s.id} className="mon-stage">
                    <AgentTag name={s.agent} />{code.slice(0, shown)}{typing && <span className="mon-cursor" />}
                  </p>
                )
              }
              return (
                <div key={s.id} className="mon-step">
                  <p className="mon-in">{s.agent && <AgentTag name={s.agent} />}In [{codeNo[i]}]: <span>{s.tool}</span></p>
                  <pre className="mon-code">{code.slice(0, shown)}{typing && <span className="mon-cursor" />}</pre>
                  {!typing && !ran && <p className="mon-line mon-dim">running in the sandbox<span className="mon-cursor" /></p>}
                  {ran && <pre className="mon-out">{s.output || '(no output)'}</pre>}
                </div>
              )
            })}
            {thinking && (
              <p className="mon-line mon-dim">
                {steps.length ? 'reading the result, planning the next step' : 'reading your question and your data'}<span className="mon-cursor" />
              </p>
            )}
            {finished && (
              <p className="mon-line mon-ok">
                {codeSteps ? `✓ done in ${codeSteps} step${codeSteps === 1 ? '' : 's'}${team ? ' by the team' : ''}` : '✓ answered without running code'}
              </p>
            )}
          </div>
        </div>
        <div className="mon-chin">
          <span className="mon-brand" aria-hidden="true">ANALYST</span>
          {!caughtUp && <button className="mon-skip" onClick={() => setN(Infinity)}>Skip typing</button>}
          <span className={`mon-led ${finished ? '' : 'on'}`} aria-hidden="true" />
        </div>
      </div>
    </figure>
  )
}

function useStream(text, done, onDone) {
  const [n, setN] = useState(() => (done || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? Infinity : 0))
  const finished = n >= text.length
  useEffect(() => {
    if (finished) { if (!done) onDone(); return }
    const step = Math.max(4, Math.ceil(text.length / 120))
    const t = setTimeout(() => setN((v) => {
      const next = text.indexOf(' ', v + step)
      return next === -1 ? Infinity : next
    }), 16)
    return () => clearTimeout(t)
  }, [n, finished]) // eslint-disable-line react-hooks/exhaustive-deps -- text is fixed once the answer arrives
  return [finished ? text : text.slice(0, n), finished, () => setN(Infinity)]
}

function Answer({ turn, onUpdate, signOut }) {
  const [shownText, streamDone, finishStream] = useStream(turn.answer, turn.streamed, () => onUpdate({ streamed: true }))
  const [copied, setCopied] = useState(false)
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)
  const rating = turn.rating
  const asking = turn.feedbackStep === 'reason'
  const [chartsOpen, setChartsOpen] = useState(false)
  const folderRef = useRef(null)
  const charts = turn.charts ?? []

  function closeCharts() {
    setChartsOpen(false)
    folderRef.current?.focus()
  }

  async function sendFeedback(value, reason = '') {
    setSending(true)
    try {
      const res = await api('/api/feedback', {
        method: 'POST', body: { question: turn.question, answer: turn.answer, rating: value, note: reason, trace: turn.trace || '' },
      })
      onUpdate({
        rating: value, feedbackStep: 'done',
        feedbackMsg: res.remembered ? 'Thanks. I will remember that.' : 'Thanks. Saved, and I will learn from it once memory is back.',
      })
    } catch (err) {
      if (err.status === 401) return signOut(err.message)
      onUpdate({ feedbackMsg: err.message })
    } finally {
      setSending(false)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(turn.answer)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {}
  }

  return (
    <article className="answer">
      <span className="magnet sm" aria-hidden="true" />
      {charts.length > 0 && (
        <button ref={folderRef} className="folder-btn" aria-expanded={chartsOpen} aria-label={`Open ${charts.length} chart${charts.length === 1 ? '' : 's'}`} onClick={() => setChartsOpen(true)}>
          Charts · {charts.length}
        </button>
      )}
      {chartsOpen && (
        <div className="folder-sheet" role="region" aria-label="Charts" onKeyDown={(e) => e.key === 'Escape' && closeCharts()}>
          <div className="folder-sheet-head">
            <span className="folder-tab">Charts</span>
            <button className="btn btn-ghost folder-close" onClick={closeCharts} autoFocus>Close folder</button>
          </div>
          {charts.map((src, j) => (
            <img key={j} className="answer-chart" src={src} alt={`Chart ${j + 1} for: ${turn.question}`} />
          ))}
        </div>
      )}
      <div className={`answer-body${streamDone ? '' : ' is-streaming'}`} aria-busy={!streamDone} onClick={streamDone ? undefined : finishStream}
        title={streamDone ? undefined : 'Click to show the whole answer'}><Markdown remarkPlugins={[remarkGfm]}>{shownText}</Markdown></div>
      {turn.chartsDropped && <p className="feedback-msg">This answer's charts were too big to keep through the page reload. Ask again to redraw them.</p>}

      <footer className="answer-foot">
        {turn.calls != null && <span className="source-tag">Computed with {turn.calls} analyst step{turn.calls === 1 ? '' : 's'}</span>}
        <div className="answer-actions" role="group" aria-label="Answer actions">
          <button className="icon-btn" onClick={copy} aria-label="Copy answer" title="Copy answer">
            <Icon name="copy" size={17} />{copied && <span className="icon-btn-label">Copied</span>}
          </button>
          <button className={`icon-btn ${rating === 'up' ? 'on-up' : ''}`} aria-pressed={rating === 'up'} aria-label="Helpful"
            title="Helpful" disabled={sending || !!rating} onClick={() => sendFeedback('up')}>
            <Icon name="thumb-up" size={17} />
          </button>
          <button className={`icon-btn ${rating === 'down' || asking ? 'on-down' : ''}`} aria-pressed={rating === 'down'} aria-label="Not helpful"
            title="Not helpful" disabled={sending || !!rating} onClick={() => onUpdate({ feedbackStep: 'reason', feedbackMsg: null })}>
            <Icon name="thumb-down" size={17} />
          </button>
        </div>
      </footer>

      {asking && !rating && (
        <form className="feedback-form" onSubmit={(e) => { e.preventDefault(); sendFeedback('down', note) }}>
          <label htmlFor={`fb-${turn.id}`}>What was wrong? I will remember the correction.</label>
          <textarea id={`fb-${turn.id}`} value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={1000}
            placeholder="For example: revenue should exclude refunds" autoFocus />
          <div className="feedback-row">
            <button className="btn btn-blue" disabled={sending}>{sending ? 'Saving' : 'Save feedback'}</button>
            <button type="button" className="btn btn-ghost" onClick={() => onUpdate({ feedbackStep: null })} disabled={sending}>Cancel</button>
          </div>
        </form>
      )}
      {turn.feedbackMsg && <p className="feedback-msg" role="status">{turn.feedbackMsg}</p>}
    </article>
  )
}
