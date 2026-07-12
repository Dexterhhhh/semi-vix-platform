import { useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { setAccessToken, setUnauthorizedHandler } from './api/client'
import { Dashboard } from './pages/Dashboard'
import { History } from './pages/History'
import { Settings } from './pages/Settings'
import { Login } from './pages/Login'

export default function App() {
  const [token, setToken] = useState<string | null>(null)
  useEffect(() => { setAccessToken(token); setUnauthorizedHandler(() => setToken(null)) }, [token])
  if (!token) return <Login onAuthenticated={setToken}/>
  return <div className="shell"><aside><div className="brand">SEMI‑VIX</div><NavLink to="/">仪表盘</NavLink><NavLink to="/history">历史计算</NavLink><NavLink to="/settings">设置与系统</NavLink><button className="logout" onClick={() => setToken(null)}>退出登录</button></aside><Routes><Route path="/" element={<Dashboard/>}/><Route path="/history" element={<History/>}/><Route path="/settings" element={<Settings/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></div>
}
