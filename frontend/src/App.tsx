import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { logoutSession, refreshSession } from './api/auth'
import { setAccessToken, setRefreshHandler, setUnauthorizedHandler } from './api/client'
import { Dashboard } from './pages/Dashboard'
import { History } from './pages/History'
import { Settings } from './pages/Settings'
import { Login } from './pages/Login'
import { IntradayDashboard } from './pages/IntradayDashboard'
import { AppShell } from './components/AppShell'

export default function App() {
  const [token, setToken] = useState<string | null>(null)
  const [restoring, setRestoring] = useState(true)

  useEffect(() => {
    const restore = async () => {
      try {
        const result = await refreshSession()
        setAccessToken(result.access_token)
        setToken(result.access_token)
        return result.access_token
      } catch {
        setAccessToken(null)
        setToken(null)
        return null
      }
    }
    setRefreshHandler(restore)
    setUnauthorizedHandler(() => { setAccessToken(null); setToken(null) })
    restore().finally(() => setRestoring(false))
  }, [])

  useEffect(() => { setAccessToken(token) }, [token])

  const logout = async () => {
    try { await logoutSession() } finally { setAccessToken(null); setToken(null) }
  }

  if (restoring) return <div className="session-loading"><span>正在恢复安全会话…</span></div>
  if (!token) return <Login onAuthenticated={setToken}/>
  return <AppShell onLogout={logout}><Routes><Route path="/" element={<IntradayDashboard/>}/><Route path="/intraday" element={<Navigate to="/" replace/>}/><Route path="/overview" element={<Dashboard/>}/><Route path="/history" element={<History/>}/><Route path="/settings" element={<Settings/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></AppShell>
}
