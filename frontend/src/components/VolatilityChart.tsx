import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { SVIXPoint } from '../types'
import { chartPalette, useTheme, type Theme } from '../theme'

export type MetricKey = 'svix' | 'core' | 'memory' | 'ai'
export const METRIC_OPTIONS: Array<{ key: MetricKey; label: string; color: string }> = [
  { key: 'svix', label: 'SVIX', color: '#007aff' },
  { key: 'core', label: 'Core Semi', color: '#805ad5' },
  { key: 'memory', label: 'Memory', color: '#c58423' },
  { key: 'ai', label: 'AI Semi', color: '#168d75' },
]
const darkMetricColors: Record<MetricKey, string> = { svix: '#0a84ff', core: '#bf5af2', memory: '#ff9f0a', ai: '#30d158' }
export const metricColor = (key: MetricKey, theme: Theme) => theme === 'dark' ? darkMetricColors[key] : METRIC_OPTIONS.find((item) => item.key === key)!.color

export function VolatilityChart({ data, metrics }: { data: SVIXPoint[]; metrics: MetricKey[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const { theme } = useTheme()
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    const selected = METRIC_OPTIONS.filter((metric) => metrics.includes(metric.key))
    const palette = chartPalette[theme]
    chart.setOption({
      animationDuration: 300,
      backgroundColor: 'transparent',
      aria: { enabled: true },
      tooltip: { trigger: 'axis', backgroundColor: palette.surface, borderColor: palette.border, textStyle: { color: palette.text }, valueFormatter: (value: unknown) => typeof value === 'number' ? value.toFixed(2) : String(value) },
      grid: { left: 52, right: 24, top: 28, bottom: 78 },
      xAxis: { type: 'time', boundaryGap: false, axisLine: { lineStyle: { color: palette.border } }, axisLabel: { color: palette.muted, hideOverlap: true } },
      yAxis: { type: 'value', name: '波动率', nameTextStyle: { color: palette.muted }, axisLabel: { color: palette.muted }, splitLine: { lineStyle: { color: palette.grid } }, scale: true },
      dataZoom: [
        { type: 'inside', filterMode: 'none', zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: true },
        { type: 'slider', filterMode: 'none', height: 22, bottom: 18, borderColor: palette.border, backgroundColor: palette.slider, fillerColor: theme === 'dark' ? 'rgba(10,132,255,.22)' : 'rgba(0,122,255,.16)', handleStyle: { color: palette.accent, borderColor: palette.accent }, textStyle: { color: palette.muted } },
      ],
      series: selected.flatMap((metric) => {
        const estimated = data.map((point) => [point.timestamp, point.estimated ? point[metric.key] : null])
        const strict = data.map((point) => [point.timestamp, point.estimated ? null : point[metric.key]])
        return [
          {
            name: `${metric.label} · 历史近似`,
            type: 'line',
            data: estimated,
            smooth: 0.2,
            showSymbol: data.filter((point) => point.estimated).length === 1,
            connectNulls: false,
            emphasis: { focus: 'series' },
            lineStyle: { color: metricColor(metric.key, theme), width: metric.key === 'svix' ? 2 : 1.5, type: 'dashed', opacity: 0.6 },
            itemStyle: { color: metricColor(metric.key, theme), opacity: 0.7 },
          },
          {
            name: `${metric.label} · 严格计算`,
            type: 'line',
            data: strict,
            smooth: 0.2,
            showSymbol: data.filter((point) => !point.estimated).length <= 2,
            connectNulls: false,
            emphasis: { focus: 'series' },
            lineStyle: { color: metricColor(metric.key, theme), width: metric.key === 'svix' ? 3 : 2, type: 'solid', opacity: 1 },
            itemStyle: { color: metricColor(metric.key, theme) },
            areaStyle: selected.length === 1 ? { color: `${metricColor(metric.key, theme)}22` } : undefined,
          },
        ]
      }),
    })
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(ref.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [data, metrics, theme])
  if (!data.length) return <div className="chart chart-empty">所选范围暂无历史数据。</div>
  return <div className="chart" ref={ref} role="img" aria-label="可缩放的半导体波动率历史走势图"/>
}
