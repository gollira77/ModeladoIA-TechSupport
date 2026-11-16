// Colores semánticos de estados y prioridades (consistentes en toda la app)
const ESTADOS = {
  'Abierto': 'bg-acero-100 text-acero',
  'En revisión': 'bg-sky-100 text-sky-800',
  'En progreso': 'bg-indigo-100 text-indigo-800',
  'Pendiente': 'bg-amber-100 text-amber-800',
  'Resuelto': 'bg-esmeralda-100 text-esmeralda-700',
  'Cerrado': 'bg-niebla-300 text-acero-500',
}
const PRIORIDADES = {
  'Baja': { punto: 'bg-acero-300', texto: 'text-acero-500' },
  'Media': { punto: 'bg-sky-500', texto: 'text-sky-800' },
  'Alta': { punto: 'bg-amber-500', texto: 'text-amber-800' },
  'Crítica': { punto: 'bg-red-600', texto: 'text-red-700 font-semibold' },
}

export function Estado({ valor }) {
  return <span className={`inline-flex whitespace-nowrap rounded px-2 py-0.5 text-xs font-medium ${ESTADOS[valor] || 'bg-niebla'}`}>{valor}</span>
}

export function Prioridad({ valor }) {
  const p = PRIORIDADES[valor] || PRIORIDADES.Baja
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap text-xs ${p.texto}`}>
      <span className={`h-2 w-2 rounded-full ${p.punto}`} />{valor}
    </span>
  )
}

export function NumeroTicket({ id, className = '' }) {
  return <span className={`font-mono text-acero-500 ${className}`}>#{id}</span>
}

export const COLOR_PRIORIDAD = { 'Baja': '#6F8BAE', 'Media': '#0EA5E9', 'Alta': '#F59E0B', 'Crítica': '#DC2626' }
export const COLOR_ESTADO = { 'Abierto': '#1E3A5F', 'En revisión': '#0284C7', 'En progreso': '#4F46E5', 'Pendiente': '#D97706', 'Resuelto': '#10B981', 'Cerrado': '#94A3B8' }
