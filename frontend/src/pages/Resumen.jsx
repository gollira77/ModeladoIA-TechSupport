import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { COLOR_ESTADO, COLOR_PRIORIDAD, Estado, NumeroTicket, Prioridad } from '../components/Insignias'

function Barras({ titulo, datos, colores }) {
  const max = Math.max(1, ...Object.values(datos))
  return (
    <section className="panel p-5">
      <h2 className="font-semibold text-acero">{titulo}</h2>
      <ul className="mt-4 space-y-2.5">
        {Object.entries(datos).map(([k, v]) => (
          <li key={k} className="grid grid-cols-[minmax(110px,170px)_1fr_2.5rem] items-center gap-3 text-sm">
            <span className="truncate text-acero-700">{k}</span>
            <span className="h-2.5 rounded-sm bg-niebla">
              <span className="block h-full rounded-sm" style={{ width: `${(v / max) * 100}%`, background: colores?.[k] || '#1E3A5F' }} />
            </span>
            <span className="text-right font-mono text-xs text-acero">{v}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Cifra({ valor, texto, destacado }) {
  if (valor === null || valor === undefined) return null
  return (
    <div className={`panel px-5 py-4 ${destacado ? 'border-esmeralda/50' : ''}`}>
      <p className={`text-3xl font-semibold ${destacado ? 'text-esmeralda-700' : 'text-acero'}`}>{valor}</p>
      <p className="mt-1 text-sm text-acero-500">{texto}</p>
    </div>
  )
}

export default function Resumen() {
  const { esStaff } = useAuth()
  const [dias, setDias] = useState(0)
  const [r, setR] = useState(null)

  useEffect(() => { api(`/resumen?periodo_dias=${dias}`).then(setR) }, [dias])
  if (!r) return <p className="p-8 text-acero-300">Cargando…</p>

  const prioridades = ['Baja', 'Media', 'Alta', 'Crítica']
  const maxCruce = Math.max(1, ...Object.values(r.categoria_x_prioridad).flatMap((x) => Object.values(x)))

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="titulo-pagina">Resumen de incidencias</h1>
          <p className="mt-1 text-sm text-acero-500">Alcance: {r.alcance}. Generado el {r.generado}.</p>
        </div>
        <select className="campo w-auto" value={dias} onChange={(e) => setDias(Number(e.target.value))} aria-label="Período">
          <option value={0}>Todo el historial</option>
          <option value={7}>Últimos 7 días</option>
          <option value={30}>Últimos 30 días</option>
        </select>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Cifra valor={r.total} texto="tickets en total" />
        <Cifra valor={r.activos} texto="activos (sin resolver)" destacado />
        <Cifra valor={r.activos_sin_asignar} texto="activos sin responsable" />
        <Cifra valor={r.prioridades_pendientes_de_revision} texto="prioridades sin revisar por soporte" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Barras titulo="Por estado" datos={r.por_estado} colores={COLOR_ESTADO} />
        <Barras titulo="Por prioridad" datos={r.por_prioridad} colores={COLOR_PRIORIDAD} />
        <Barras titulo="Por categoría" datos={r.por_categoria} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1fr]">
        <section className="panel overflow-x-auto p-5">
          <h2 className="font-semibold text-acero">Categoría por prioridad</h2>
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="text-xs text-acero-500"><th className="pb-2 text-left font-medium">Categoría</th>{prioridades.map((p) => <th key={p} className="pb-2 font-medium">{p}</th>)}</tr>
            </thead>
            <tbody>
              {Object.entries(r.categoria_x_prioridad).map(([c, fila]) => (
                <tr key={c}>
                  <td className="py-1 pr-3 text-acero-700">{c}</td>
                  {prioridades.map((p) => (
                    <td key={p} className="p-0.5">
                      <span className="block rounded py-1.5 text-center font-mono text-xs"
                        style={{ background: fila[p] ? `rgba(30,58,95,${0.12 + (fila[p] / maxCruce) * 0.75})` : '#EEF2F5', color: fila[p] / maxCruce > 0.45 ? 'white' : '#1E3A5F' }}>
                        {fila[p] || '·'}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel p-5">
          <h2 className="font-semibold text-acero">Urgentes sin resolver</h2>
          <p className="mt-1 text-xs text-acero-500">Prioridad Crítica y Alta en estados activos</p>
          <ul className="mt-3 divide-y divide-niebla-200">
            {r.urgentes_activos.length === 0 && <li className="py-6 text-center text-sm text-acero-500">No hay incidencias urgentes activas.</li>}
            {r.urgentes_activos.map((t) => (
              <li key={t.id} className="flex items-center gap-3 py-2.5 text-sm">
                <NumeroTicket id={t.id} className="text-xs" />
                <Link to={`/tickets/${t.id}`} className="min-w-0 flex-1 truncate text-acero hover:underline">{t.titulo}</Link>
                <Prioridad valor={t.prioridad} />
                <Estado valor={t.estado} />
              </li>
            ))}
          </ul>
          {!esStaff && <p className="mt-3 text-xs text-acero-300">Ves solo tus propios tickets.</p>}
        </section>
      </div>
    </div>
  )
}
