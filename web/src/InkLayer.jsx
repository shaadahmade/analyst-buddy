import { useEffect, useImperativeHandle, useRef, useState } from 'react'
import { history, pathOf, rub } from './marker.js'

const ERASER_RADIUS = 20

export default function InkLayer({ feedRef, saved, keep, tool, height, onLetGo, onInkChange, ref }) {
  const [board, setBoard] = useState(() => history.start(saved))
  const strokes = board.now
  const live = useRef(null)
  const liveEl = useRef(null)
  const rubbing = useRef(null)

  useImperativeHandle(ref, () => ({
    undo: () => setBoard(history.undo),
    redo: () => setBoard(history.redo),
    clear: () => setBoard((h) => (h.now.length ? history.change(h, []) : h)),
  }), [])
  useEffect(() => keep(strokes), [keep, strokes])
  const hasInk = strokes.length > 0
  const canUndo = board.past.length > 0
  const canRedo = board.future.length > 0
  useEffect(() => onInkChange({ hasInk, canUndo, canRedo }), [hasInk, canUndo, canRedo, onInkChange])

  function boardPoint(e) {
    const f = feedRef.current
    const b = f.getBoundingClientRect()
    return [Math.round(e.clientX - b.left - f.clientLeft + f.scrollLeft), Math.round(e.clientY - b.top - f.clientTop + f.scrollTop)]
  }
  const samples = (e) => e.nativeEvent.getCoalescedEvents?.() ?? [e]

  function down(e) {
    if (!tool) return
    e.currentTarget.setPointerCapture(e.pointerId)
    if (tool === 'eraser') {
      rubbing.current = strokes
      const p = boardPoint(e)
      setBoard((h) => history.replace(h, rub(h.now, p, ERASER_RADIUS)))
      return
    }
    live.current = { tone: tool, pts: [boardPoint(e)], screen: [[e.clientX, e.clientY]] }
    liveEl.current.setAttribute('class', `tone-${tool}`)
    liveEl.current.setAttribute('d', pathOf(live.current.pts))
  }

  function move(e) {
    if (rubbing.current) {
      const points = samples(e).map(boardPoint)
      setBoard((h) => history.replace(h, points.reduce((left, p) => rub(left, p, ERASER_RADIUS), h.now)))
      return
    }
    const s = live.current
    if (!s) return
    for (const c of samples(e)) {
      s.pts.push(boardPoint(c))
      s.screen.push([c.clientX, c.clientY])
    }
    liveEl.current.setAttribute('d', pathOf(s.pts))
  }

  function up() {
    if (rubbing.current) {
      const before = rubbing.current
      rubbing.current = null
      if (JSON.stringify(before) !== JSON.stringify(strokes)) {
        setBoard((h) => ({ past: [...h.past, before].slice(-100), now: h.now, future: [] }))
      }
      return onLetGo('eraser', null)
    }
    const s = live.current
    live.current = null
    if (!s) return
    const path = liveEl.current
    const xs = s.screen.map((p) => p[0])
    const ys = s.screen.map((p) => p[1])
    const box = { left: Math.min(...xs), right: Math.max(...xs), top: Math.min(...ys), bottom: Math.max(...ys) }
    const small = box.right - box.left < 12 && box.bottom - box.top < 12
    if (s.tone === 'magic' && !small) {
      Promise.resolve(onLetGo(s.tone, box)).finally(() => {
        if (live.current) return
        path.classList.add('fading')
        setTimeout(() => { if (!live.current) path.setAttribute('d', '') }, 400)
      })
      return
    }
    path.setAttribute('d', '')
    if (small) return onLetGo(s.tone, null)
    setBoard((h) => history.change(h, [...h.now, { tone: s.tone, pts: s.pts }]))
    onLetGo(s.tone, box)
  }

  return (
    <svg className="marker-layer" style={{ height }} aria-hidden="true"
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
      {strokes.map((k, i) => <path key={i} d={pathOf(k.pts)} className={`tone-${k.tone}`} />)}
      <path ref={liveEl} d="" />
    </svg>
  )
}
