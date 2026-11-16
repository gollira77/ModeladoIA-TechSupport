import { createContext, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null)
  const [cargando, setCargando] = useState(Boolean(getToken()))

  useEffect(() => {
    if (getToken()) {
      api('/auth/me').then(setUsuario).catch(() => setToken(null)).finally(() => setCargando(false))
    }
    const vencida = () => setUsuario(null)
    window.addEventListener('sesion-vencida', vencida)
    return () => window.removeEventListener('sesion-vencida', vencida)
  }, [])

  async function login(username, password) {
    const r = await api('/auth/login', { method: 'POST', body: { username, password } })
    setToken(r.token)
    setUsuario(await api('/auth/me'))
  }
  function logout() {
    setToken(null)
    try { sessionStorage.removeItem('ts_chat') } catch { /* */ }
    setUsuario(null)
  }
  const esStaff = usuario && usuario.rol !== 'solicitante'
  return <AuthCtx.Provider value={{ usuario, cargando, login, logout, esStaff }}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
