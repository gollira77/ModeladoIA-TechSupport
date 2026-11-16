// Cliente HTTP del frontend. El token JWT se guarda en sessionStorage (se borra al cerrar la pestaña).
const TOKEN_KEY = 'ts_token'

export function getToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t) {
  try { t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY) } catch { /* sin storage */ }
}

export class ApiError extends Error {
  constructor(status, mensaje, datos) { super(mensaje); this.status = status; this.datos = datos }
}

export async function api(ruta, { method = 'GET', body, form } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body) headers['Content-Type'] = 'application/json'
  const r = await fetch(`/api${ruta}`, { method, headers, body: form || (body ? JSON.stringify(body) : undefined) })
  if (r.status === 401 && token) {
    setToken(null)
    window.dispatchEvent(new Event('sesion-vencida'))
  }
  const datos = await r.json().catch(() => ({}))
  if (!r.ok) {
    const d = datos.detail || {}
    throw new ApiError(r.status, d.mensaje || 'No se pudo completar la operación.', d)
  }
  return datos
}

// Chat con el agente: lee el stream SSE y llama a onEvento por cada evento del loop del agente.
export async function chatStream({ mensaje, session_id, adjuntos_ids }, onEvento, signal) {
  const r = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ mensaje, session_id, adjuntos_ids }),
    signal,
  })
  if (!r.ok) {
    const d = (await r.json().catch(() => ({}))).detail || {}
    throw new ApiError(r.status, d.mensaje || 'No se pudo enviar el mensaje.')
  }
  const lector = r.body.getReader()
  const dec = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await lector.read()
    if (done) break
    buffer += dec.decode(value, { stream: true })
    const bloques = buffer.split('\n\n')
    buffer = bloques.pop()
    for (const b of bloques) {
      const linea = b.split('\n').find((l) => l.startsWith('data: '))
      if (linea) onEvento(JSON.parse(linea.slice(6)))
    }
  }
}
