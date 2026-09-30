import { lazy, Suspense, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { logoutSession, refreshSession } from './api/auth'
import { setAccessToken, setRefreshHandler, setUnauthorizedHandler } from './api/client'
import { Login } from './pages/Login'
import { AppShell } from './components/AppShell'

const Dashboard = lazy(() => import('./pages/Dashboard').then((m) => ({ default: m.Dashboard })))
const History = lazy(() => import('./pages/History').then((m) => ({ default: m.History })))
const Settings = lazy(() => import('./pages/Settings').then((m) => ({ default: m.Settings })))
const IntradayDashboard = lazy(() => import('./pages/IntradayDashboard').then((m) => ({ default: m.IntradayDashboard })))

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
  return <AppShell onLogout={logout}><Suspense fallback={<div className="session-loading"><span>正在加载页面…</span></div>}><Routes><Route path="/" element={<IntradayDashboard/>}/><Route path="/intraday" element={<Navigate to="/" replace/>}/><Route path="/overview" element={<Dashboard/>}/><Route path="/history" element={<History/>}/><Route path="/settings" element={<Settings/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></Suspense></AppShell>
}
