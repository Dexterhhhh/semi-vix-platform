type Props = { label: string; value?: number | null; accent?: boolean }
export function SVIXCard({ label, value, accent = false }: Props) {
  return <section className={`metric-card ${accent ? 'accent' : ''}`}><span>{label}</span><strong>{value == null ? '—' : value.toFixed(2)}</strong><small>{value == null ? '等待计算结果' : '年化隐含波动率'}</small></section>
}
