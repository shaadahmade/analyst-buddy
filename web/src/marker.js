
const PICKABLE = '.q p, .answer-body p, .answer-body li, .answer-body h1, .answer-body h2, .answer-body h3, .answer-body tr, .mon-code, .mon-out, .answer-chart, .starter'
export const MAX_CONTEXT = 8000

export function picks(rect, box) {
  const w = Math.min(rect.right, box.right) - Math.max(rect.left, box.left)
  const h = Math.min(rect.bottom, box.bottom) - Math.max(rect.top, box.top)
  if (w <= 0 || h <= 0) return false
  const cx = (rect.left + rect.right) / 2
  const cy = (rect.top + rect.bottom) / 2
  if (cx >= box.left && cx <= box.right && cy >= box.top && cy <= box.bottom) return true
  const overlap = w * h
  const area = (r) => (r.right - r.left) * (r.bottom - r.top)
  return overlap >= 0.4 * area(rect) || overlap >= 0.4 * area(box)
}

function describe(el) {
  if (el.matches('tr')) return [...el.cells].map((c) => c.textContent.trim()).join(' | ')
  if (el.matches('.answer-chart')) return `[chart: ${el.alt}]`
  if (el.matches('.mon-code')) return `code the analyst ran:\n${el.textContent.trim()}`
  if (el.matches('.mon-out')) return `output:\n${el.textContent.trim()}`
  return el.textContent.trim()
}

export function markedText(feed, box) {
  const groups = new Map()
  let count = 0
  for (const el of feed.querySelectorAll(PICKABLE)) {
    if (!picks(el.getBoundingClientRect(), box)) continue
    const turn = el.closest('.turn')
    const where = el.matches('.q p') ? 'Your earlier question'
      : turn ? `From the answer to "${turn.querySelector('.q p')?.textContent.trim()}"` : 'From the board'
    if (!groups.has(where)) groups.set(where, [])
    const lines = groups.get(where)
    const head = el.matches('tr') && el.closest('table')?.rows[0]
    if (head && head !== el && !lines.includes(describe(head))) lines.push(describe(head))
    lines.push(describe(el))
    count++
  }
  const text = [...groups].map(([where, lines]) => `${where}:\n${lines.join('\n')}`).join('\n\n')
  return { text: text.slice(0, MAX_CONTEXT), count }
}

export function rub(strokes, [x, y], r) {
  const at = (a, b, t) => [Math.round((a[0] + (b[0] - a[0]) * t) * 10) / 10, Math.round((a[1] + (b[1] - a[1]) * t) * 10) / 10]
  const under = (a, b) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], fx = a[0] - x, fy = a[1] - y
    const A = dx * dx + dy * dy
    if (!A) return Math.hypot(fx, fy) < r ? [0, 1] : null
    const B = 2 * (fx * dx + fy * dy), disc = B * B - 4 * A * (fx * fx + fy * fy - r * r)
    if (disc <= 0) return null
    const t1 = (-B - Math.sqrt(disc)) / (2 * A), t2 = (-B + Math.sqrt(disc)) / (2 * A)
    return t2 <= 0 || t1 >= 1 ? null : [Math.max(0, t1), Math.min(1, t2)]
  }
  return strokes.flatMap((s) => {
    const runs = [[]]
    for (let i = 1; i < s.pts.length; i++) {
      const a = s.pts[i - 1], b = s.pts[i]
      const cut = under(a, b)
      if (!runs.at(-1).length && (!cut || cut[0] > 0)) runs.at(-1).push(a)
      if (!cut) {
        runs.at(-1).push(b)
        continue
      }
      if (cut[0] > 0) {
        runs.at(-1).push(at(a, b, cut[0]))
        runs.push([])
      }
      if (cut[1] < 1) runs.at(-1).push(at(a, b, cut[1]), b)
    }
    return runs.filter((run) => run.length > 1).map((pts) => ({ tone: s.tone, pts }))
  })
}

export function pathOf(pts) {
  if (pts.length < 3) return `M${pts.map((p) => p.join(' ')).join(' L')}`
  let d = `M${pts[0].join(' ')}`
  for (let i = 1; i < pts.length - 1; i++) {
    d += ` Q${pts[i].join(' ')} ${(pts[i][0] + pts[i + 1][0]) / 2} ${(pts[i][1] + pts[i + 1][1]) / 2}`
  }
  return `${d} L${pts.at(-1).join(' ')}`
}

export const history = {
  start: (now) => ({ past: [], now, future: [] }),
  change: (h, now) => ({ past: [...h.past, h.now].slice(-100), now, future: [] }),
  replace: (h, now) => ({ ...h, now }),
  undo: (h) => (h.past.length ? { past: h.past.slice(0, -1), now: h.past.at(-1), future: [h.now, ...h.future] } : h),
  redo: (h) => (h.future.length ? { past: [...h.past, h.now], now: h.future[0], future: h.future.slice(1) } : h),
}
