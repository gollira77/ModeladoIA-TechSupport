import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, getToken } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Estado, NumeroTicket, Prioridad } from '../components/Insignias'

const EVENTOS = {
  CREACION: 'Creación', CAMBIO_ESTADO: 'Cambio de estado', CAMBIO_PRIORIDAD: 'Cambio de prioridad',
  COMENTARIO: 'Comentario', ADJUNTO: 'Archivo adjuntado', ASIGNACION: 'Asignación', REASIGNACION: 'Reasignación',
}
const EXIGE_MOTIVO = ['Pendiente', 'Resuelto', 'Cerrado']

function Dato({ titulo, children }) {
  if (!children) return null
  return (
    <div>
      <dt className="text-xs text-acero-500">{titulo}</dt>
      <dd className="mt-0.5 whitespace-pre-wrap text-sm text-tinta">{children}</dd>
    </div>
  )
}

function Adjunto({ a }) {
  async function abrir() {
    const r = await fetch(`/api/adjuntos/${a.id}/archivo`, { headers: { Authorization: `Bearer ${getToken()}` } })
    if (!r.ok) return
    const url = URL.createObjectURL(await r.blob())
    window.open(url, '_blank', 'noopener')
  }
  return (
    <li className="flex items-center justify-between gap-3 rounded-md border border-niebla-300 px-3 py-2 text-sm">
      <span className="min-w-0 truncate"><span className="font-mono text-xs text-acero-300">{a.id}</span> {a.nombre}</span>
      <span className="flex shrink-0 items-center gap-3">
        <span className={`text-xs ${a.analisis_estado === 'ok' ? 'text-esmeralda-700' : 'text-amber-700'}`}>{a.analisis_estado === 'ok' ? 'analizado' : `análisis ${a.analisis_estado}`}</span>
        <button onClick={abrir} className="text-xs text-acero hover:underline">Abrir</button>
      </span>
    </li>
  )
}

