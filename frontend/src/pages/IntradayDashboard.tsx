import { useEffect, useState, type CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'

import { getIntradaySVIX, getMarketStatus } from '../api/svix'
import { IntradayChart } from '../components/IntradayChart'
import { IntradayCandlestickChart } from '../components/IntradayCandlestickChart'
import { METRIC_OPTIONS, metricColor, type MetricKey } from '../components/VolatilityChart'
import { useTheme } from '../theme'
import { getCustomIndex, getCustomIndexIntraday } from '../api/customIndex'
import { CustomIndexChart } from '../components/CustomIndexChart'
import type { ObservationPoint } from '../types'

const marketLabels = { PRE_MARKET: '等待开盘', OPEN: '交易中', POST_CLOSE_DELAY: '收盘延迟补全', CLOSED: '已休市' }
const etTime = (value?: string | null) => value ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(value)) : '—'
const labels: Record<string, string> = { FREE_ESTIMATE: '免费估算', ESTIMATE: '观察估算', OLD_QUOTES: '部分报价较旧', CACHED: '含缓存成分', PARTIAL_COVERAGE: '部分覆盖', NO_VALID_DATA: '暂无数据', LEGACY: '旧版历史结果' }
const calculationLabels: Record<string, string> = { PENDING: '等待计算', COMPLETED: '已完成', PARTIAL: '部分完成', FAILED: '计算失败', NO_NEW_DATA: '没有新市场报价', NO_VALID_DATA: '无有效数据' }
const reasonLabels: Record<string, string> = { NO_ASSETS: '没有可用成分', SOXX_UNAVAILABLE: 'SOXX 暂不可用', INSUFFICIENT_COVERAGE: '覆盖率不足 70%', INSUFFICIENT_DAILY_HISTORY: '股票日线历史不足', CORRELATION_TOO_OLD: '相关矩阵已过期', INVALID_CORRELATION_HISTORY: '相关历史无效', INVALID_PORTFOLIO_COVARIANCE: '组合方差无效' }

function changeFor(points: ObservationPoint[], metric: MetricKey): number | null {
  let lastIndex = points.length - 1
  while (lastIndex >= 0 && points[lastIndex][metric] === null) lastIndex--
  if (lastIndex < 0) return null
  const last = points[lastIndex]
  let first = last
  for (let index = lastIndex - 1; index >= 0; index--) {
    const point = points[index]
    const next = points[index + 1]
    if (point.comparable_key !== last.comparable_key || new Date(next.timestamp).getTime() - new Date(point.timestamp).getTime() > 10 * 60_000) break
    if (point[metric] !== null) first = point
  }
  return first === last ? null : (last[metric] as number) - (first[metric] as number)
}

