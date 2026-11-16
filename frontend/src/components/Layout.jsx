import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { api } from '../lib/api'

const ROLES = { solicitante: 'Solicitante', tecnico: 'Técnico de soporte', supervisor: 'Supervisor' }

function Enlace({ to, children }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
          isActive ? 'bg-acero-700 text-white shadow-[inset_3px_0_0_#10B981]' : 'text-acero-100 hover:bg-acero-700/60 hover:text-white'
        }`}
    >
      {children}
    </NavLink>
  )
}

function EstadoModelo() {
  const [s, setS] = useState(null)
  useEffect(() => { api('/salud').then(setS).catch(() => setS(null)) }, [])
  if (!s) return null
  const items = [
    ['Agente', s.modelo_agente.disponible],
    ['Visión', s.modelo_vision.disponible],
    ['RAG', s.modelo_embeddings.disponible],
  ]
  return (
    <div className="rounded-md bg-acero-800 p-3 text-xs text-acero-100" title={`Agente: ${s.modelo_agente.nombre}\nVisión: ${s.modelo_vision.nombre}\nEmbeddings: ${s.modelo_embeddings.nombre}`}>
      <p className="mb-2 font-medium text-white">Ollama {s.ollama ? 'conectado' : 'sin conexión'}</p>
      <ul className="space-y-1">
        {items.map(([n, ok]) => (
          <li key={n} className="flex items-center gap-2">
            <span className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-esmeralda' : 'bg-amber-400'}`} />
            {n}<span className="ml-auto text-acero-300">{ok ? 'listo' : 'no disponible'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Layout({ children }) {
  const { usuario, logout } = useAuth()
  const [abierto, setAbierto] = useState(false)
  return (
    <div className="flex min-h-screen">
      <aside className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col bg-acero px-4 py-5 transition-transform md:static md:translate-x-0 ${abierto ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="mb-8 flex items-center gap-3 px-2">
          <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7" fill="#132740" /><path d="M9 16h14M16 9v14" stroke="#10B981" strokeWidth="4" strokeLinecap="round" /></svg>
          <div>
            <p className="font-semibold leading-tight text-white">TechSupport S.A.</p>
            <p className="text-xs text-acero-300">Mesa de Ayuda</p>
          </div>
        </div>
        <nav className="space-y-1" onClick={() => setAbierto(false)}>
          <Enlace to="/">Asistente TechBot</Enlace>
          <Enlace to="/tickets">{usuario.rol === 'solicitante' ? 'Mis tickets' : 'Tickets'}</Enlace>
          <Enlace to="/resumen">Resumen</Enlace>
          {usuario.rol === 'supervisor' && <Enlace to="/seguridad">Seguridad y derivaciones</Enlace>}
        </nav>
        <div className="mt-auto space-y-3">
          <EstadoModelo />
          <div className="rounded-md border border-acero-500 p-3">
            <p className="text-sm font-medium text-white">{usuario.nombre}</p>
            <p className="text-xs text-acero-300">{ROLES[usuario.rol]} · {usuario.area}</p>
            <button onClick={logout} className="mt-2 text-xs text-esmeralda hover:underline">Cerrar sesión</button>
          </div>
        </div>
      </aside>
      {abierto && <div className="fixed inset-0 z-20 bg-acero-900/40 md:hidden" onClick={() => setAbierto(false)} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-niebla-300 bg-white px-4 py-3 md:hidden">
          <button className="btn-sec px-3 py-1.5" onClick={() => setAbierto(true)} aria-label="Abrir menú">Menú</button>
          <span className="font-semibold text-acero">TechSupport S.A.</span>
        </header>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  )
}
