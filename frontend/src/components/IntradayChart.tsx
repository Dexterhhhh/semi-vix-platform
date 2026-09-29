import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

import type { ObservationPoint } from '../types'
import { METRIC_OPTIONS, type MetricKey } from './VolatilityChart'
import { metricColor } from './VolatilityChart'
import { chartPalette, useTheme } from '../theme'

const nyTime = new Intl.DateTimeFormat('zh-CN', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false })

export function IntradayChart({ data, metrics, marketOpen, collectionEnd, marketActive = false }: { data: ObservationPoint[]; metrics: MetricKey[]; marketOpen?: string | null; collectionEnd?: string | null; marketActive?: boolean }) {
  const element = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const { theme } = useTheme()

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
    const palette = chartPalette[theme]
    const openedAt = marketOpen ? new Date(marketOpen).getTime() : undefined
    const closesAt = collectionEnd ? new Date(collectionEnd).getTime() : undefined
    const latestAt = data.length ? new Date(data[data.length - 1].timestamp).getTime() : undefined
    const progressiveEnd = openedAt === undefined ? undefined : Math.max(openedAt + 60 * 60 * 1000, (latestAt ?? openedAt) + 15 * 60 * 1000)
    const visibleEnd = marketActive && closesAt !== undefined && progressiveEnd !== undefined ? Math.min(closesAt, progressiveEnd) : closesAt
    const lineData = (key: MetricKey): [string, number | null][] => data.flatMap((point, index) => {
      const previous = data[index - 1]
      const separated = previous && (new Date(point.timestamp).getTime() - new Date(previous.timestamp).getTime() > 10 * 60_000 || point.comparable_key !== previous.comparable_key)
      return separated ? [[new Date((new Date(point.timestamp).getTime() + new Date(previous.timestamp).getTime()) / 2).toISOString(), null], [point.timestamp, point[key]]] : [[point.timestamp, point[key]]]
    })
    chart.current.setOption({
      animationDuration: 500,
      animationDurationUpdate: 900,
      animationEasingUpdate: 'cubicOut',
      backgroundColor: 'transparent',
      aria: { enabled: true },
      tooltip: {
        trigger: 'axis',
        backgroundColor: palette.surface,
        borderColor: palette.border,
        textStyle: { color: palette.text, fontSize: 12 },
        extraCssText: 'box-shadow:0 10px 30px rgba(29,45,69,.11);border-radius:10px;',
        formatter: (items: Array<{ axisValue: number; marker: string; seriesName: string; data: [string, number | null] }>) => {
          if (!items.length) return ''
          return `<strong>${nyTime.format(new Date(items[0].axisValue))} ET</strong><br/>${items.filter((item) => !item.seriesName.endsWith('数据点') && typeof item.data[1] === 'number').map((item) => `${item.marker}${item.seriesName}: ${item.data[1]?.toFixed(2)}`).join('<br/>')}`
        },
      },
      grid: { left: 44, right: 45, top: 20, bottom: 42 },
      xAxis: {
        type: 'time',
        min: openedAt,
        max: visibleEnd,
        boundaryGap: false,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: palette.muted, formatter: (value: number) => nyTime.format(new Date(value)) },
        splitLine: { show: true, lineStyle: { color: palette.grid } },
      },
      yAxis: { type: 'value', scale: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: palette.muted }, splitLine: { lineStyle: { color: palette.grid } } },
      series: selected.flatMap((metric) => [
        {
          name: metric.label,
          type: 'line',
          data: lineData(metric.key),
          smooth: 0.12,
          showSymbol: false,
          lineStyle: { color: metricColor(metric.key, theme), width: metric.key === 'svix' ? 3 : 2 },
          itemStyle: { color: metricColor(metric.key, theme) },
          areaStyle: selected.length === 1 ? { color: `${metricColor(metric.key, theme)}22` } : undefined,
          endLabel: { show: data.length > 1, color: metricColor(metric.key, theme), formatter: (item: { value: [string, number | null] }) => item.value[1]?.toFixed(2) ?? '' },
        },
        {
          name: `${metric.label} 数据点`,
          type: 'scatter',
          data: data.length <= 12 ? data.filter((point) => point[metric.key] !== null).map((point) => [point.timestamp, point[metric.key]]) : [],
          symbol: 'circle',
          symbolSize: 6,
          z: 6,
          itemStyle: { color: metricColor(metric.key, theme), borderColor: palette.dotBorder, borderWidth: 1.5 },
          tooltip: { show: false },
        },
      ]),
    }, { notMerge: false, replaceMerge: ['series'] })
  }, [collectionEnd, data, marketActive, marketOpen, metrics, theme])

  return (
    <div className="intraday-chart-frame">
      <div ref={element} className="intraday-chart" role="img" aria-label="自动更新的单日 SVIX 分时走势图" />
      {!data.length && <div className="intraday-chart-empty">等待本交易日第一条可用计算数据…</div>}
    </div>
  )
}
