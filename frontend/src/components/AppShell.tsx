import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useTheme } from '../theme'

export function AppShell({ children, onLogout, preview = false }: { children: ReactNode; onLogout?: () => void; preview?: boolean }) {
  const { theme, toggleTheme } = useTheme()
  return <div className="shell">
    <aside className="app-sidebar">
      <div className="brand"><span className="brand-mark" aria-hidden="true"><i/><i/><i/></span><span>Semi‑VIX<small>波动率观察</small></span></div>
      <p className="nav-caption">工作空间</p>
      <nav aria-label="主导航">
        <NavLink to={preview ? '/preview' : '/'} end>日内趋势</NavLink>
        {!preview && <><NavLink to="/overview">历史概览</NavLink><NavLink to="/history">历史计算</NavLink><NavLink to="/settings">设置与系统</NavLink></>}
      </nav>
      <div className="sidebar-footer">
        <button type="button" className="theme-toggle" onClick={toggleTheme} aria-label={theme === 'dark' ? '切换浅色模式' : '切换深色模式'} aria-pressed={theme === 'dark'}>
          <span className="theme-glyphs" aria-hidden="true">
            <svg className="theme-sun" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
            <svg className="theme-moon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5 8.5 8.5 0 1 0 20.5 14.5Z"/></svg>
          </span>
          <span>{theme === 'dark' ? '深色模式' : '浅色模式'}</span><i className="theme-switch" aria-hidden="true"/>
        </button>
        <span className="sidebar-readonly"><i/>只读观察</span>{preview ? <span className="sidebar-preview">本地设计预览</span> : <button className="logout" onClick={onLogout}>退出登录</button>}
      </div>
    </aside>
    {children}
  </div>
}
