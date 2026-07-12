import { useQuery } from '@tanstack/react-query'
import { getComponents, getCurrentSVIX, getHistory } from '../api/svix'
import { SVIXCard } from '../components/SVIXCard'
import { VolatilityChart } from '../components/VolatilityChart'
import { ComponentTable } from '../components/ComponentTable'

const day = (offset: number) => new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10)
export function Dashboard() {
  const current = useQuery({ queryKey: ['svix-current'], queryFn: getCurrentSVIX, retry: false })
  const components = useQuery({ queryKey: ['svix-components'], queryFn: getComponents, retry: false })
  const history = useQuery({ queryKey: ['svix-history', '30d'], queryFn: () => getHistory(day(-30), day(0)), retry: false })
  const value = current.data
  return <main><header><div><p className="eyebrow">SEMICONDUCTOR VOLATILITY</p><h1>Semi‑VIX Dashboard</h1></div><span className="status-dot">只读分析</span></header><div className="cards"><SVIXCard label="SVIX 30D" value={value?.svix} accent/><SVIXCard label="Core Semi" value={value?.core}/><SVIXCard label="Memory" value={value?.memory}/><SVIXCard label="AI Semi" value={value?.ai}/></div><section className="panel chart-panel"><div className="panel-title"><div><h3>SVIX 历史走势</h3><p>30 日年化隐含波动率</p></div><div className="ranges">1M　3M　6M　1Y　MAX</div></div><VolatilityChart data={history.data ?? []}/></section><ComponentTable components={components.data}/>{current.isError && <p className="empty">暂无 SVIX 历史数据。先完成行情采集并创建历史计算任务。</p>}</main>
}
