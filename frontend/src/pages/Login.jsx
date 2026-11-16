import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { api } from '../lib/api'

const ROLES = { solicitante: 'Solicitantes', tecnico: 'Técnicos de soporte', supervisor: 'Supervisión' }

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [demo, setDemo] = useState([])

  useEffect(() => { api('/usuarios/demo').then(setDemo).catch(() => {}) }, [])

  async function enviar(e) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try { await login(username, password) } catch (err) { setError(err.message) } finally { setEnviando(false) }
  }

  return (
    <div className="grid min-h-screen md:grid-cols-[1fr_minmax(420px,520px)]">
      <section className="relative hidden overflow-hidden bg-acero p-12 text-white md:flex md:flex-col">
        <div className="flex items-center gap-3">
          <svg width="40" height="40" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7" fill="#132740" /><path d="M9 16h14M16 9v14" stroke="#10B981" strokeWidth="4" strokeLinecap="round" /></svg>
          <span className="text-lg font-semibold">TechSupport S.A.</span>
        </div>
        <div className="my-auto max-w-lg">
          <h1 className="text-4xl font-semibold leading-tight">Contale el problema a TechBot y queda registrado.</h1>
          <p className="mt-5 text-lg text-acero-100">
            Escribí con tus palabras, adjuntá una captura, una foto del equipo o el log del error. El asistente
            entiende la incidencia, la clasifica, propone la prioridad y genera el ticket.
          </p>
          <div className="mt-10 rounded-lg border border-acero-500 bg-acero-800/70 p-5 font-mono text-sm leading-relaxed text-acero-100">
            <p><span className="text-esmeralda">usuario ›</span> no me anda la vpn, adjunto el log</p>
            <p className="mt-2"><span className="text-acero-300">TechBot ›</span> analizar_adjunto · vpn_forticlient.log</p>
            <p><span className="text-acero-300">TechBot ›</span> crear_ticket · Redes y conectividad · Alta</p>
            <p className="mt-2 text-white">Ticket #1054 creado y asignado a Paula Ibarra.</p>
          </div>
        </div>
        <p className="text-xs text-acero-300">Entorno de demostración. Todos los datos son ficticios.</p>
      </section>

      <section className="flex flex-col justify-center bg-white px-6 py-10 sm:px-12">
        <h2 className="text-2xl font-semibold text-acero">Iniciar sesión</h2>
        <p className="mt-1 text-sm text-acero-500">Mesa de Ayuda · acceso para empleados</p>
        <form onSubmit={enviar} className="mt-8 space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-acero">Usuario</span>
            <input className="campo" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-acero">Contraseña</span>
            <input className="campo" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </label>
          {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</p>}
          <button className="btn-primario w-full py-2.5" disabled={enviando}>{enviando ? 'Ingresando…' : 'Ingresar'}</button>
        </form>

        {demo.length > 0 && (
          <div className="mt-10">
            <p className="text-sm font-medium text-acero">Usuarios de demostración</p>
            <p className="mb-3 text-xs text-acero-500">Contraseña de todos: <span className="font-mono">demo123</span>. Elegí uno para completar el formulario.</p>
            <div className="space-y-3">
              {Object.entries(ROLES).map(([rol, titulo]) => (
                <div key={rol}>
                  <p className="mb-1 text-xs text-acero-300">{titulo}</p>
                  <div className="flex flex-wrap gap-2">
                    {demo.filter((u) => u.rol === rol).map((u) => (
                      <button key={u.username} type="button"
                        onClick={() => { setUsername(u.username); setPassword('demo123') }}
                        className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${username === u.username ? 'border-esmeralda bg-esmeralda-50 text-esmeralda-700' : 'border-niebla-300 text-acero hover:border-acero-300'}`}>
                        {u.nombre}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