export default function TicketDetalle() {
  const { id } = useParams()
  const { usuario, esStaff } = useAuth()
  const [t, setT] = useState(null)
  const [hist, setHist] = useState([])
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [destino, setDestino] = useState('')
  const [motivo, setMotivo] = useState('')
  const [comentario, setComentario] = useState('')
  const [interno, setInterno] = useState(false)
  const [prioridad, setPrioridad] = useState({ valor: '', motivo: '' })
  const [tecnicos, setTecnicos] = useState([])
  const [tecnico, setTecnico] = useState('')

  const cargar = useCallback(() => {
    api(`/tickets/${id}`).then(setT).catch((e) => setError(e.message))
    api(`/tickets/${id}/historial`).then((h) => setHist(h.eventos)).catch(() => {})
  }, [id])
  useEffect(() => { cargar() }, [cargar])
  useEffect(() => { if (usuario.rol === 'supervisor') api('/tecnicos').then(setTecnicos) }, [usuario.rol])

  async function accion(fn, ok) {
    setAviso(''); setError('')
    try { await fn(); setAviso(ok); cargar(); return true } catch (e) { setError(e.message); return false }
  }

  if (error && !t) return (
    <div className="mx-auto max-w-3xl px-8 py-16 text-center">
      <p className="text-lg font-medium text-acero">{error}</p>
      <Link to="/tickets" className="btn-sec mt-6">Volver a tickets</Link>
    </div>
  )
  if (!t) return <p className="p-8 text-acero-300">Cargando…</p>

  const cerrado = t.estado === 'Cerrado'

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-8">
      <Link to="/tickets" className="text-sm text-acero-500 hover:text-acero">‹ Tickets</Link>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <NumeroTicket id={t.id} className="text-sm" />
          <h1 className="titulo-pagina mt-1">{t.titulo}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
            <Estado valor={t.estado} />
            <Prioridad valor={t.prioridad} />
            <span className="text-acero-500">{t.categoria}</span>
            {!t.prioridad_revisada_por_soporte && !cerrado && (
              <span className="rounded bg-niebla-200 px-2 py-0.5 text-xs text-acero-500">Prioridad propuesta por el asistente, pendiente de revisión</span>
            )}
          </div>
        </div>
      </div>

      {(aviso || error) && (
        <p className={`mt-4 rounded-md px-3 py-2 text-sm ${error ? 'bg-red-50 text-red-700' : 'bg-esmeralda-50 text-esmeralda-700'}`} role="status">{error || aviso}</p>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <section className="panel p-5">
            <dl className="grid gap-4 sm:grid-cols-2">
              <Dato titulo="Solicitante">{`${t.solicitante}${t.solicitante_area ? ` · ${t.solicitante_area}` : ''}`}</Dato>
              <Dato titulo="Responsable">{t.responsable}</Dato>
              <Dato titulo="Creado">{t.creado}</Dato>
              <Dato titulo="Última actualización">{t.actualizado}</Dato>
              <Dato titulo="Sistema afectado">{t.sistema_afectado}</Dato>
              <Dato titulo="Alcance">{t.usuarios_afectados}</Dato>
            </dl>
            <dl className="mt-5 space-y-4 border-t border-niebla-200 pt-5">
              <Dato titulo="Descripción">{t.descripcion}</Dato>
              {t.mensaje_error && (
                <div>
                  <dt className="text-xs text-acero-500">Mensaje de error</dt>
                  <dd className="mt-1 rounded-md bg-acero-900 px-3 py-2 font-mono text-xs text-esmeralda-100">{t.mensaje_error}</dd>
                </div>
              )}
              <Dato titulo="Síntomas">{t.sintomas}</Dato>
              <Dato titulo="Contexto">{t.contexto}</Dato>
              <Dato titulo="Justificación de la prioridad">{t.prioridad_justificacion}</Dato>
            </dl>
          </section>

          {t.adjuntos.length > 0 && (
            <section className="panel p-5">
              <h2 className="mb-3 font-semibold text-acero">Adjuntos</h2>
              <ul className="space-y-2">{t.adjuntos.map((a) => <Adjunto key={a.id} a={a} />)}</ul>
            </section>
          )}

          <section className="panel p-5">
            <h2 className="font-semibold text-acero">Comentarios</h2>
            <ul className="mt-3 space-y-3">
              {t.comentarios.length === 0 && <li className="text-sm text-acero-500">Todavía no hay comentarios.</li>}
              {t.comentarios.map((c, i) => (
                <li key={i} className={`rounded-md border px-3 py-2 text-sm ${c.interno ? 'border-amber-200 bg-amber-50' : 'border-niebla-200'}`}>
                  <p className="text-xs text-acero-500"><span className="font-medium text-acero">{c.autor}</span> · {c.fecha}{c.interno && ' · nota interna'}</p>
                  <p className="mt-1 whitespace-pre-wrap">{c.texto}</p>
                </li>
              ))}
            </ul>
            {!cerrado && (
              <form className="mt-4 space-y-2" onSubmit={(e) => {
                e.preventDefault()
                accion(() => api(`/tickets/${t.id}/comentarios`, { method: 'POST', body: { texto: comentario, interno } }), 'Comentario agregado.')
                  .then((ok) => ok && setComentario(''))
              }}>
                <textarea className="campo" rows={3} placeholder="Agregar información o un comentario" value={comentario} onChange={(e) => setComentario(e.target.value)} maxLength={2000} required minLength={3} />
                <div className="flex items-center justify-between">
                  {esStaff ? <label className="flex items-center gap-2 text-sm text-acero"><input type="checkbox" checked={interno} onChange={(e) => setInterno(e.target.checked)} className="accent-esmeralda" />Nota interna (solo soporte)</label> : <span />}
                  <button className="btn-primario">Agregar comentario</button>
                </div>
              </form>
            )}
          </section>
        </div>

        <div className="space-y-6">
          {!cerrado && t.transiciones_posibles.length > 0 && (
            <section className="panel p-5">
              <h2 className="font-semibold text-acero">Cambiar estado</h2>
              <p className="mt-1 text-xs text-acero-500">Solo se muestran las transiciones del flujo. El sistema valida además tu rol.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {t.transiciones_posibles.map((e) => (
                  <button key={e} onClick={() => { setDestino(e); setMotivo('') }}
                    className={`rounded-md border px-3 py-1.5 text-sm ${destino === e ? 'border-esmeralda bg-esmeralda-50 text-esmeralda-700' : 'border-niebla-300 text-acero hover:border-acero-300'}`}>
                    {e}
                  </button>
                ))}
              </div>
              {destino && (
                <form className="mt-3 space-y-2" onSubmit={(ev) => {
                  ev.preventDefault()
                  if (destino === 'Cerrado' && !window.confirm(`¿Confirmás el cierre del ticket #${t.id}? Es definitivo.`)) return
                  accion(() => api(`/tickets/${t.id}/estado`, { method: 'POST', body: { estado: destino, comentario: motivo } }), `Estado actualizado a ${destino}.`)
                    .then((ok) => ok && setDestino(''))
                }}>
                  <textarea className="campo" rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)}
                    placeholder={EXIGE_MOTIVO.includes(destino) ? 'Motivo o detalle (obligatorio)' : 'Comentario (opcional)'}
                    required={EXIGE_MOTIVO.includes(destino)} />
                  <button className="btn-esmeralda w-full">Pasar a {destino}</button>
                </form>
              )}
            </section>
          )}

          {esStaff && !cerrado && (
            <section className="panel space-y-3 p-5">
              <h2 className="font-semibold text-acero">Revisar prioridad</h2>
              <form className="space-y-2" onSubmit={(e) => {
                e.preventDefault()
                accion(() => api(`/tickets/${t.id}/prioridad`, { method: 'POST', body: { prioridad: prioridad.valor, motivo: prioridad.motivo } }), 'Prioridad actualizada.')
                  .then((ok) => ok && setPrioridad({ valor: '', motivo: '' }))
              }}>
                <select className="campo" value={prioridad.valor} onChange={(e) => setPrioridad({ ...prioridad, valor: e.target.value })} required aria-label="Nueva prioridad">
                  <option value="">Nueva prioridad…</option>
                  {['Baja', 'Media', 'Alta', 'Crítica'].filter((p) => p !== t.prioridad).map((p) => <option key={p}>{p}</option>)}
                </select>
                <input className="campo" placeholder="Motivo del cambio" value={prioridad.motivo} onChange={(e) => setPrioridad({ ...prioridad, motivo: e.target.value })} required minLength={5} />
                <button className="btn-sec w-full">Guardar prioridad</button>
              </form>
              {usuario.rol === 'supervisor' && (
                <form className="space-y-2 border-t border-niebla-200 pt-3" onSubmit={(e) => {
                  e.preventDefault()
                  accion(() => api(`/tickets/${t.id}/asignar`, { method: 'POST', body: { tecnico } }), 'Responsable actualizado.')
                }}>
                  <h3 className="text-sm font-medium text-acero">Responsable</h3>
                  <select className="campo" value={tecnico} onChange={(e) => setTecnico(e.target.value)} required aria-label="Técnico">
                    <option value="">Elegir técnico…</option>
                    {tecnicos.map((x) => <option key={x.username} value={x.username}>{x.nombre} — {x.especialidades.filter(Boolean).join(', ') || 'Supervisión'}</option>)}
                  </select>
                  <button className="btn-sec w-full">Asignar</button>
                </form>
              )}
              {usuario.rol === 'tecnico' && t.responsable === 'Sin asignar' && (
                <button className="btn-sec w-full" onClick={() => accion(() => api(`/tickets/${t.id}/asignar`, { method: 'POST', body: { tecnico: 'yo' } }), 'Tomaste el ticket.')}>Tomar este ticket</button>
              )}
            </section>
          )}

          <section className="panel p-5">
            <h2 className="font-semibold text-acero">Historial</h2>
            <p className="mt-1 text-xs text-acero-500">Cada cambio con fecha, responsable y origen</p>
            <ol className="relative mt-4 space-y-4 border-l border-niebla-300 pl-5">
              {hist.map((e, i) => (
                <li key={i} className="relative">
                  <span className={`absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full ${e.tipo === 'CAMBIO_ESTADO' ? 'bg-esmeralda' : e.tipo === 'CREACION' ? 'bg-acero' : 'bg-acero-300'}`} />
                  <p className="text-sm font-medium text-acero">
                    {EVENTOS[e.tipo] || e.tipo}
                    {e.anterior && e.nuevo ? `: ${e.anterior} → ${e.nuevo}` : e.nuevo && e.tipo !== 'COMENTARIO' ? `: ${e.nuevo}` : ''}
                  </p>
                  {e.detalle && <p className="mt-0.5 text-xs text-acero-700">{e.detalle}</p>}
                  <p className="mt-0.5 text-[11px] text-acero-300">{e.fecha} · {e.responsable_del_cambio} · vía {e.origen}</p>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </div>
  )
}
