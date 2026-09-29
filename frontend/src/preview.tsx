/** Local design preview only. This module is loaded only by Vite in development. */
import { QueryClient } from '@tanstack/react-query'

import { AppShell } from './components/AppShell'
import { IntradayDashboard } from './pages/IntradayDashboard'
import type { MarketStatus, ObservationPoint } from './types'

const now = new Date()
const sessionDate = now.toISOString().slice(0, 10)
// Present a plausible New York trading session regardless of local preview time.
const first = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 13, 30)
const last = first + 89 * 60_000
const iso = (value: number) => new Date(value).toISOString()

const points: ObservationPoint[] = Array.from({ length: 90 }, (_, index) => {
  const drift = index * .036
  const wave = Math.sin(index / 7) * .54 + Math.sin(index / 2.8) * .16
  const svix = 22.8 + drift + wave
  return {
    timestamp: iso(first + index * 60_000),
    svix, core: 24.9 + drift * .75 + Math.sin(index / 7.6) * .48,
    memory: 27.3 + drift * 1.25 + Math.sin(index / 6.4) * .71,
    ai: 21.7 + drift * .92 + Math.sin(index / 8.2) * .43,
    calculation_quality: .71, estimated: true, source_feed: 'alpaca:indicative',
    calculation_method: 'semivix-observe-v1', market_data_quality: 'indicative_estimate',
    status: 'FREE_ESTIMATE', coverage: .86, cached_coverage: 0,
    batch_id: `preview-${index}`, oldest_input_at: iso(first + index * 60_000 - 2 * 60_000),
    comparable_key: 'preview-stable-method',
    component_counts: { core: '1/1', memory: '1/2', ai: '3/3' }, reasons: {},
    details: { assets: Object.fromEntries(['SOXX', 'MU', 'NVDA', 'AMD', 'AVGO'].map((symbol) => [symbol, { status: 'NEW' }])) },
  }
})

const market: MarketStatus = {
  state: 'OPEN', is_collection_window: true, session_date: sessionDate,
  market_open: iso(first), market_close: iso(first + 6.5 * 60 * 60_000),
  collection_end: iso(first + 6.75 * 60 * 60_000),
  next_open: null, last_collection_at: points.at(-1)?.timestamp ?? null,
  last_collection_status: 'COMPLETED', last_calculation_status: 'COMPLETED',
  next_collection_at: iso(last + 60_000),
}

export const previewClient = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, refetchOnWindowFocus: false, retry: false } } })
previewClient.setQueryData(['market-status'], market)
previewClient.setQueryData(['svix-intraday', sessionDate], points)
previewClient.setQueryData(['custom-index'], { enabled: false })

export function PreviewApp() {
  return <AppShell preview><div className="preview-content"><div className="preview-banner">本地设计预览 · 页面数值为演示数据，不代表实时行情</div><IntradayDashboard previewMode/></div></AppShell>
}
