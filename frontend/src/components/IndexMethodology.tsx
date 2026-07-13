import type { CSSProperties } from 'react'

const definitions = [
  {
    name: 'SVIX 30D',
    color: '#38bdf8',
    description: '半导体组合的 30 天隐含波动率。先计算各标的 VIX 式隐含方差，再结合相关性矩阵合成为组合波动率。',
    allocations: [['Core Semi', '50%'], ['Memory', '30%'], ['AI Semi', '20%']],
  },
  {
    name: 'Core Semi',
    color: '#a78bfa',
    description: '以半导体 ETF 代表行业核心波动率。',
    allocations: [['SOXX', '100%']],
  },
  {
    name: 'Memory',
    color: '#fbbf24',
    description: '聚焦存储产业相关标的的组合波动率。',
    allocations: [['MU', '50%'], ['SKHY', '50%']],
  },
  {
    name: 'AI Semi',
    color: '#34d399',
    description: '聚焦 AI 计算与相关半导体公司的组合波动率。',
    allocations: [['NVDA', '50%'], ['AMD', '25%'], ['AVGO', '25%']],
  },
] as const

export function IndexMethodology() {
  return <section className="panel methodology-panel">
    <div className="methodology-heading">
      <div><h3>指标构成与计算说明</h3><p>以下为基础权重；最终结果使用各标的隐含波动率及相关性共同计算，并不是各波动率的简单加权平均。</p></div>
      <span>30D IMPLIED VOLATILITY</span>
    </div>
    <div className="methodology-grid">
      {definitions.map((definition) => <article key={definition.name} style={{ '--method-color': definition.color } as CSSProperties}>
        <h4>{definition.name}</h4>
        <p>{definition.description}</p>
        <div className="allocation-list">
          {definition.allocations.map(([symbol, weight]) => <div key={symbol}><span>{symbol}</span><strong>{weight}</strong><i><b style={{ width: weight }}/></i></div>)}
        </div>
      </article>)}
    </div>
    <div className="methodology-notes">
      <p><strong>相关性：</strong>60 / 120 / 252 个交易日窗口分别占 50% / 30% / 20%，用于构建组合协方差矩阵。</p>
      <p><strong>去重调整：</strong>如提供 SOXX 成分暴露，系统会扣除 SOXX 与直接持有股票之间的重复暴露，再把剩余权重归一化。</p>
      <p><strong>数据可用性：</strong>某个分组内部分标的缺失时，仅在满足最低覆盖条件后使用可用标的重新归一化；覆盖不足则不会生成正式结果。</p>
    </div>
  </section>
}
