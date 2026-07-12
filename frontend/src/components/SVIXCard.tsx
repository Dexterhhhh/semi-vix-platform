type Props = { label: string; value?: number; accent?: boolean }
export function SVIXCard({ label, value, accent = false }: Props) {
  return <section className={`metric-card ${accent ? 'accent' : ''}`}><span>{label}</span><strong>{value === undefined ? '—' : value.toFixed(2)}</strong><small>{value === undefined ? '等待计算结果' : '年化隐含波动率'}</small></section>
}
