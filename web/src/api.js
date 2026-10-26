const TOKEN_KEY = 'analyst-token'

export function loadToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null }
}

export function saveToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {}
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

async function request(path, { method = 'GET', body, form } = {}) {
  const headers = {}
  const token = loadToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body) headers['Content-Type'] = 'application/json'
  let res
  try {
    res = await fetch(path, { method, headers, body: form ?? (body && JSON.stringify(body)) })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is the backend running?')
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, typeof data.detail === 'string' ? data.detail : `Server error (${res.status})`)
  }
  return res
}

export async function api(path, options) {
  return (await request(path, options)).json().catch(() => ({}))
}

export async function apiStream(path, body, onEvent) {
  const res = await request(path, { method: 'POST', body })
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  for (;;) {
    let chunk
    try {
      chunk = await reader.read()
    } catch {
      throw new ApiError(0, 'Lost the connection to the server.')
    }
    if (chunk.done) return
    buf += chunk.value
    const lines = buf.split('\n')
    buf = lines.pop()
    for (const line of lines) if (line) onEvent(JSON.parse(line))
  }
}
