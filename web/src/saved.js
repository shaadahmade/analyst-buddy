const KEY = 'analyst-board:'

export function loadBoard(tenant) {
  try {
    return JSON.parse(sessionStorage.getItem(KEY + tenant)) ?? null
  } catch {
    return null
  }
}

export function saveBoard(tenant, board) {
  const lighter = { ...board, turns: board.turns.map((t) => (t.charts?.length || t.images?.length ? { ...t, charts: [], images: [], chartsDropped: Boolean(t.charts?.length) } : t)) }
  for (const b of [board, lighter]) {
    try {
      sessionStorage.setItem(KEY + tenant, JSON.stringify(b))
      return
    } catch {}
  }
}

export function forgetBoards() {
  try {
    for (const k of Object.keys(sessionStorage)) if (k.startsWith(KEY)) sessionStorage.removeItem(k)
  } catch {}
}
