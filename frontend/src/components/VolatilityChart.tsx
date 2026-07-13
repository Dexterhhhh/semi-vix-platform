import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { SVIXPoint } from '../types'

export type MetricKey = 'svix' | 'core' | 'memory' | 'ai'
export const METRIC_OPTIONS: Array<{ key: MetricKey; label: string; color: string }> = [
  { key: 'svix', label: 'SVIX', color: '#38bdf8' },
  { key: 'core', label: 'Core Semi', color: '#a78bfa' },
  { key: 'memory', label: 'Memory', color: '#fbbf24' },
  { key: 'ai', label: 'AI Semi', color: '#34d399' },
]

export function VolatilityChart({ data, metrics }: { data: SVIXPoint[]; metrics: MetricKey[] }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    const selected = METRIC_OPTIONS.filter((metric) => metrics.includes(metric.key))
    chart.setOption({
      animationDuration: 300,
      backgroundColor: 'transparent',
      aria: { enabled: true },
      tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => typeof value === 'number' ? value.toFixed(2) : String(value) },
      grid: { left: 52, right: 24, top: 28, bottom: 78 },
      xAxis: { type: 'time', boundaryGap: false, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#94a3b8', hideOverlap: true } },
      yAxis: { type: 'value', name: '波动率', nameTextStyle: { color: '#64748b' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#1e293b' } }, scale: true },
      dataZoom: [
        { type: 'inside', filterMode: 'none', zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: true },
        { type: 'slider', filterMode: 'none', height: 22, bottom: 18, borderColor: '#334155', backgroundColor: '#0b1728', fillerColor: 'rgba(56,189,248,.18)', handleStyle: { color: '#38bdf8', borderColor: '#7dd3fc' }, textStyle: { color: '#94a3b8' } },
      ],
      series: selected.flatMap((metric) => {
        const estimated = data.filter((point) => point.estimated)
        const strict = data.filter((point) => !point.estimated)
        return [
          {
            name: `${metric.label} · 历史近似`,
            type: 'line',
            data: estimated.map((point) => [point.timestamp, point[metric.key]]),
            smooth: 0.2,
            showSymbol: estimated.length === 1,
            connectNulls: false,
            emphasis: { focus: 'series' },
            lineStyle: { color: metric.color, width: metric.key === 'svix' ? 2 : 1.5, type: 'dashed', opacity: 0.45 },
            itemStyle: { color: metric.color, opacity: 0.55 },
          },
          {
            name: `${metric.label} · 严格计算`,
            type: 'line',
            data: strict.map((point) => [point.timestamp, point[metric.key]]),
            smooth: 0.2,
            showSymbol: strict.length <= 2,
            connectNulls: false,
            emphasis: { focus: 'series' },
            lineStyle: { color: metric.color, width: metric.key === 'svix' ? 3 : 2, type: 'solid', opacity: 1 },
            itemStyle: { color: metric.color },
            areaStyle: selected.length === 1 ? { color: `${metric.color}22` } : undefined,
          },
        ]
      }),
    })
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(ref.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [data, metrics])
  if (!data.length) return <div className="chart chart-empty">所选范围暂无历史数据。</div>
  return <div className="chart" ref={ref} role="img" aria-label="可缩放的半导体波动率历史走势图"/>
}
