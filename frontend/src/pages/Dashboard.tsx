import { useState, type CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getComponents, getCurrentSVIX, getHistory } from '../api/svix'
import { SVIXCard } from '../components/SVIXCard'
import { METRIC_OPTIONS, VolatilityChart, type MetricKey } from '../components/VolatilityChart'
import { ComponentTable } from '../components/ComponentTable'
import { IndexMethodology } from '../components/IndexMethodology'
import { CustomIndexChart } from '../components/CustomIndexChart'
import { getCurrentCustomIndex, getCustomIndex, getCustomIndexHistory } from '../api/customIndex'

type RangeKey = '1M' | '3M' | '6M' | '1Y' | 'MAX'
const MAX_HISTORY_START = '2000-01-01'

const isoDay = (value: Date) => value.toISOString().slice(0, 10)
const today = () => isoDay(new Date())
const rangeStart = (range: RangeKey) => {
  if (range === 'MAX') return MAX_HISTORY_START
  const value = new Date()
  if (range === '1Y') value.setUTCFullYear(value.getUTCFullYear() - 1)
  else value.setUTCMonth(value.getUTCMonth() - Number.parseInt(range, 10))
  return isoDay(value)
}

export function Dashboard() {
  const [activeRange, setActiveRange] = useState<RangeKey | null>('1M')
  const [startDate, setStartDate] = useState(() => rangeStart('1M'))
  const [endDate, setEndDate] = useState(today)
  const [metrics, setMetrics] = useState<MetricKey[]>(['svix'])
  const validRange = startDate <= endDate
  const current = useQuery({ queryKey: ['svix-current'], queryFn: getCurrentSVIX, retry: false })
  const components = useQuery({ queryKey: ['svix-components'], queryFn: getComponents, retry: false })
  const history = useQuery({ queryKey: ['svix-history', startDate, endDate], queryFn: () => getHistory(startDate, endDate), enabled: validRange, retry: false })
  const customConfig = useQuery({ queryKey: ['custom-index'], queryFn: getCustomIndex })
  const customEnabled = Boolean(customConfig.data?.enabled)
  const customCurrent = useQuery({ queryKey: ['custom-index-current', customConfig.data?.version], queryFn: getCurrentCustomIndex, enabled: customEnabled, retry: false })
  const customHistory = useQuery({ queryKey: ['custom-index-history', customConfig.data?.version, startDate, endDate], queryFn: () => getCustomIndexHistory(startDate, endDate), enabled: customEnabled && validRange, retry: false })
  const value = current.data

  const chooseRange = (range: RangeKey) => {
    setActiveRange(range)
    setStartDate(rangeStart(range))
    setEndDate(today())
  }
  const toggleMetric = (metric: MetricKey) => {
    setMetrics((selected) => selected.includes(metric)
      ? (selected.length === 1 ? selected : selected.filter((item) => item !== metric))
      : [...selected, metric])
  }

  return <main>
    <header><div><p className="eyebrow">SEMICONDUCTOR VOLATILITY</p><h1>Semi‑VIX Dashboard</h1></div><span className="status-dot">只读分析</span></header>
    <div className="cards"><SVIXCard label="SVIX 30D" value={value?.svix} accent/><SVIXCard label="Core Semi" value={value?.core}/><SVIXCard label="Memory" value={value?.memory}/><SVIXCard label="AI Semi" value={value?.ai}/></div>
    <section className="panel chart-panel">
      <div className="panel-title chart-title"><div><h3>历史走势</h3><p>同色浅虚线为历史近似值，同色实线为严格计算值；可拖动底部滑块或在图内缩放</p></div><span className="chart-status">{history.isFetching ? '载入中…' : `${history.data?.length ?? 0} 个数据点${history.data?.some((point) => point.estimated) ? ` · ${history.data.filter((point) => point.estimated).length} 个近似` : ''}${history.data?.some((point) => !point.estimated) ? ` · ${history.data.filter((point) => !point.estimated).length} 个严格` : ''}`}</span></div>
      <div className="chart-controls">
        <div className="metric-switcher" aria-label="图表指标">
          {METRIC_OPTIONS.map((metric) => <button key={metric.key} type="button" aria-pressed={metrics.includes(metric.key)} className={metrics.includes(metric.key) ? 'active' : ''} style={{ '--metric-color': metric.color } as CSSProperties} onClick={() => toggleMetric(metric.key)}>{metric.label}</button>)}
        </div>
        <div className="range-controls">
          <div className="ranges" aria-label="快速时间范围">
            {(['1M', '3M', '6M', '1Y', 'MAX'] as RangeKey[]).map((range) => <button key={range} type="button" aria-pressed={activeRange === range} className={activeRange === range ? 'active' : ''} onClick={() => chooseRange(range)}>{range}</button>)}
          </div>
          <label>开始<input aria-label="图表开始日期" type="date" min={MAX_HISTORY_START} max={endDate} value={startDate} onChange={(event) => { setStartDate(event.target.value); setActiveRange(null) }}/></label>
          <span>—</span>
          <label>结束<input aria-label="图表结束日期" type="date" min={startDate} max={today()} value={endDate} onChange={(event) => { setEndDate(event.target.value); setActiveRange(null) }}/></label>
        </div>
      </div>
      {!validRange
        ? <p className="chart-empty error">开始日期不能晚于结束日期。</p>
        : history.isError
          ? <p className="chart-empty error">历史数据载入失败，请稍后重试。</p>
          : <VolatilityChart data={history.data ?? []} metrics={metrics}/>}
    </section>
    <ComponentTable components={components.data}/>
    {current.isError && <p className="empty">暂无 SVIX 历史数据。先完成行情采集并创建历史计算任务。</p>}
    {customConfig.data?.enabled && <section className="panel custom-index-dashboard">
      <div className="custom-index-summary"><div><span>独立自定义指数 · V{customConfig.data.version}</span><h3>{customConfig.data.name}</h3><p>{customConfig.data.components.map((item) => `${item.symbol} ${Number(item.weight_percent.toFixed(2))}%`).join(' · ')}</p></div><div className="custom-index-value"><strong>{customCurrent.data?.value.toFixed(2) ?? '—'}</strong><small>{customCurrent.data ? `质量 ${(customCurrent.data.calculation_quality * 100).toFixed(0)}%` : '等待首次计算'}</small></div></div>
      <CustomIndexChart data={customHistory.data ?? []} name={customConfig.data.name}/>
    </section>}
    <IndexMethodology/>
  </main>
}
