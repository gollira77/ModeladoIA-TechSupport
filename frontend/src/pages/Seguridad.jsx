import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const TIPOS = {
  PROMPT_INJECTION: 'Intento de manipular al asistente',
  DATO_SENSIBLE: 'Pedido de información sensible',
  FUERA_DE_TEMA: 'Consulta fuera de tema',
  PERMISO_DENEGADO: 'Operación sin permiso',
  ADJUNTO_SOSPECHOSO: 'Archivo con instrucciones ocultas',
  COMANDO_REMOTO: 'Pedido de ejecutar comandos',
  SALIDA_FILTRADA: 'Respuesta filtrada',
  LIMITE_TASA: 'Exceso de mensajes',
  LOGIN_FALLIDO: 'Inicio de sesión fallido',
  MENSAJE_EXCESIVO: 'Mensaje demasiado largo',
}
const SEV = { alta: 'bg-red-100 text-red-700', media: 'bg-amber-100 text-amber-800', baja: 'bg-niebla-200 text-acero-500' }

export default function Seguridad() {
  const [eventos, setEventos] = useState([])
  const [derivaciones, setDerivaciones] = useState([])
  const [pestana, setPestana] = useState('eventos')

  useEffect(() => {
    api('/seguridad/eventos').then(setEventos)
    api('/derivaciones').then(setDerivaciones)
  }, [])

  const altas = eventos.filter((e) => e.severidad === 'alta').length

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-8 2xl:max-w-[100rem] 2xl:px-12">
      <h1 className="titulo-pagina">Seguridad y derivaciones</h1>
      <p className="mt-1 max-w-2xl text-sm text-acero-500">
        Registro de lo que las barreras de seguridad detectaron y de las consultas que el asistente derivó a una
        persona. Tres intentos graves en 15 minutos bloquean temporalmente al usuario.
      </p>

      <div className="mt-6 flex gap-1 border-b border-niebla-300" role="tablist">
        {[['eventos', `Eventos de seguridad (${eventos.length})`], ['derivaciones', `Derivaciones a personas (${derivaciones.length})`]].map(([k, t]) => (
          <button key={k} role="tab" aria-selected={pestana === k} onClick={() => setPestana(k)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm ${pestana === k ? 'border-esmeralda font-medium text-acero' : 'border-transparent text-acero-500 hover:text-acero'}`}>
            {t}
          </button>
        ))}
      </div>

      {pestana === 'eventos' ? (
        <>
          {altas > 0 && <p className="mt-4 text-sm text-red-700">{altas} evento(s) de severidad alta.</p>}
          <div className="panel mt-4 overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-niebla-300 text-left text-xs text-acero-500">
                  <th className="px-4 py-3 font-medium">Fecha</th><th className="px-4 py-3 font-medium">Usuario</th>
                  <th className="px-4 py-3 font-medium">Evento</th><th className="px-4 py-3 font-medium">Severidad</th>
                  <th className="px-4 py-3 font-medium">Detalle</th>
                </tr>
              </thead>
              <tbody>
                {eventos.map((e) => (
                  <tr key={e.id} className="border-b border-niebla-200 align-top last:border-0">
                    <td className="whitespace-nowrap px-4 py-3 text-acero-500">{e.fecha}</td>
                    <td className="px-4 py-3">{e.usuario}</td>
                    <td className="px-4 py-3 font-medium text-acero">{TIPOS[e.tipo] || e.tipo}</td>
                    <td className="px-4 py-3"><span className={`rounded px-2 py-0.5 text-xs ${SEV[e.severidad]}`}>{e.severidad}</span></td>
                    <td className="max-w-md px-4 py-3 text-acero-700">
                      {e.detalle}
                      {e.extracto && <span className="mt-1 block truncate font-mono text-xs text-acero-300" title={e.extracto}>“{e.extracto}”</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {eventos.length === 0 && <p className="px-4 py-12 text-center text-sm text-acero-500">Sin eventos registrados. Probá los escenarios de seguridad desde el asistente.</p>}
          </div>
        </>
      ) : (
        <div className="panel mt-4 divide-y divide-niebla-200">
          {derivaciones.length === 0 && <p className="px-4 py-12 text-center text-sm text-acero-500">No hay consultas derivadas.</p>}
          {derivaciones.map((d) => (
            <div key={d.id} className="flex flex-wrap items-start gap-4 px-5 py-4 text-sm">
              <span className="font-mono text-xs text-acero-500">{d.id}</span>
              <div className="min-w-0 flex-1">
                <p className="text-tinta">{d.motivo}</p>
                <p className="mt-1 text-xs text-acero-500">{d.usuario} · {d.fecha}{d.ticket_id ? ` · ticket #${d.ticket_id}` : ''}</p>
              </div>
              <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">{d.estado}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
