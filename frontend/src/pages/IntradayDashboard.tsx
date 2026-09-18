import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'

import { getIntradaySVIX, getMarketStatus } from '../api/svix'
import { IntradayChart } from '../components/IntradayChart'
import { METRIC_OPTIONS, type MetricKey } from '../components/VolatilityChart'
import { getCustomIndex, getCustomIndexIntraday } from '../api/customIndex'
import { CustomIndexChart } from '../components/CustomIndexChart'

const marketLabels = { PRE_MARKET: '等待开盘', OPEN: '交易中', POST_CLOSE_DELAY: '收盘延迟补全', CLOSED: '已休市' }
const etTime = (value?: string | null) => value ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(value)) : '—'

export function IntradayDashboard() {
  const market = useQuery({ queryKey: ['market-status'], queryFn: getMarketStatus, refetchInterval: 30_000 })
  const [sessionDate, setSessionDate] = useState('')
  const [followCurrentSession, setFollowCurrentSession] = useState(true)
  const [metrics, setMetrics] = useState<MetricKey[]>(['svix'])
  useEffect(() => { if (followCurrentSession && market.data?.session_date) setSessionDate(market.data.session_date) }, [followCurrentSession, market.data?.session_date])
  const intraday = useQuery({ queryKey: ['svix-intraday', sessionDate], queryFn: () => getIntradaySVIX(sessionDate), enabled: Boolean(sessionDate), refetchInterval: market.data?.is_collection_window ? 30_000 : false })
  const points = intraday.data ?? []
  const latest = points.at(-1)
  const first = points[0]
  const changes = useMemo(() => latest && first ? { svix: latest.svix - first.svix, core: latest.core - first.core, memory: latest.memory - first.memory, ai: latest.ai - first.ai } : null, [first, latest])
  const toggleMetric = (metric: MetricKey) => setMetrics((selected) => selected.includes(metric) ? (selected.length === 1 ? selected : selected.filter((item) => item !== metric)) : [...selected, metric])
  const showingCurrentSession = sessionDate === market.data?.session_date
  const customConfig = useQuery({ queryKey: ['custom-index'], queryFn: getCustomIndex })
  const customIntraday = useQuery({ queryKey: ['custom-index-intraday', customConfig.data?.version, sessionDate], queryFn: () => getCustomIndexIntraday(sessionDate), enabled: Boolean(customConfig.data?.enabled && sessionDate), refetchInterval: market.data?.is_collection_window ? 30_000 : false })
  const customLatest = customIntraday.data?.at(-1)
  const latestIsFresh = Boolean(latest && Date.now() - new Date(latest.timestamp).getTime() <= 5 * 60_000)
  const isLive = showingCurrentSession && Boolean(market.data?.is_collection_window) && latestIsFresh

  return <main>
    <header><div><p className="eyebrow">US SESSION · INTRADAY</p><h1>单日仪表盘</h1><p className="intraday-subtitle">免费 Alpaca Indicative 结果会实时更新并明确标记为估算，不等同于 OPRA BBO</p></div><span className={`market-badge ${isLive ? 'live' : ''}`}><i />{!showingCurrentSession ? '历史交易日' : isLive ? latest?.estimated ? 'INDICATIVE · LIVE' : 'LIVE' : market.data ? marketLabels[market.data.state] : '载入中'}</span></header>
    <section className="session-strip">
      <div><span>交易日</span><input type="date" value={sessionDate} max={market.data?.session_date ?? undefined} onChange={(event) => { setSessionDate(event.target.value); setFollowCurrentSession(event.target.value === market.data?.session_date) }} /></div>
      <div><span>开盘（ET）</span><strong>{showingCurrentSession ? etTime(market.data?.market_open) : '09:30:00'}</strong></div>
      <div><span>正常收盘（ET）</span><strong>{showingCurrentSession ? etTime(market.data?.market_close) : '—'}</strong></div>
      <div><span>补全截止（ET）</span><strong>{showingCurrentSession ? etTime(market.data?.collection_end) : '—'}</strong></div>
      <div><span>最近采集</span><strong>{etTime(market.data?.last_collection_at)}</strong></div>
      <div><span>数据点</span><strong>{points.length}</strong></div>
    </section>
    <div className="cards intraday-cards">{METRIC_OPTIONS.map((metric) => <section key={metric.key} className={`metric-card ${metric.key === 'svix' ? 'accent' : ''}`}><span>{metric.label}</span><strong>{latest ? latest[metric.key].toFixed(2) : '—'}</strong><small className={changes && changes[metric.key] >= 0 ? 'positive' : 'negative'}>{changes ? `${changes[metric.key] >= 0 ? '+' : ''}${changes[metric.key].toFixed(2)} 日内` : '等待更多数据'}</small></section>)}</div>
    <section className="panel intraday-panel">
      <div className="panel-title chart-title"><div><h3>SVIX 分时走势</h3><p>{isLive ? latest?.estimated ? '自动刷新中 · 当前为免费 Indicative 估算' : '自动刷新中 · 当前为正式 BBO 计算' : !showingCurrentSession ? '正在查看历史交易日' : latest && !latestIsFresh ? '最近结果已过期，等待新的合格计算' : market.data?.state === 'CLOSED' ? '市场已关闭，曲线停止生长' : '等待美股正常交易时段'}</p></div>{isLive && <span className="live-indicator"><i />{latest?.estimated ? 'INDICATIVE' : 'LIVE'}</span>}</div>
      <div className="metric-switcher intraday-switcher">{METRIC_OPTIONS.map((metric) => <button key={metric.key} type="button" aria-pressed={metrics.includes(metric.key)} className={metrics.includes(metric.key) ? 'active' : ''} style={{ '--metric-color': metric.color } as CSSProperties} onClick={() => toggleMetric(metric.key)}>{metric.label}</button>)}</div>
      <IntradayChart data={points} metrics={metrics} marketOpen={showingCurrentSession ? market.data?.market_open : undefined} collectionEnd={showingCurrentSession ? market.data?.collection_end : undefined} marketActive={showingCurrentSession && Boolean(market.data?.is_collection_window)}/>
      {intraday.isError && <p className="error">日内数据载入失败，请稍后重试。</p>}
    </section>
    {customConfig.data?.enabled && <section className="panel intraday-panel custom-intraday-panel"><div className="panel-title chart-title"><div><p className="eyebrow">CUSTOM INDEX · V{customConfig.data.version}</p><h3>{customConfig.data.name}</h3><p>{customConfig.data.components.map((item) => `${item.symbol} ${Number(item.weight_percent.toFixed(2))}%`).join(' · ')}</p></div><div className="custom-index-value"><strong>{customLatest?.value.toFixed(2) ?? '—'}</strong><small>{customIntraday.data?.length ?? 0} 个数据点{customLatest?.estimated ? ' · Indicative 估算' : ''}</small></div></div><CustomIndexChart data={customIntraday.data ?? []} name={customConfig.data.name} intraday/></section>}
  </main>
}
