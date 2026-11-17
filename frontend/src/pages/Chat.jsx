import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api, chatStream } from '../lib/api'
import { useAuth } from '../lib/auth'

// Nombres legibles de las herramientas para la traza del agente
const HERRAMIENTAS = {
  crear_ticket: 'Crear ticket',
  consultar_ticket: 'Consultar ticket',
  buscar_tickets: 'Buscar tickets',
  actualizar_estado: 'Actualizar estado',
  agregar_comentario: 'Agregar comentario',
  adjuntar_archivo: 'Adjuntar archivo',
  consultar_historial: 'Consultar historial',
  generar_resumen: 'Generar resumen',
  cambiar_prioridad: 'Cambiar prioridad',
  asignar_ticket: 'Asignar responsable',
  analizar_adjunto: 'Analizar adjunto',
  consultar_base_conocimiento: 'Consultar base de conocimiento (RAG)',
  derivar_a_humano: 'Derivar a una persona',
}

const SUGERENCIAS = {
  solicitante: [
    'No me anda la VPN desde casa',
    '¿Cuál es el estado del ticket 1052?',
    'Mostrame los tickets que tengo abiertos',
    'Mi impresora tiene una luz roja y no imprime',
  ],
  staff: [
    '¿Qué incidencias críticas siguen pendientes?',
    'Haceme un resumen de los tickets por estado y prioridad',
    'Mostrame el historial del ticket 1052',
    '¿Qué tickets activos hay de Redes y conectividad?',
  ],
}

const ACEPTA = 'image/png,image/jpeg,image/webp,image/bmp,image/gif,.txt,.log'
const CHAT_KEY = 'ts_chat'

function leerSesion() {
  try { return sessionStorage.getItem(CHAT_KEY) } catch { return null }
}
function guardarSesion(id) {
  try { id ? sessionStorage.setItem(CHAT_KEY, id) : sessionStorage.removeItem(CHAT_KEY) } catch { /* */ }
}

function ChipAdjunto({ a, onQuitar }) {
  const estado = a.subiendo ? 'Analizando…' : a.error ? 'Rechazado' : a.analisis_estado === 'ok' ? 'Analizado' : 'Análisis limitado'
  const color = a.error ? 'border-red-300 bg-red-50 text-red-700'
    : a.subiendo ? 'border-niebla-300 bg-niebla text-acero-500'
    : a.alerta_seguridad?.includes('injection') ? 'border-amber-300 bg-amber-50 text-amber-800'
    : a.analisis_estado === 'ok' ? 'border-esmeralda/40 bg-esmeralda-50 text-esmeralda-700' : 'border-amber-300 bg-amber-50 text-amber-800'
  return (
    <details className={`group relative rounded-md border px-2.5 py-1 text-xs ${color}`}>
      <summary className="flex cursor-pointer list-none items-center gap-2">
        <span className="max-w-[180px] truncate font-medium">{a.nombre}</span>
        <span className={a.subiendo ? 'latido' : ''}>{estado}</span>
        {onQuitar && !a.subiendo && (
          <button type="button" onClick={(e) => { e.preventDefault(); onQuitar() }} className="ml-1 text-acero-300 hover:text-red-600" aria-label="Quitar adjunto">✕</button>
        )}
      </summary>
      {(a.analisis || a.error) && (
        <div className="absolute bottom-full left-0 z-10 mb-2 max-h-72 w-[min(28rem,80vw)] overflow-auto rounded-md border border-niebla-300 bg-white p-3 text-tinta shadow-lg">
          {a.error ? <p className="text-red-700">{a.error}</p> : (
            <>
              <p className="mb-1 font-medium text-acero">Lo que el sistema extrajo del archivo</p>
              {a.alerta_seguridad && <p className="mb-2 rounded bg-amber-50 px-2 py-1 text-amber-800">Alerta: {a.alerta_seguridad}</p>}
              <pre className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-acero-700">{a.analisis}</pre>
            </>
          )}
        </div>
      )}
    </details>
  )
}

