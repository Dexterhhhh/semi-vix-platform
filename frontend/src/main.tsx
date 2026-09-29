import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { ThemeProvider } from './theme'
import './styles.css'
import './modern.css'

const root = ReactDOM.createRoot(document.getElementById('root')!)
const render = (app: React.ReactNode, client: QueryClient) => root.render(<React.StrictMode><ThemeProvider><QueryClientProvider client={client}><BrowserRouter>{app}</BrowserRouter></QueryClientProvider></ThemeProvider></React.StrictMode>)

if (import.meta.env.DEV && window.location.pathname === '/preview') {
  import('./preview').then(({ PreviewApp, previewClient }) => render(<PreviewApp/>, previewClient))
} else {
  render(<App/>, new QueryClient())
}
