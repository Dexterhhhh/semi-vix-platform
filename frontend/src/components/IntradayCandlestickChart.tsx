import { useEffect, useMemo, useRef } from 'react'
import * as echarts from '../lib/echarts'

import type { ObservationPoint } from '../types'
import { aggregateIntradayCandles } from '../lib/intradayCandles'
import { METRIC_OPTIONS, type MetricKey } from './VolatilityChart'
import { chartPalette, useTheme } from '../theme'

const nyTime = new Intl.DateTimeFormat('zh-CN', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false })

export function IntradayCandlestickChart({ data, metric, intervalMinutes, marketOpen, collectionEnd, marketActive = false }: { data: ObservationPoint[]; metric: MetricKey; intervalMinutes: number; marketOpen?: string | null; collectionEnd?: string | null; marketActive?: boolean }) {
  const element = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const { theme } = useTheme()
  const candles = useMemo(() => aggregateIntradayCandles(data, metric, intervalMinutes), [data, metric, intervalMinutes])
  const metricLabel = METRIC_OPTIONS.find((item) => item.key === metric)?.label ?? metric

  useEffect(() => {
    if (!element.current) return
    chart.current = echarts.init(element.current)
    const observer = new ResizeObserver(() => chart.current?.resize())
    observer.observe(element.current)
    return () => { observer.disconnect(); chart.current?.dispose(); chart.current = null }
  }, [])

  useEffect(() => {
    if (!chart.current) return
    const palette = chartPalette[theme]
    const duration = intervalMinutes * 60_000
    const openedAt = marketOpen ? Date.parse(marketOpen) : candles[0]?.timestamp
    const closesAt = collectionEnd ? Date.parse(collectionEnd) : undefined
    const latestAt = candles.at(-1)?.timestamp
    const progressiveEnd = openedAt === undefined ? undefined : Math.max(openedAt + 60 * 60_000, (latestAt ?? openedAt) + 15 * 60_000)
    const visibleEnd = marketActive && closesAt !== undefined && progressiveEnd !== undefined ? Math.min(closesAt, progressiveEnd) : closesAt ?? latestAt
    const start = openedAt === undefined ? undefined : Math.floor(openedAt / duration) * duration
    const end = visibleEnd === undefined ? undefined : Math.max(start ?? visibleEnd, Math.min(visibleEnd, latestAt ?? visibleEnd))
    const slots: number[] = []
    if (start !== undefined && end !== undefined) for (let time = start; time <= end && slots.length < 500; time += duration) slots.push(time)
    const byTime = new Map(candles.map((candle) => [candle.timestamp, candle]))
    chart.current.setOption({
      animationDuration: 350,
      backgroundColor: 'transparent',
      aria: { enabled: false },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'cross' },
        backgroundColor: palette.surface, borderColor: palette.border, textStyle: { color: palette.text, fontSize: 12 },
        extraCssText: 'box-shadow:0 10px 30px rgba(29,45,69,.11);border-radius:10px;',
        formatter: (items: Array<{ dataIndex: number }>) => {
          const candle = byTime.get(slots[items[0]?.dataIndex])
          if (!candle) return ''
          return `<strong>${nyTime.format(new Date(candle.timestamp))} ET · ${intervalMinutes} 分钟</strong><br/>开 ${candle.open.toFixed(2)}% · 高 ${candle.high.toFixed(2)}%<br/>低 ${candle.low.toFixed(2)}% · 收 ${candle.close.toFixed(2)}%<br/>${candle.count} 个有效观察点`
        },
      },
      grid: { left: 44, right: 30, top: 24, bottom: 42 },
      xAxis: { type: 'category', data: slots, boundaryGap: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: palette.muted, formatter: (value: number) => nyTime.format(new Date(Number(value))) }, splitLine: { show: true, lineStyle: { color: palette.grid } } },
      yAxis: { type: 'value', scale: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: palette.muted, formatter: (value: number) => `${value}%` }, splitLine: { lineStyle: { color: palette.grid } } },
      series: [{
        name: `${metricLabel} 蜡烛图`, type: 'candlestick',
        data: slots.map((time) => {
          const candle = byTime.get(time)
          return candle ? [candle.open, candle.close, candle.low, candle.high] : '-'
        }),
        barMaxWidth: 17,
        itemStyle: { color: theme === 'dark' ? '#ff6961' : '#d35e69', color0: theme === 'dark' ? '#30d158' : '#19a085', borderColor: theme === 'dark' ? '#ff6961' : '#d35e69', borderColor0: theme === 'dark' ? '#30d158' : '#19a085' },
      }],
    }, { notMerge: true })
  }, [candles, collectionEnd, intervalMinutes, marketActive, marketOpen, metricLabel, theme])

  return <div className="intraday-chart-frame">
    <div ref={element} className="intraday-chart" role="img" aria-label={`${metricLabel} ${intervalMinutes} 分钟波动率蜡烛图`} />
    {!candles.length && <div className="intraday-chart-empty">等待本交易日第一条可用计算数据…</div>}
  </div>
}