function Traza({ pasos, activo }) {
  if (!pasos?.length && !activo) {
    return (
      <p className="text-sm leading-relaxed text-acero-500">
        Acá vas a ver cómo trabaja el agente en cada mensaje: qué herramientas decide usar, con qué datos y qué
        le devolvieron. El modelo no toca la base de datos directamente; solo pide ejecutar herramientas.
      </p>
    )
  }
  return (
    <ol className="relative space-y-4 border-l border-niebla-300 pl-5">
      {(pasos || []).map((p, i) => (
        <li key={i} className="relative">
          <span className={`absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-white ${
            p.tipo === 'guardrail' || p.tipo === 'error' ? 'bg-amber-500' : p.tipo === 'resultado' ? 'bg-esmeralda' : 'bg-acero'}`} />
          {p.tipo === 'herramienta' && (
            <>
              <p className="text-sm font-medium text-acero">{HERRAMIENTAS[p.nombre] || p.nombre}</p>
              {Object.keys(p.args || {}).length > 0 && (
                <dl className="mt-1 space-y-0.5 text-xs">
                  {Object.entries(p.args).filter(([, v]) => v !== '' && v !== false && v !== null && !(Array.isArray(v) && !v.length)).map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <dt className="shrink-0 text-acero-300">{k.replaceAll('_', ' ')}</dt>
                      <dd className="min-w-0 break-words text-acero-700">{typeof v === 'object' ? JSON.stringify(v) : String(v).slice(0, 140)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </>
          )}
          {p.tipo === 'resultado' && <p className="text-xs text-esmeralda-700">{p.resumen}</p>}
          {p.tipo === 'guardrail' && <p className="text-sm font-medium text-amber-700">{p.mensaje}<span className="block text-xs font-normal text-acero-500">El mensaje no llegó al modelo.</span></p>}
          {p.tipo === 'error' && <p className="text-sm text-amber-700">{p.mensaje}</p>}
        </li>
      ))}
      {activo && (
        <li className="relative">
          <span className="latido absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-white bg-esmeralda" />
          <p className="text-sm text-acero-500">Razonando…</p>
        </li>
      )}
    </ol>
  )
}

export default function Chat() {
  const { usuario, esStaff } = useAuth()
  const [mensajes, setMensajes] = useState([])
  const [texto, setTexto] = useState('')
  const [adjuntos, setAdjuntos] = useState([])
  const [sessionId, setSessionId] = useState(leerSesion())
  const [enviando, setEnviando] = useState(false)
  const [seleccion, setSeleccion] = useState(null)
  const [arrastrando, setArrastrando] = useState(false)
  const finRef = useRef(null)
  const inputArchivo = useRef(null)

  useEffect(() => {
    if (sessionId && mensajes.length === 0) {
      api(`/chat/sesiones/${sessionId}`).then((r) => setMensajes(r.mensajes)).catch(() => {})
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { finRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [mensajes])

  async function subir(files) {
    for (const f of Array.from(files).slice(0, 5 - adjuntos.length)) {
      const temp = { tmp: crypto.randomUUID(), nombre: f.name, subiendo: true }
      setAdjuntos((a) => [...a, temp])
      const form = new FormData()
      form.append('archivo', f)
      try {
        const r = await api('/adjuntos', { method: 'POST', form })
        setAdjuntos((a) => a.map((x) => (x.tmp === temp.tmp ? r : x)))
      } catch (e) {
        setAdjuntos((a) => a.map((x) => (x.tmp === temp.tmp ? { ...x, subiendo: false, error: e.message } : x)))
      }
    }
  }

  async function enviar(contenido = texto) {
    const listos = adjuntos.filter((a) => a.id)
    if ((!contenido.trim() && !listos.length) || enviando || adjuntos.some((a) => a.subiendo)) return
    const idx = mensajes.length + 1
    setMensajes((m) => [...m, { rol: 'usuario', texto: contenido, adjuntos: listos }, { rol: 'agente', texto: '', pasos: [], activo: true }])
    setSeleccion(idx)
    setTexto('')
    setAdjuntos([])
    setEnviando(true)
    const actualizar = (fn) => setMensajes((m) => m.map((x, i) => (i === idx ? fn(x) : x)))
    try {
      await chatStream({ mensaje: contenido, session_id: sessionId, adjuntos_ids: listos.map((a) => a.id) }, (ev) => {
        if (ev.tipo === 'sesion') { setSessionId(ev.session_id); guardarSesion(ev.session_id) }
        else if (ev.tipo === 'respuesta') actualizar((x) => ({ ...x, texto: x.texto ? `${x.texto}\n\n${ev.texto}` : ev.texto }))
        else if (ev.tipo === 'error') actualizar((x) => ({ ...x, error: ev.mensaje, pasos: [...x.pasos, ev] }))
        else if (ev.tipo !== 'fin') actualizar((x) => ({ ...x, pasos: [...x.pasos, ev], bloqueado: x.bloqueado || ev.tipo === 'guardrail' }))
      })
    } catch (e) {
      actualizar((x) => ({ ...x, error: e.message }))
    } finally {
      actualizar((x) => ({ ...x, activo: false }))
      setEnviando(false)
    }
  }

  function nuevaConversacion() {
    guardarSesion(null)
    setSessionId(null)
    setMensajes([])
    setSeleccion(null)
  }

  const pasosVisibles = (seleccion != null ? mensajes[seleccion] : [...mensajes].reverse().find((m) => m.rol === 'agente'))
  const sugerencias = esStaff ? SUGERENCIAS.staff : SUGERENCIAS.solicitante

  return (
    <div className="flex h-[calc(100vh-57px)] md:h-screen">
      <section
        className={`relative flex min-w-0 flex-1 flex-col ${arrastrando ? 'ring-2 ring-inset ring-esmeralda' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setArrastrando(true) }}
        onDragLeave={() => setArrastrando(false)}
        onDrop={(e) => { e.preventDefault(); setArrastrando(false); subir(e.dataTransfer.files) }}
      >
        <header className="flex items-center justify-between border-b border-niebla-300 bg-white px-6 py-4">
          <div>
            <h1 className="text-lg font-semibold text-acero">TechBot</h1>
            <p className="text-xs text-acero-500">Asistente de la Mesa de Ayuda · responde solo sobre soporte técnico</p>
          </div>
          <button className="btn-sec py-1.5 text-xs" onClick={nuevaConversacion} disabled={enviando}>Nueva conversación</button>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
          {mensajes.length === 0 ? (
            <div className="mx-auto mt-6 max-w-3xl xl:max-w-4xl 2xl:max-w-5xl">
              <h2 className="text-2xl font-semibold text-acero">Hola, {usuario.nombre.split(' ')[0]}.</h2>
              <p className="mt-2 text-acero-500">
                Contame qué está fallando como se lo dirías a un compañero. Podés arrastrar capturas, fotos del equipo
                o archivos .log y .txt: los analizo antes de registrar el ticket.
              </p>
              <div className="mt-6 grid gap-2 sm:grid-cols-2">
                {sugerencias.map((s) => (
                  <button key={s} onClick={() => enviar(s)} className="rounded-md border border-niebla-300 bg-white px-3 py-2.5 text-left text-sm text-acero hover:border-esmeralda">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-5 xl:max-w-4xl 2xl:max-w-5xl">
              {mensajes.map((m, i) => m.rol === 'usuario' ? (
                <div key={i} className="flex flex-col items-end">
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-lg rounded-br-sm bg-acero px-4 py-2.5 text-sm text-white">{m.texto}</div>
                  {m.adjuntos?.length > 0 && (
                    <div className="mt-1 flex flex-wrap justify-end gap-1">{m.adjuntos.map((a) => <ChipAdjunto key={a.id} a={a} />)}</div>
                  )}
                </div>
              ) : (
                <div key={i} className="flex gap-3">
                  <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-md bg-acero-100 text-xs font-semibold text-acero">TB</div>
                  <div className="min-w-0 flex-1">
                    <div className={`md rounded-lg border px-4 py-2.5 text-sm leading-relaxed ${m.bloqueado ? 'border-amber-300 bg-amber-50' : 'border-niebla-300 bg-white'}`}>
                      {m.texto ? <ReactMarkdown>{m.texto}</ReactMarkdown> : m.activo ? <span className="latido text-acero-300">Pensando…</span> : null}
                      {m.error && <p className="mt-1 text-amber-700">{m.error}</p>}
                    </div>
                    {m.pasos?.length > 0 && (
                      <button onClick={() => setSeleccion(i)} className={`mt-1 text-xs ${seleccion === i ? 'text-esmeralda-700' : 'text-acero-300 hover:text-acero'}`}>
                        {m.pasos.filter((p) => p.tipo === 'herramienta').length} herramienta(s) usadas · ver traza
                      </button>
                    )}
                  </div>
                </div>
              ))}
              <div ref={finRef} />
            </div>
          )}
        </div>

        <form onSubmit={(e) => { e.preventDefault(); enviar() }} className="border-t border-niebla-300 bg-white px-4 py-3 sm:px-8">
          <div className="mx-auto max-w-3xl xl:max-w-4xl 2xl:max-w-5xl">
            {adjuntos.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {adjuntos.map((a, i) => <ChipAdjunto key={a.id || a.tmp} a={a} onQuitar={() => setAdjuntos((x) => x.filter((_, j) => j !== i))} />)}
              </div>
            )}
            <div className="flex items-end gap-2">
              <button type="button" className="btn-sec px-3" onClick={() => inputArchivo.current?.click()} disabled={adjuntos.length >= 5} title="Adjuntar imagen, captura, .txt o .log">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M21.4 11.1l-9.2 9.2a6 6 0 01-8.5-8.5l9.2-9.2a4 4 0 015.7 5.7l-9.2 9.2a2 2 0 01-2.8-2.8l8.5-8.5" /></svg>
                <span className="sr-only">Adjuntar archivo</span>
              </button>
              <input ref={inputArchivo} type="file" accept={ACEPTA} multiple hidden onChange={(e) => { subir(e.target.files); e.target.value = '' }} />
              <textarea
                className="campo max-h-40 min-h-[42px] resize-none"
                rows={1}
                placeholder="Describí el problema o hacé una consulta sobre tus tickets…"
                value={texto}
                maxLength={4000}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar() } }}
              />
              <button className="btn-esmeralda" disabled={enviando || adjuntos.some((a) => a.subiendo)}>Enviar</button>
            </div>
            <p className="mt-1.5 text-[11px] text-acero-300">Imágenes, capturas, .txt y .log hasta 8 MB. No compartas contraseñas: el asistente nunca te las va a pedir.</p>
          </div>
        </form>
      </section>

      <aside className="hidden w-80 shrink-0 overflow-y-auto border-l border-niebla-300 bg-niebla px-5 py-5 lg:block xl:w-96 2xl:w-[26rem]">
        <h2 className="text-sm font-semibold text-acero">Traza del agente</h2>
        <p className="mb-4 text-xs text-acero-500">Herramientas que decidió usar en el mensaje seleccionado</p>
        <Traza pasos={pasosVisibles?.pasos} activo={pasosVisibles?.activo} />
      </aside>
    </div>
  )
}
