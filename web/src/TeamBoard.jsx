import { useEffect, useRef, useState } from 'react'

const PHASES = [
  { key: 'plan', label: 'Plan', agents: ['Supervisor'] },
  { key: 'data', label: 'Data', agents: ['Data Agent'] },
  { key: 'analyse', label: 'Analyse', agents: [] },
  { key: 'check', label: 'Check', agents: ['Verifier'] },
  { key: 'answer', label: 'Answer', agents: ['Writer'] },
]
const ROLES = {
  Supervisor: 'Plans the work and decides when it is done',
  'Data Agent': 'Picks the right tables and columns',
  Analyst: 'Writes and runs Python on one part',
  Verifier: 'Recomputes the key numbers on its own',
  Writer: 'Writes the answer from checked numbers',
}
const LABEL = { waiting: 'waiting', working: 'working', done: 'done', stopped: 'stopped', skipped: 'not needed' }
const phaseOf = (name) => (name.startsWith('Analyst') ? 2 : PHASES.findIndex((p) => p.agents.includes(name)))
const firstLine = (text = '') => (text.split('\n').find((l) => l.trim() && !/^(STDOUT|STDERR|RESULT):$/.test(l.trim())) ?? '').trim()
const kindOf = (name) => name.split(' ')[0].toLowerCase()

function teamState(steps) {
  const plan = steps.find((s) => s.tool === 'stage' && s.agent === 'Supervisor' && s.args.text.startsWith('Splitting the work'))
  const quick = steps.some((s) => s.tool === 'stage' && s.agent === 'Supervisor' && s.args.text.includes('one analyst'))
  if (!plan && !quick) return null
  const parts = plan ? plan.args.text.split(': ').slice(1).join(': ').split(' | ') : []
  const agents = new Map()
  const get = (name) => {
    if (!agents.has(name)) agents.set(name, { name, phase: phaseOf(name), task: '', now: '', runs: 0, checks: [], seen: false })
    return agents.get(name)
  }
  let latest = null
  for (const s of steps) {
    const a = get(s.agent || 'Analyst')
    a.seen = true
    if (s.tool === 'stage') {
      const text = s.args.text
      if (a.phase === 2 && !a.task) a.task = text
      else if (/^[✓✗]/.test(text)) a.checks.push({ ok: text.startsWith('✓'), text: text.slice(1).trim() })
      else a.now = text
    } else if (s.tool === 'run_python') {
      a.runs += 1
      a.now = s.output == null ? `Running: ${firstLine(s.args.code)}` : `Read: ${firstLine(s.output) || '(no output)'}`
    } else {
      a.now = `Using ${s.tool}`
    }
    latest = { agent: a.name, text: a.now || a.task }
  }
  const analysts = plan ? parts.map((_, i) => `Analyst ${i + 1}`) : ['Analyst']
  const names = quick ? ['Supervisor', 'Analyst'] : ['Supervisor', 'Data Agent', ...analysts, 'Verifier', 'Writer']
  for (const name of names) get(name)
  const columns = (quick ? [PHASES[0], PHASES[2]] : PHASES).map((p) => (p.key === 'analyse' ? { ...p, agents: analysts } : p))
  return { quick, parts, agents, columns, latest }
}

function statusOf(agent, reached, live, stopped) {
  if (!agent.seen) return live ? 'waiting' : 'skipped'
  if (!live) return stopped && agent.phase >= reached ? 'stopped' : 'done'
  return agent.phase < reached ? 'done' : 'working'
}

function columnStatus(statuses) {
  for (const s of ['working', 'stopped', 'waiting']) if (statuses.includes(s)) return s
  return statuses.every((s) => s === 'skipped') ? 'skipped' : 'done'
}

