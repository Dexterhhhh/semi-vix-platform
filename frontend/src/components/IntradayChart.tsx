import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

import type { SVIXPoint } from '../types'
import { METRIC_OPTIONS, type MetricKey } from './VolatilityChart'

const nyTime = new Intl.DateTimeFormat('zh-CN', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false })

export function IntradayChart({ data, metrics, marketOpen, collectionEnd, marketActive = false }: { data: SVIXPoint[]; metrics: MetricKey[]; marketOpen?: string | null; collectionEnd?: string | null; marketActive?: boolean }) {
  const element = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!element.current) return
    chart.current = echarts.init(element.current)
    const observer = new ResizeObserver(() => chart.current?.resize())
    observer.observe(element.current)
    return () => { observer.disconnect(); chart.current?.dispose(); chart.current = null }
  }, [])

  useEffect(() => {
    if (!chart.current) return
    const selected = METRIC_OPTIONS.filter((metric) => metrics.includes(metric.key))
    const openedAt = marketOpen ? new Date(marketOpen).getTime() : undefined
    const closesAt = collectionEnd ? new Date(collectionEnd).getTime() : undefined
    const latestAt = data.length ? new Date(data[data.length - 1].timestamp).getTime() : undefined
    const progressiveEnd = openedAt === undefined ? undefined : Math.max(openedAt + 60 * 60 * 1000, (latestAt ?? openedAt) + 15 * 60 * 1000)
    const visibleEnd = marketActive && closesAt !== undefined && progressiveEnd !== undefined ? Math.min(closesAt, progressiveEnd) : closesAt
    chart.current.setOption({
      animationDuration: 500,
      animationDurationUpdate: 900,
      animationEasingUpdate: 'cubicOut',
      backgroundColor: 'transparent',
      aria: { enabled: true },
      tooltip: {
        trigger: 'axis',
        formatter: (items: Array<{ axisValue: number; marker: string; seriesName: string; data: [string, number] }>) => {
          if (!items.length) return ''
          return `<strong>${nyTime.format(new Date(items[0].axisValue))} ET</strong><br/>${items.filter((item) => !item.seriesName.endsWith('数据点')).map((item) => `${item.marker}${item.seriesName}: ${item.data[1].toFixed(2)}`).join('<br/>')}`
        },
      },
      grid: { left: 56, right: 24, top: 28, bottom: 52 },
      xAxis: {
        type: 'time',
        min: openedAt,
        max: visibleEnd,
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#94a3b8', formatter: (value: number) => nyTime.format(new Date(value)) },
        splitLine: { show: true, lineStyle: { color: '#13233a' } },
      },
      yAxis: { type: 'value', scale: true, name: '波动率', nameTextStyle: { color: '#64748b' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#1e293b' } } },
      series: selected.flatMap((metric) => [
        {
          name: metric.label,
          type: 'line',
          data: data.map((point) => [point.timestamp, point[metric.key]]),
          smooth: 0.18,
          showSymbol: false,
          lineStyle: { color: metric.color, width: metric.key === 'svix' ? 3 : 2 },
          itemStyle: { color: metric.color },
          areaStyle: selected.length === 1 ? { color: `${metric.color}25` } : undefined,
          endLabel: { show: data.length > 1, color: metric.color, formatter: (item: { value: [string, number] }) => item.value[1].toFixed(2) },
        },
        {
          name: `${metric.label} 数据点`,
          type: 'scatter',
          data: data.map((point) => [point.timestamp, point[metric.key]]),
          symbol: 'circle',
          symbolSize: 8,
          z: 6,
          itemStyle: { color: metric.color, borderColor: '#e0f2fe', borderWidth: 1.5 },
          tooltip: { show: false },
        },
      ]),
    }, { notMerge: false, replaceMerge: ['series'] })
  }, [collectionEnd, data, marketActive, marketOpen, metrics])

  return (
    <div className="intraday-chart-frame">
      <div ref={element} className="intraday-chart" role="img" aria-label="自动更新的单日 SVIX 分时走势图" />
      {!data.length && <div className="intraday-chart-empty">等待本交易日第一条可用计算数据…</div>}
    </div>
  )
}
