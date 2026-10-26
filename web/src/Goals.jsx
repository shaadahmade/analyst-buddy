import { useState } from 'react'
import Icon from './Icon.jsx'

const same = (a, b) => a.trim().toLowerCase() === b.trim().toLowerCase()

export function GoalsNote({ goals, canEdit, onSave }) {
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function commit(next) {
    setBusy(true)
    setError('')
    try {
      await onSave(next)
      setEditing(null)
      setDraft('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function submit(e) {
    e.preventDefault()
    const text = draft.trim()
    if (!text) return setEditing(null)
    commit(editing === 'new' ? [...goals, text] : goals.map((g, i) => (i === editing ? text : g)))
  }

  const editor = (
    <form className="goal-edit" onSubmit={submit}>
      <input value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={200} autoFocus disabled={busy}
        placeholder="e.g. Grow repeat orders 10% by March" aria-label={editing === 'new' ? 'New goal' : 'Edit goal'}
        onKeyDown={(e) => { if (e.key === 'Escape') { setEditing(null); setDraft('') } }} />
      <button className="btn btn-blue" disabled={busy || !draft.trim()}>Save</button>
    </form>
  )

  return (
    <>
      {goals.length ? (
        <ul className="rail-goals">
          {goals.map((g, i) => (editing === i ? <li key={g}>{editor}</li> : (
            <li key={g} className="goal-row">
              <Icon name="goal" size={16} /><span>{g}</span>
              {canEdit && (
                <span className="row-actions">
                  <button type="button" className="row-btn" aria-label={`Edit goal: ${g}`} title="Edit" onClick={() => { setEditing(i); setDraft(g) }}>✎</button>
                  <button type="button" className="row-btn danger" aria-label={`Delete goal: ${g}`} title="Delete" disabled={busy}
                    onClick={() => window.confirm(`Delete the goal "${g}"?`) && commit(goals.filter((_, j) => j !== i))}>✕</button>
                </span>
              )}
            </li>
          )))}
        </ul>
      ) : <p className="rail-empty">No goals yet. {canEdit ? 'Add one below, or tell the analyst your targets in the chat.' : 'An owner, admin or analyst can add them.'}</p>}
      {canEdit && (editing === 'new' ? editor : (
        <button type="button" className="link add-goal" onClick={() => { setEditing('new'); setDraft('') }} disabled={goals.length >= 20}>+ Add goal</button>
      ))}
      {error && <p className="error" role="alert">{error}</p>}
    </>
  )
}

export function GoalSuggestions({ steps, goals, canEdit, onSave }) {
  const [dismissed, setDismissed] = useState([])
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const seen = new Set()
  const suggestions = steps
    .filter((s) => s.tool === 'suggest_goal' && s.args && !(s.output ?? '').startsWith('not suggested'))
    .map((s) => ({ action: s.args.action, goal: s.args.goal ?? '', newGoal: s.args.new_goal ?? '' }))
    .filter((s) => {
      const key = `${s.action}|${s.goal.toLowerCase()}|${s.newGoal.toLowerCase()}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  if (!suggestions.length) return null

  const done = (s) => (s.action === 'add' ? goals.some((g) => same(g, s.goal))
    : s.action === 'remove' ? !goals.some((g) => same(g, s.goal)) : goals.some((g) => same(g, s.newGoal)))
  const apply = (s) => (s.action === 'add' ? [...goals, s.goal]
    : s.action === 'remove' ? goals.filter((g) => !same(g, s.goal)) : goals.map((g) => (same(g, s.goal) ? s.newGoal : g)))
  const text = (s) => (s.action === 'add' ? <>Add <b>“{s.goal}”</b> to your goals?</>
    : s.action === 'remove' ? <>Remove the goal <b>“{s.goal}”</b>?</> : <>Change <b>“{s.goal}”</b> to <b>“{s.newGoal}”</b>?</>)
  const verb = { add: 'Add to goals', remove: 'Remove goal', update: 'Update goal' }

  async function accept(s, key) {
    setBusy(key)
    setError('')
    try {
      await onSave(apply(s))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="goal-suggestions" role="group" aria-label="Goal suggestions">
      {suggestions.map((s) => {
        const key = `${s.action}|${s.goal}|${s.newGoal}`
        if (dismissed.includes(key)) return null
        const applied = done(s)
        return (
          <div key={key} className={`goal-card ${applied ? 'is-done' : ''}`}>
            <Icon name="goal" size={18} />
            <p>{applied ? <>✓ {s.action === 'add' ? 'Added to goals' : s.action === 'remove' ? 'Removed from goals' : 'Goal updated'}: <b>{s.action === 'update' ? s.newGoal : s.goal}</b></> : text(s)}</p>
            {!applied && (canEdit ? (
              <span className="goal-card-actions">
                <button className="btn btn-blue" disabled={!!busy} onClick={() => accept(s, key)}>{busy === key ? 'Saving' : verb[s.action]}</button>
                <button className="btn btn-ghost" disabled={!!busy} onClick={() => setDismissed((d) => [...d, key])}>Not now</button>
              </span>
            ) : <em>Only an owner, admin or analyst can change goals.</em>)}
          </div>
        )
      })}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  )
}
