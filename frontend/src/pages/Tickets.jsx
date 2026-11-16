import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Estado, NumeroTicket, Prioridad } from '../components/Insignias'

export default function Tickets() {
  const { usuario, esStaff } = useAuth()
  const navigate = useNavigate()
  const [cat, setCat] = useState(null)
  const [f, setF] = useState({ estado: '', categoria: '', prioridad: '', texto: '', solo_activos: false, solo_mios: false })
  const [res, setRes] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => { api('/catalogos').then(setCat) }, [])
  useEffect(() => {
    const t = setTimeout(() => {
      const q = new URLSearchParams(Object.entries(f).filter(([, v]) => v).map(([k, v]) => [k, String(v)]))
      api(`/tickets?${q}`).then(setRes).catch((e) => setError(e.message))
    }, 250)
    return () => clearTimeout(t)
  }, [f])

  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="titulo-pagina">{esStaff ? 'Tickets' : 'Mis tickets'}</h1>
          <p className="mt-1 text-sm text-acero-500">
            {esStaff ? 'Todas las incidencias registradas, ordenadas por prioridad.' : `Incidencias registradas por ${usuario.nombre}.`}
          </p>
        </div>
        <Link to="/" className="btn-esmeralda">Reportar un problema</Link>
      </div>

      <div className="panel mt-6 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_auto]">
        <input className="campo" placeholder="Buscar por título, sistema o error" value={f.texto} onChange={set('texto')} aria-label="Buscar" />
        <select className="campo" value={f.estado} onChange={set('estado')} aria-label="Estado">
          <option value="">Todos los estados</option>
          {cat?.estados.map((e) => <option key={e}>{e}</option>)}
        </select>
        <select className="campo" value={f.categoria} onChange={set('categoria')} aria-label="Categoría">
          <option value="">Todas las categorías</option>
          {cat?.categorias.map((e) => <option key={e}>{e}</option>)}
        </select>
        <select className="campo" value={f.prioridad} onChange={set('prioridad')} aria-label="Prioridad">
          <option value="">Todas las prioridades</option>
          {cat?.prioridades.map((e) => <option key={e}>{e}</option>)}
        </select>
        <div className="flex flex-col justify-center gap-1 text-sm text-acero">
          <label className="flex items-center gap-2"><input type="checkbox" checked={f.solo_activos} onChange={set('solo_activos')} className="accent-esmeralda" />Solo activos</label>
          {usuario.rol === 'tecnico' && <label className="flex items-center gap-2"><input type="checkbox" checked={f.solo_mios} onChange={set('solo_mios')} className="accent-esmeralda" />Asignados a mí</label>}
        </div>
      </div>

      {error && <p className="mt-4 text-sm text-red-700">{error}</p>}

      <div className="panel mt-4 overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-niebla-300 text-left text-xs text-acero-500">
              <th className="px-4 py-3 font-medium">Ticket</th>
              <th className="px-4 py-3 font-medium">Título</th>
              <th className="px-4 py-3 font-medium">Categoría</th>
              <th className="px-4 py-3 font-medium">Prioridad</th>
              <th className="px-4 py-3 font-medium">Estado</th>
              {esStaff && <th className="px-4 py-3 font-medium">Solicitante</th>}
              <th className="px-4 py-3 font-medium">Responsable</th>
              <th className="px-4 py-3 font-medium">Creado</th>
            </tr>
          </thead>
          <tbody>
            {res?.tickets.map((t) => (
              <tr key={t.id} onClick={() => navigate(`/tickets/${t.id}`)} className="cursor-pointer border-b border-niebla-200 last:border-0 hover:bg-niebla/60">
                <td className="px-4 py-3"><NumeroTicket id={t.id} /></td>
                <td className="max-w-xs px-4 py-3"><Link to={`/tickets/${t.id}`} className="font-medium text-acero hover:underline" onClick={(e) => e.stopPropagation()}>{t.titulo}</Link></td>
                <td className="px-4 py-3 text-acero-500">{t.categoria}</td>
                <td className="px-4 py-3"><Prioridad valor={t.prioridad} /></td>
                <td className="px-4 py-3"><Estado valor={t.estado} /></td>
                {esStaff && <td className="px-4 py-3 text-acero-500">{t.solicitante}</td>}
                <td className="px-4 py-3 text-acero-500">{t.responsable}</td>
                <td className="whitespace-nowrap px-4 py-3 text-acero-500">{t.creado}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {res && res.tickets.length === 0 && (
          <div className="px-4 py-12 text-center">
            <p className="font-medium text-acero">No hay tickets con estos filtros.</p>
            <p className="mt-1 text-sm text-acero-500">Probá quitar algún filtro o reportá un problema nuevo desde el asistente.</p>
          </div>
        )}
      </div>
      {res && <p className="mt-2 text-xs text-acero-300">{res.total} ticket(s)</p>}
    </div>
  )
}
