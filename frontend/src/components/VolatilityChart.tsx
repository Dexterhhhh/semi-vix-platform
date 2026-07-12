import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { SVIXPoint } from '../types'

export function VolatilityChart({ data }: { data: SVIXPoint[] }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chart.setOption({ backgroundColor: 'transparent', tooltip: { trigger: 'axis' }, grid: { left: 42, right: 18, top: 24, bottom: 32 }, xAxis: { type: 'category', data: data.map((point) => new Date(point.timestamp).toLocaleDateString()), axisLine: { lineStyle: { color: '#334155' } } }, yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1e293b' } } }, series: [{ type: 'line', data: data.map((point) => point.svix), smooth: true, showSymbol: false, lineStyle: { color: '#38bdf8', width: 3 }, areaStyle: { color: 'rgba(56,189,248,.16)' } }] })
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(ref.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [data])
  return <div className="chart" ref={ref} />
}
