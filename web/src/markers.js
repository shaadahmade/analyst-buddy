import { useEffect, useState } from 'react'

const DRAW_EASE = 'cubic-bezier(0.3, 0.7, 0.2, 1)'
const MOVE_EASE = 'cubic-bezier(0.45, 0, 0.25, 1)'
const HELD = 120
const NIB = 40
const UNCAP = 30

const BARREL = 66

export function canLend(frame, tone) {
  const cap = frame?.querySelector(`.tray .cap.${tone}`)
  return !!cap?.offsetParent && cap.offsetWidth === BARREL && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function lendMarker(frame, tone) {
  const cap = frame.querySelector(`.tray .cap.${tone}`)
  const pen = document.createElement('i')
  pen.className = `cap ${tone} flying-marker`
  if (tone === 'magic') {
    const tag = document.createElement('b')
    tag.className = 'ai-tag'
    tag.textContent = 'AI'
    pen.append(tag)
  }
  const lid = document.createElement('i')
  lid.className = `cap ${tone} lying-cap`
  for (const el of [pen, lid]) el.setAttribute('aria-hidden', 'true')
  let cancelled = false
  let deg, rest, out, above, last

  const local = (q) => {
    const box = frame.getBoundingClientRect()
    return [q.x - box.left, q.y - box.top]
  }
  const at = ([x, y], r) => ({ transform: `translate(${x}px, ${y}px) rotate(${r}deg)` })
  async function fly(frames, duration, easing = MOVE_EASE) {
    const a = pen.animate(frames, { duration, easing, fill: 'forwards' })
    await a.finished
    a.commitStyles()
    a.cancel()
  }
  function cleanup() {
    pen.getAnimations().forEach((a) => a.cancel())
    pen.remove()
    lid.remove()
    delete cap.dataset.uncapped
  }

  return {
    async takeOut(to) {
      await document.fonts.ready
      if (cancelled) throw new Error('cancelled')
      const box = frame.getBoundingClientRect()
      const c = cap.getBoundingClientRect()
      const m = new DOMMatrix(getComputedStyle(cap).transform)
      const tilt = Math.atan2(m.b, m.a)
      deg = (tilt * 180) / Math.PI
      const cx = (c.left + c.right) / 2 - box.left
      const cy = (c.top + c.bottom) / 2 - box.top
      const nibAt = (back) => [cx + (NIB - back) * Math.cos(tilt), cy + (NIB - back) * Math.sin(tilt)]
      rest = nibAt(0)
      out = nibAt(UNCAP)
      above = [out[0] - 10, out[1] - 50]
      pen.style.transform = at(rest, deg).transform
      Object.assign(lid.style, { left: `${cx - 33}px`, top: `${cy - 6}px`, transform: `rotate(${deg}deg)` })
      frame.append(pen, lid)
      cap.dataset.uncapped = ''
      await fly([at(rest, deg), at(out, deg)], 260, 'cubic-bezier(0.3, 0, 0.2, 1)')
      pen.classList.add('lifted')
      last = local(to())
      await fly([at(out, deg), at(above, 60), at(last, HELD)], 760)
    },
    hold(q) {
      last = local(q)
      pen.style.transform = at(last, HELD).transform
    },
    async putBack() {
      await fly([at(last, HELD), at(above, 60), at(out, deg)], 700)
      pen.classList.remove('lifted')
      await fly([at(out, deg), at(rest, deg)], 240, 'cubic-bezier(0.5, 0, 0.7, 1)')
      cleanup()
    },
    cancel() {
      cancelled = true
      cleanup()
    },
  }
}

export function canLendEraser(frame) {
  return !!frame?.querySelector('.tray .eraser')?.offsetParent && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function lendEraser(frame) {
  const block = frame.querySelector('.tray .eraser')
  const held = document.createElement('i')
  held.className = 'eraser flying-eraser'
  held.setAttribute('aria-hidden', 'true')
  let cancelled = false
  let rest, last
  const local = (q) => {
    const box = frame.getBoundingClientRect()
    return [q.x - box.left, q.y - box.top]
  }
  const at = ([x, y], r) => ({ transform: `translate(${x}px, ${y}px) rotate(${r}deg)` })
  async function fly(frames, duration) {
    const a = held.animate(frames, { duration, easing: MOVE_EASE, fill: 'forwards' })
    await a.finished
    a.commitStyles()
    a.cancel()
  }
  function cleanup() {
    held.getAnimations().forEach((a) => a.cancel())
    held.remove()
    delete block.dataset.lent
  }
  return {
    async takeOut(to) {
      if (cancelled) throw new Error('cancelled')
      const b = block.getBoundingClientRect()
      rest = local({ x: (b.left + b.right) / 2, y: (b.top + b.bottom) / 2 })
      held.style.transform = at(rest, 0).transform
      frame.append(held)
      block.dataset.lent = ''
      held.classList.add('lifted')
      last = local(to())
      await fly([at(rest, 0), at([rest[0], rest[1] - 40], -6), at(last, -8)], 620)
    },
    hold(q) {
      last = local(q)
      held.style.transform = at(last, -8).transform
    },
    async putBack() {
      await fly([at(last, -8), at([rest[0], rest[1] - 40], -6), at(rest, 0)], 560)
      cleanup()
    },
    cancel() {
      cancelled = true
      cleanup()
    },
  }
}

function markerTrip(frame, tone, { begin, pointAt }) {
  const hand = lendMarker(frame, tone)
  let cancelled = false
  let ink = null
  const done = (async () => {
    try {
      await hand.takeOut(() => pointAt(0))
      ink = begin()
      await new Promise((resolve) => {
        const follow = () => {
          if (cancelled) return resolve()
          hand.hold(pointAt(ink.effect.getComputedTiming().progress ?? 1))
          if (ink.playState === 'finished') return resolve()
          requestAnimationFrame(follow)
        }
        follow()
      })
      if (cancelled) return false
      await hand.putBack()
      return true
    } catch {
      return false
    }
  })()
  return {
    done,
    cancel() {
      cancelled = true
      ink?.cancel()
      hand.cancel()
    },
  }
}

function scribble(el) {
  const w = el.clientWidth
  const h = el.clientHeight
  const NS = 'http://www.w3.org/2000/svg'
  const svg = document.createElementNS(NS, 'svg')
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`)
  svg.setAttribute('preserveAspectRatio', 'none')
  const line = document.createElementNS(NS, 'polyline')
  const step = 11
  const points = []
  for (let i = 0, x = 4; x <= w - 4 + step; i++, x += step) points.push(`${Math.min(x, w - 4)},${i % 2 ? h + 14 : -14}`)
  line.setAttribute('points', points.join(' '))
  line.setAttribute('pathLength', '1000')
  svg.append(line)
  return { svg, line }
}

export function useMarkerStroke(rootRef, selector, tone, deps) {
  useEffect(() => {
    const root = rootRef.current
    const path = root?.querySelector(selector)
    const frame = root?.closest('.board-frame')
    if (!path || !canLend(frame, tone)) return
    path.style.animation = 'none'
    path.style.opacity = '0'
    const trip = markerTrip(frame, tone, {
      begin: () => path.animate([{ strokeDashoffset: 900, opacity: 1 }, { strokeDashoffset: 0, opacity: 1 }],
        { duration: 900, easing: DRAW_EASE, fill: 'forwards' }),
      pointAt: (progress) => {
        const p = path.getPointAtLength(path.getTotalLength() * progress)
        return new DOMPoint(p.x, p.y).matrixTransform(path.getScreenCTM())
      },
    })
    return () => trip.cancel()
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps -- callers list what should redraw it
}

export function useMarkerFill(btnRef, ready) {
  const [filled, setFilled] = useState(false)
  useEffect(() => {
    if (!ready) return
    const btn = btnRef.current
    const frame = btn?.closest('.board-frame')
    if (!canLend(frame, 'blue')) {
      setFilled(true)
      return () => setFilled(false)
    }
    const layer = btn.querySelector('.btn-ink')
    const lit = btn.querySelector('.btn-label-lit')
    const { svg, line } = scribble(btn)
    layer.replaceChildren(svg)
    let reveal = null
    const fill = { duration: 1100, easing: 'cubic-bezier(0.4, 0, 0.6, 1)', fill: 'forwards' }
    const trip = markerTrip(frame, 'blue', {
      begin: () => {
        reveal = lit.animate([{ clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)' }], fill)
        return line.animate([{ strokeDashoffset: 1000, opacity: 1 }, { strokeDashoffset: 0, opacity: 1 }], fill)
      },
      pointAt: (progress) => {
        const p = line.getPointAtLength(line.getTotalLength() * progress)
        return new DOMPoint(p.x, p.y).matrixTransform(line.getScreenCTM())
      },
    })
    trip.done.then((finished) => finished && setFilled(true))
    return () => {
      trip.cancel()
      reveal?.cancel()
      layer.replaceChildren()
      setFilled(false)
    }
  }, [btnRef, ready])

  return filled
}
