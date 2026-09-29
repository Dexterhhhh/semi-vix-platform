import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { CustomIndexPoint } from '../types'
import { chartPalette, useTheme } from '../theme'

export function CustomIndexChart({ data, name, intraday = false }: { data: CustomIndexPoint[]; name: string; intraday?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const { theme } = useTheme()
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    const palette = chartPalette[theme]
    const accent = theme === 'dark' ? '#bf5af2' : '#805ad5'
    chart.setOption({
      animationDurationUpdate: 700, backgroundColor: 'transparent', aria: { enabled: true },
      tooltip: { trigger: 'axis', backgroundColor: palette.surface, borderColor: palette.border, textStyle: { color: palette.text }, valueFormatter: (value: unknown) => typeof value === 'number' ? value.toFixed(2) : String(value) },
      grid: { left: 52, right: 28, top: 26, bottom: intraday ? 45 : 72 },
      xAxis: { type: 'time', boundaryGap: false, axisLine: { lineStyle: { color: palette.border } }, axisLabel: { color: palette.muted, hideOverlap: true } },
      yAxis: { type: 'value', scale: true, name: '波动率', nameTextStyle: { color: palette.muted }, axisLabel: { color: palette.muted }, splitLine: { lineStyle: { color: palette.grid } } },
      dataZoom: intraday ? [] : [{ type: 'inside', filterMode: 'none' }, { type: 'slider', filterMode: 'none', height: 20, bottom: 16, borderColor: palette.border, backgroundColor: palette.slider, fillerColor: `${accent}22`, textStyle: { color: palette.muted } }],
      series: [{ name, type: 'line', data: data.map((point) => [point.timestamp, point.value]), smooth: .18, showSymbol: intraday || data.length <= 2, symbolSize: 7, lineStyle: { color: accent, width: 3 }, itemStyle: { color: accent }, areaStyle: { color: `${accent}22` }, endLabel: { show: intraday && data.length > 1, color: accent, formatter: (item: { value: [string, number] }) => item.value[1].toFixed(2) } }],
    }, { notMerge: true })
    const observer = new ResizeObserver(() => chart.resize()); observer.observe(ref.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [data, intraday, name, theme])
  if (!data.length) return <div className="custom-index-chart chart-empty">等待自定义指数计算结果。</div>
  return <div ref={ref} className="custom-index-chart" role="img" aria-label={`${name}走势图`}/>
}