export default function TeamBoard({ steps, live, stopped }) {
  const [open, setOpen] = useState(null)
  const rail = useRef(null)
  useEffect(() => {
    if (!open) return
    const away = (e) => { if (!rail.current?.contains(e.target)) setOpen(null) }
    const esc = (e) => { if (e.key === 'Escape') setOpen(null) }
    window.addEventListener('pointerdown', away)
    window.addEventListener('keydown', esc)
    return () => { window.removeEventListener('pointerdown', away); window.removeEventListener('keydown', esc) }
  }, [open])
  const state = teamState(steps)
  if (!state) return null
  const all = [...state.agents.values()]
  const reached = Math.max(...all.filter((a) => a.seen).map((a) => a.phase))
  const status = Object.fromEntries(all.map((a) => [a.name, statusOf(a, reached, live, stopped)]))
  const checks = state.agents.get('Verifier')?.checks ?? []
  const good = checks.filter((c) => c.ok).length
  const runs = all.reduce((n, a) => n + a.runs, 0)
  const working = all.filter((a) => status[a.name] === 'working').map((a) => a.name)
  const summary = live ? (working.length ? `${working.join(', ')} working` : 'Starting')
    : stopped ? 'Stopped' : `${runs} code run${runs === 1 ? '' : 's'}${checks.length ? ` · ${good} of ${checks.length} confirmed` : ''}`

  return (
    <aside ref={rail} className={`team-rail ${live ? 'is-live' : ''}`} aria-label="The agent team working on this question">
      <p className="rail-title"><b>{state.quick ? 'Quick question' : 'Agent team'}</b><span role="status">{summary}</span></p>
      <ol className="vflow">
        {state.columns.map((col) => {
          const s = columnStatus(col.agents.map((n) => status[n]))
          const lead = state.agents.get(col.agents[0])
          const many = col.key === 'analyse' && col.agents.length > 1
          const label = col.key === 'analyse' ? (many ? 'Analysts' : 'Analyst') : col.label
          const count = many ? `${col.agents.filter((n) => status[n] === 'done').length}/${col.agents.length}` : ''
          const now = col.agents.map((n) => state.agents.get(n)).filter((a) => status[a.name] === 'working' && a.now).at(-1)?.now
          const isOpen = open === col.key
          return (
            <li key={col.key} className={`vstep agent-${kindOf(col.agents[0])} is-${s} ${isOpen ? 'is-open' : ''}`}>
              <button type="button" className="capsule" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : col.key)}
                title={`${label}: ${LABEL[s]}`}>
                <span className="cap-label">{label}</span>
                {count && <span className="cap-count">{count}</span>}
                {col.key === 'check' && checks.length > 0 && (
                  <span className="cap-count"><span className="cap-ok">{good}✓</span>{checks.length > good && <span className="cap-bad"> {checks.length - good}✗</span>}</span>
                )}
                {!(col.key === 'check' && checks.length) && <span className="cap-state">{s === 'done' ? '✓' : s === 'stopped' ? '■' : ''}</span>}
                <i className="cap-chev" aria-hidden="true" />
              </button>
              {many && (
                <span className="subcaps">
                  {col.agents.map((n, i) => <span key={n} className={`subcap is-${status[n]}`} title={`${n}: ${state.agents.get(n).task}`}>{i + 1}{status[n] === 'done' ? '✓' : ''}</span>)}
                </span>
              )}
              {now && !isOpen && <span className="cap-now" title={now}>{now}</span>}
              {isOpen && (
                <div className="cap-pop" role="dialog" aria-label={`${label} details`}>
                  <p className="cap-role">{many ? 'Each analyst works on one part in parallel:' : lead.task || ROLES[kindOf(lead.name) === 'analyst' ? 'Analyst' : lead.name]}</p>
                  {col.key === 'plan' && state.parts.length > 0 && <ol>{state.parts.map((part) => <li key={part}>{part}</li>)}</ol>}
                  {many && <ol>{col.agents.map((n) => <li key={n}><b>{n}</b> {state.agents.get(n).task} <em>{LABEL[status[n]]}</em></li>)}</ol>}
                  {col.key === 'check' && checks.length > 0 && (
                    <ul className="cap-checks">{checks.map((c, i) => <li key={i} className={c.ok ? 'ok' : 'bad'}><b>{c.ok ? '✓' : '✗'}</b>{c.text}</li>)}</ul>
                  )}
                  {now && <p className="cap-live">{now}</p>}
                  {col.agents.some((n) => state.agents.get(n).runs) && (
                    <p className="cap-runs">{((n) => `${n} code run${n === 1 ? '' : 's'}`)(col.agents.reduce((n, a) => n + state.agents.get(a).runs, 0))}</p>
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </aside>
  )
}
