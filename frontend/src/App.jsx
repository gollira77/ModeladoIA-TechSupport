import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './lib/auth'
import Layout from './components/Layout'
import Login from './pages/Login'
import Chat from './pages/Chat'
import Tickets from './pages/Tickets'
import TicketDetalle from './pages/TicketDetalle'
import Resumen from './pages/Resumen'
import Seguridad from './pages/Seguridad'

export default function App() {
  const { usuario, cargando } = useAuth()
  if (cargando) return <div className="grid h-screen place-items-center text-acero-300">Cargando…</div>
  if (!usuario) return <Login />
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Chat />} />
        <Route path="/tickets" element={<Tickets />} />
        <Route path="/tickets/:id" element={<TicketDetalle />} />
        <Route path="/resumen" element={<Resumen />} />
        {usuario.rol === 'supervisor' && <Route path="/seguridad" element={<Seguridad />} />}
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  )
}
