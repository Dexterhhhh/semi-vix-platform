import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { flushSync } from 'react-dom'

export type Theme = 'light' | 'dark'
const storageKey = 'semi-vix-theme'
const systemTheme = (): Theme => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
const savedTheme = (): Theme | null => {
  try {
    const saved = window.localStorage.getItem(storageKey)
    return saved === 'light' || saved === 'dark' ? saved : null
  } catch {
    return null
  }
}
const initialTheme = savedTheme() ?? systemTheme()
document.documentElement.dataset.theme = initialTheme
document.documentElement.style.colorScheme = initialTheme

const ThemeContext = createContext<{ theme: Theme; toggleTheme: () => void } | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
  }, [theme])

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const followSystem = () => { if (!savedTheme()) setTheme(systemTheme()) }
    media.addEventListener('change', followSystem)
    return () => media.removeEventListener('change', followSystem)
  }, [])

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    try { window.localStorage.setItem(storageKey, next) } catch { /* Theme still changes for this session. */ }
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!reduceMotion) document.documentElement.classList.add('theme-motion')
    if (document.startViewTransition && !reduceMotion) {
      document.startViewTransition(() => {
        flushSync(() => setTheme(next))
        document.documentElement.dataset.theme = next
        document.documentElement.style.colorScheme = next
      })
    } else {
      setTheme(next)
    }
  }

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('ThemeProvider is missing')
  return context
}

export const chartPalette = {
  light: { surface: '#ffffff', text: '#1c1c1e', muted: '#6e6e73', grid: '#e5e5ea', border: '#d1d1d6', slider: '#f2f2f7', dotBorder: '#ffffff', accent: '#007aff' },
  dark: { surface: '#2c2c2e', text: '#f5f5f7', muted: '#aeaeb2', grid: '#38383a', border: '#545458', slider: '#1c1c1e', dotBorder: '#1c1c1e', accent: '#0a84ff' },
} as const
