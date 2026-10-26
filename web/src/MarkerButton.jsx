import { useRef } from 'react'
import { useMarkerFill } from './markers.js'

export default function MarkerButton({ ready, busy, children }) {
  const btnRef = useRef(null)
  const active = useMarkerFill(btnRef, ready) && ready
  return (
    <button ref={btnRef} className={`btn btn-block access-btn ${active ? 'btn-blue' : 'btn-unfilled'}`} disabled={!active || busy}>
      <span className="btn-label">{children}</span>
      <span className="btn-ink" aria-hidden="true" />
      <span className="btn-label btn-label-lit" aria-hidden="true">{children}</span>
    </button>
  )
}
