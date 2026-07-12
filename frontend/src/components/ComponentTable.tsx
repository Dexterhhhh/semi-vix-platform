import type { Components } from '../types'
export function ComponentTable({ components }: { components?: Components }) {
  return <section className="panel"><h3>组件波动率</h3><table><tbody>{[['Core Semi', components?.core], ['Memory', components?.memory], ['AI Semi', components?.ai]].map(([name, value]) => <tr key={String(name)}><td>{name}</td><td>{typeof value === 'number' ? `${value.toFixed(2)}%` : '—'}</td></tr>)}</tbody></table></section>
}
