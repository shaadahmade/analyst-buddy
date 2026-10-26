import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import Icon from './Icon.jsx'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const ZONES = ['Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Europe/London', 'Europe/Berlin', 'America/New_York', 'America/Los_Angeles', 'Australia/Sydney', 'UTC']
const hourLabel = (h) => `${String(h).padStart(2, '0')}:00`
const dateLabel = (name) => new Date(`${name}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

export default function Reports({ canManage, onAuthError }) {
  const [data, setData] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loaded, setLoaded] = useState({ name: null, html: '' })
  const [form, setForm] = useState(null)
  const [saveMsg, setSaveMsg] = useState('')
  const [loadError, setLoadError] = useState('')

  const handle = useCallback((err, show) => (err.status === 401 ? onAuthError(err.message) : show(err.message)), [onAuthError])

  const load = useCallback(async () => {
    try {
      const res = await api('/api/reports')
      setData(res)
      setForm((f) => f ?? { ...res.settings, recipientsText: res.settings.recipients.join('\n') })
      setSelected((s) => s ?? res.reports[0]?.name ?? null)
      setLoadError('')
    } catch (err) {
      handle(err, setLoadError)
    }
  }, [handle])

  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!data?.running) return
    const id = setInterval(load, 4000)
    return () => clearInterval(id)
  }, [data?.running, load])

  useEffect(() => {
    if (!selected) return
    let live = true
    api(`/api/reports/${selected}`).then((r) => live && setLoaded({ name: selected, html: r.html })).catch((err) => live && handle(err, setLoadError))
    return () => { live = false }
  }, [selected, handle])
  const preview = loaded.name === selected ? loaded.html : ''

  async function createNow() {
    try {
      await api('/api/reports/run', { method: 'POST' })
      setSelected(null)
      setData((d) => ({ ...d, running: true, error: null }))
    } catch (err) {
      handle(err, setLoadError)
    }
  }

  async function save(e) {
    e.preventDefault()
    setSaveMsg('')
    const body = {
      enabled: form.enabled, weekday: Number(form.weekday), hour: Number(form.hour), timezone: form.timezone,
      recipients: form.recipientsText.split(/[\s,;]+/).filter(Boolean),
    }
    try {
      const res = await api('/api/reports/settings', { method: 'PUT', body })
      setData((d) => ({ ...d, settings: res.settings }))
      setSaveMsg(res.settings.enabled ? `Saved. Next report: ${DAYS[res.settings.weekday]} at ${hourLabel(res.settings.hour)}.` : 'Saved. The schedule is off.')
    } catch (err) {
      handle(err, setSaveMsg)
    }
  }

  if (!data) return <div className="reports"><p className="rail-empty" role="status">{loadError || 'Loading reports'}</p></div>

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  return (
    <div className="reports">
      <section className="report-actions" aria-labelledby="create-h">
        <div>
          <h2 id="create-h">Weekly review</h2>
          <p className="lead">Your analyst checks the latest week against the previous four, scores every goal and picks three actions.</p>
        </div>
        {canManage && <button className="btn btn-blue" onClick={createNow} disabled={data.running}>
          {data.running ? <><span className="mini-spin" aria-hidden="true" />Creating report</> : <><Icon name="logo" size={18} />Create this week's report</>}
        </button>}
        {data.running && <p className="rail-empty" role="status">This takes a minute or two. You can keep chatting meanwhile.</p>}
        {(data.error || loadError) && <p className="error" role="alert">{data.error || loadError}</p>}
      </section>

      <div className="report-grid">
        <section className="report-list" aria-labelledby="past-h">
          <h3 id="past-h" className="rail-h">Past reports</h3>
          {data.reports.length === 0 ? (
            <p className="rail-empty">No reports yet. {canManage ? 'Create the first one now, or turn on the weekly schedule below.' : 'An owner or admin can create one.'}</p>
          ) : (
            <ul>
              {data.reports.map((r) => (
                <li key={r.name}>
                  <button className={`report-item ${selected === r.name ? 'on' : ''}`} aria-current={selected === r.name} onClick={() => setSelected(r.name)}>
                    <span className="report-date">{dateLabel(r.name)}{r.period ? `, for ${r.period}` : ''}</span>
                    <span className="report-head">
                      {r.figure && <b className={`tone-${r.figure_tone}`}>{r.figure}</b>}
                      <span>{r.headline}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {canManage && <form className="schedule" onSubmit={save} aria-labelledby="sched-h">
            <h3 id="sched-h" className="rail-h">Schedule</h3>
            <label className="check">
              <input type="checkbox" checked={form.enabled} onChange={set('enabled')} />
              Create a report every week
            </label>
            <div className="schedule-row">
              <label className="field"><span>Day</span>
                <select value={form.weekday} onChange={set('weekday')}>{DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}</select>
              </label>
              <label className="field"><span>Time</span>
                <select value={form.hour} onChange={set('hour')}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{hourLabel(h)}</option>)}</select>
              </label>
            </div>
            <label className="field"><span>Timezone</span>
              <select value={form.timezone} onChange={set('timezone')}>
                {[...new Set([form.timezone, ...ZONES])].map((z) => <option key={z} value={z}>{z}</option>)}
              </select>
            </label>
            <label className="field"><span>Send to <em>(one email per line)</em></span>
              <textarea rows={3} value={form.recipientsText} onChange={set('recipientsText')} placeholder="you@yourcompany.com" />
            </label>
            <p className="note">Email sending is not switched on yet. Reports are saved here and listed above.</p>
            <button className="btn btn-outline btn-block">Save schedule</button>
            {saveMsg && <p className="feedback-msg" role="status">{saveMsg}</p>}
        </form>}

        <section className="report-preview" aria-label="Report preview">
          {preview ? (
            <iframe title={`Weekly report ${selected}`} srcDoc={preview} sandbox="" />
          ) : (
            <div className="preview-empty">
              <p className="marker-note big">{data.running ? 'Writing your review' : 'Your Monday review lands here'}</p>
              <p className="lead">What changed, why, how each goal is doing, and what to do this week.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
