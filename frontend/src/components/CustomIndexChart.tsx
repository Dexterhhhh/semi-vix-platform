import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { CustomIndexPoint } from '../types'

export function CustomIndexChart({ data, name, intraday = false }: { data: CustomIndexPoint[]; name: string; intraday?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chart.setOption({
      animationDurationUpdate: 700, backgroundColor: 'transparent', aria: { enabled: true },
      tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => typeof value === 'number' ? value.toFixed(2) : String(value) },
      grid: { left: 52, right: 28, top: 26, bottom: intraday ? 45 : 72 },
      xAxis: { type: 'time', boundaryGap: false, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#94a3b8', hideOverlap: true } },
      yAxis: { type: 'value', scale: true, name: '波动率', nameTextStyle: { color: '#64748b' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#1e293b' } } },
      dataZoom: intraday ? [] : [{ type: 'inside', filterMode: 'none' }, { type: 'slider', filterMode: 'none', height: 20, bottom: 16, borderColor: '#334155', backgroundColor: '#0b1728', fillerColor: 'rgba(244,114,182,.18)', textStyle: { color: '#94a3b8' } }],
      series: [{ name, type: 'line', data: data.map((point) => [point.timestamp, point.value]), smooth: .18, showSymbol: intraday || data.length <= 2, symbolSize: 7, lineStyle: { color: '#f472b6', width: 3 }, itemStyle: { color: '#f472b6' }, areaStyle: { color: 'rgba(244,114,182,.14)' }, endLabel: { show: intraday && data.length > 1, color: '#f472b6', formatter: (item: { value: [string, number] }) => item.value[1].toFixed(2) } }],
    }, { notMerge: true })
    const observer = new ResizeObserver(() => chart.resize()); observer.observe(ref.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [data, intraday, name])
  if (!data.length) return <div className="custom-index-chart chart-empty">等待自定义指数计算结果。</div>
  return <div ref={ref} className="custom-index-chart" role="img" aria-label={`${name}走势图`}/>
}