export function IntradayDashboard({ previewMode = false }: { previewMode?: boolean }) {
  const { theme } = useTheme()
  const market = useQuery({ queryKey: ['market-status'], queryFn: getMarketStatus, refetchInterval: previewMode ? false : 30_000 })
  const [sessionDate, setSessionDate] = useState('')
  const [followCurrentSession, setFollowCurrentSession] = useState(true)
  const [metrics, setMetrics] = useState<MetricKey[]>(['svix'])
  const [chartMode, setChartMode] = useState<'line' | 'candle'>('line')
  const [candleMetric, setCandleMetric] = useState<MetricKey>('svix')
  const [candleInterval, setCandleInterval] = useState(5)
  useEffect(() => { if (followCurrentSession && market.data?.session_date) setSessionDate(market.data.session_date) }, [followCurrentSession, market.data?.session_date])
  const intraday = useQuery({ queryKey: ['svix-intraday', sessionDate], queryFn: () => getIntradaySVIX(sessionDate), enabled: Boolean(sessionDate), refetchInterval: !previewMode && market.data?.is_collection_window ? 30_000 : false })
  const points = intraday.data ?? []
  const latest = points.at(-1)
  const toggleMetric = (metric: MetricKey) => {
    if (chartMode === 'candle') setCandleMetric(metric)
    else setMetrics((selected) => selected.includes(metric) ? (selected.length === 1 ? selected : selected.filter((item) => item !== metric)) : [...selected, metric])
  }
  const showingCurrentSession = sessionDate === market.data?.session_date
  const customConfig = useQuery({ queryKey: ['custom-index'], queryFn: getCustomIndex })
  const customIntraday = useQuery({ queryKey: ['custom-index-intraday', customConfig.data?.version, sessionDate], queryFn: () => getCustomIndexIntraday(sessionDate), enabled: Boolean(customConfig.data?.enabled && sessionDate), refetchInterval: !previewMode && market.data?.is_collection_window ? 30_000 : false })
  const customLatest = customIntraday.data?.at(-1)
  const latestIsFresh = Boolean(latest && (previewMode || (latest.oldest_input_at ? Date.now() - new Date(latest.oldest_input_at).getTime() <= 15 * 60_000 : latest.status === 'LEGACY' && Date.now() - new Date(latest.timestamp).getTime() <= 5 * 60_000)))
  const isLive = showingCurrentSession && Boolean(market.data?.is_collection_window) && latestIsFresh
  const lastSvix = [...points].reverse().find((point) => point.svix !== null)
  const svixChange = changeFor(points, 'svix')
  const statusLabel = !showingCurrentSession ? '历史交易日' : previewMode ? '演示数据' : isLive ? '数据更新中' : latest && !latestIsFresh ? '报价已过期' : market.data ? marketLabels[market.data.state] : '载入中'

  return <main className="trend-page">
    <header className="trend-page-header"><div><p className="eyebrow">MARKET OBSERVATION</p><h1>波动率趋势</h1><p className="intraday-subtitle">观察半导体板块的日内变化</p></div><span className={`market-badge ${isLive ? 'live' : ''}`}><i />{statusLabel}</span></header>
    <section className="panel trend-hero">
      <div className="trend-toolbar"><label className="trend-date">交易日<input aria-label="选择交易日" type="date" value={sessionDate} max={market.data?.session_date ?? undefined} onChange={(event) => { setSessionDate(event.target.value); setFollowCurrentSession(event.target.value === market.data?.session_date) }} /></label><span className="trend-timezone">NYSE · 美东时间</span></div>
      <div className="trend-headline"><div><span className="hero-overline">Semi‑VIX · 30 日预期波动率</span><div className="hero-number">{lastSvix?.svix?.toFixed(2) ?? '—'}<span>{lastSvix?.svix !== null && lastSvix ? '%' : ''}</span></div><p className="hero-change">{svixChange === null ? '等待更多可比观察点' : <><span className={svixChange >= 0 ? 'positive' : 'negative'}>{svixChange >= 0 ? '+' : ''}{svixChange.toFixed(2)} 点</span> · 本日可比变化</>}</p></div><div className="trend-headline-aside"><span>{latest?.status === 'LEGACY' ? '旧版历史结果' : latest?.estimated ? '免费报价估算' : '观察结果'}</span><strong>{lastSvix ? etTime(lastSvix.timestamp) : '—'} ET</strong><small>{latest?.svix === null ? '当前综合值暂缺，显示上次有效结果' : latest && !latestIsFresh && showingCurrentSession ? '最近结果已过期' : '最近一次有效计算'}</small></div></div>
      <div className="trend-chart-heading"><div><h2>日内走势</h2><p>{chartMode === 'candle' ? `每根蜡烛汇总 ${candleInterval} 分钟内的波动率观察值，并非股票价格` : '将鼠标移到曲线上查看具体时点'}</p></div><div className="trend-chart-controls"><div className="chart-mode-switch" aria-label="图表方式"><button type="button" aria-pressed={chartMode === 'line'} className={chartMode === 'line' ? 'active' : ''} onClick={() => setChartMode('line')}>折线</button><button type="button" aria-pressed={chartMode === 'candle'} className={chartMode === 'candle' ? 'active' : ''} onClick={() => setChartMode('candle')}>蜡烛</button></div>{chartMode === 'candle' && <label className="candle-interval">周期 <select aria-label="蜡烛周期" value={candleInterval} onChange={(event) => setCandleInterval(Number(event.target.value))}><option value={5}>5 分钟</option><option value={15}>15 分钟</option><option value={30}>30 分钟</option></select></label>}</div></div>
      <div className="metric-switcher intraday-switcher" aria-label="切换图表分项">{METRIC_OPTIONS.map((metric) => <button key={metric.key} type="button" aria-pressed={chartMode === 'candle' ? candleMetric === metric.key : metrics.includes(metric.key)} className={(chartMode === 'candle' ? candleMetric === metric.key : metrics.includes(metric.key)) ? 'active' : ''} style={{ '--metric-color': metricColor(metric.key, theme) } as CSSProperties} onClick={() => toggleMetric(metric.key)}>{metric.label}</button>)}</div>
      {chartMode === 'candle' && <div className="candle-key"><span><i className="up"/>波动率上升</span><span><i className="down"/>波动率下降</span></div>}
      {chartMode === 'line' ? <IntradayChart data={points} metrics={metrics} marketOpen={showingCurrentSession ? market.data?.market_open : undefined} collectionEnd={showingCurrentSession ? market.data?.collection_end : undefined} marketActive={showingCurrentSession && Boolean(market.data?.is_collection_window)}/> : <IntradayCandlestickChart data={points} metric={candleMetric} intervalMinutes={candleInterval} marketOpen={showingCurrentSession ? market.data?.market_open : undefined} collectionEnd={showingCurrentSession ? market.data?.collection_end : undefined} marketActive={showingCurrentSession && Boolean(market.data?.is_collection_window)}/>}
      {intraday.isError && <p className="error">日内数据载入失败，请稍后重试。</p>}
    </section>
    <section className="trend-components"><div className="trend-section-heading"><div><h2>分项观察</h2><p>与主曲线使用同一交易日和计算口径</p></div><span>{points.length} 个观察点</span></div><div className="trend-component-grid">{METRIC_OPTIONS.filter((metric) => metric.key !== 'svix').map((metric) => {
      const point = [...points].reverse().find((item) => item[metric.key] !== null)
      const change = changeFor(points, metric.key)
      return <div key={metric.key} className="trend-component"><span className="component-dot" style={{ background: metricColor(metric.key, theme) }}/><div><span>{metric.label}</span><strong>{point?.[metric.key]?.toFixed(2) ?? '—'}<small>{point?.[metric.key] !== null && point ? '%' : ''}</small></strong></div><small className={change !== null && change >= 0 ? 'positive' : 'negative'}>{change === null ? '暂无可比变化' : `${change >= 0 ? '+' : ''}${change.toFixed(2)} 点`}</small></div>
    })}</div></section>
    <section className="trend-provenance"><div className="trend-section-heading"><div><h2>数据状态</h2><p>报价与计算信息</p></div><span>{calculationLabels[market.data?.last_calculation_status ?? ''] ?? '等待采集'}</span></div><div className="trend-facts"><div><span>最近采集</span><strong>{etTime(market.data?.last_collection_at)} ET</strong></div><div><span>原始权重覆盖</span><strong>{latest && Number.isFinite(latest.coverage) ? `${(latest.coverage * 100).toFixed(0)}%` : '—'}</strong></div><div><span>最旧报价</span><strong>{etTime(latest?.oldest_input_at)} ET</strong></div><div><span>本轮状态</span><strong>{latest ? labels[latest.status] ?? latest.status : '等待数据'}</strong></div></div>{latest && <details><summary>查看计算口径与来源</summary><p>方法 {latest.calculation_method} · 批次 {latest.batch_id ?? '历史'} · 报价源 {latest.source_feed ?? '未知'}{latest.cached_coverage ? ` · 缓存覆盖 ${(latest.cached_coverage * 100).toFixed(0)}%` : ''}</p><p>{Object.entries(latest.reasons ?? {}).map(([name, reason]) => `${name}: ${reasonLabels[reason] ?? reason}`).join(' · ') || '各分项可用'} · Memory {latest.component_counts?.memory ?? '0/2'} · AI {latest.component_counts?.ai ?? '0/3'}</p></details>}</section>
    {customConfig.data?.enabled && <section className="panel intraday-panel custom-intraday-panel"><div className="panel-title chart-title"><div><p className="eyebrow">CUSTOM INDEX · V{customConfig.data.version}</p><h3>{customConfig.data.name}</h3><p>{customConfig.data.components.map((item) => `${item.symbol} ${Number(item.weight_percent.toFixed(2))}%`).join(' · ')}</p></div><div className="custom-index-value"><strong>{customLatest?.value.toFixed(2) ?? '—'}</strong><small>{customIntraday.data?.length ?? 0} 个数据点{customLatest?.estimated ? ' · Indicative 估算' : ''}</small></div></div><CustomIndexChart data={customIntraday.data ?? []} name={customConfig.data.name} intraday/></section>}
  </main>
}
