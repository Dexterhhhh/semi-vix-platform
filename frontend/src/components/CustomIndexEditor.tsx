import { FormEvent, useEffect, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

import { getCustomIndex, getListedSymbol, saveCustomIndex } from '../api/customIndex'
import type { CustomIndexComponent, CustomIndexPayload } from '../types'

type EditableComponent = CustomIndexComponent & { rowId: string }
const newRowId = () => crypto.randomUUID()
const defaults: EditableComponent[] = [{ rowId: newRowId(), symbol: 'NVDA', weight_percent: 50 }, { rowId: newRowId(), symbol: 'AMD', weight_percent: 25 }, { rowId: newRowId(), symbol: 'AVGO', weight_percent: 25 }]
const symbolPattern = /^[A-Z][A-Z0-9.-]{0,15}$/

export function CustomIndexEditor() {
  const client = useQueryClient()
  const config = useQuery({ queryKey: ['custom-index'], queryFn: getCustomIndex })
  const [name, setName] = useState('My Semiconductor Index')
  const [enabled, setEnabled] = useState(true)
  const [missingPolicy, setMissingPolicy] = useState<'STRICT' | 'RENORMALIZE'>('STRICT')
  const [components, setComponents] = useState<EditableComponent[]>(defaults)
  const symbols = components.map((item) => item.symbol.trim().toUpperCase())
  const symbolInputKey = symbols.join('\0')
  const [debouncedSymbols, setDebouncedSymbols] = useState(defaults.map((item) => item.symbol))
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSymbols(symbolInputKey.split('\0')), 350)
    return () => window.clearTimeout(timer)
  }, [symbolInputKey])
  const lookups = useQueries({ queries: components.map((_, index) => {
    const symbol = debouncedSymbols[index] ?? ''
    return {
      queryKey: ['listed-symbol', symbol],
      queryFn: () => getListedSymbol(symbol),
      enabled: symbol === symbols[index] && symbolPattern.test(symbol),
      staleTime: 6 * 60 * 60 * 1000,
      retry: false,
    }
  }) })
  useEffect(() => {
    if (!config.data) return
    setName(config.data.name); setEnabled(config.data.enabled); setMissingPolicy(config.data.missing_policy); setComponents(config.data.components.map((item) => ({ ...item, rowId: newRowId() })))
  }, [config.data])
  const save = useMutation({ mutationFn: saveCustomIndex, onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ['custom-index'] }), client.invalidateQueries({ queryKey: ['custom-index-current'] }), client.invalidateQueries({ queryKey: ['custom-index-history'] })]) } })
  const total = components.reduce((sum, item) => sum + (Number(item.weight_percent) || 0), 0)
  const duplicate = new Set(components.map((item) => item.symbol.trim().toUpperCase())).size !== components.length
  const valid = name.trim().length > 0 && components.length > 0 && components.every((item) => symbolPattern.test(item.symbol.trim().toUpperCase()) && item.weight_percent > 0) && Math.abs(total - 100) <= .01 && !duplicate && lookups.every((lookup, index) => lookup.data?.symbol === symbols[index])
  const update = (position: number, value: Partial<CustomIndexComponent>) => setComponents((items) => items.map((item, index) => index === position ? { ...item, ...value } : item))
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!valid) return
    const payload: CustomIndexPayload = { name: name.trim(), enabled, missing_policy: missingPolicy, components: components.map((item) => ({ symbol: item.symbol.trim().toUpperCase(), weight_percent: Number(item.weight_percent) })) }
    save.mutate(payload)
  }
  return <section className="panel custom-index-editor">
    <div className="panel-title"><h3>独立自定义指数</h3>{config.data && <span className="version-badge">版本 V{config.data.version}</span>}</div>
    <form onSubmit={submit}>
      <div className="custom-index-meta">
        <label>指数名称<input value={name} maxLength={64} onChange={(event) => setName(event.target.value)}/></label>
        <label>缺失数据策略<select value={missingPolicy} onChange={(event) => setMissingPolicy(event.target.value as 'STRICT' | 'RENORMALIZE')}><option value="STRICT">严格：任一标的缺失则不计算</option><option value="RENORMALIZE">容错：可用权重≥50%时重新归一化</option></select></label>
        <label className="enable-custom"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)}/> 启用自动采集与计算</label>
      </div>
      <div className="custom-components">
        <div className="component-header"><span>标的代码</span><span>公司 / 标的名称</span><span>基础权重</span><span/></div>
        {components.map((component, index) => {
          const symbol = symbols[index]
          const lookup = lookups[index]
          const nameStatus = !symbol ? '输入代码' : !symbolPattern.test(symbol) ? '代码格式无效' : debouncedSymbols[index] !== symbol || lookup.isPending ? '识别中…' : lookup.data?.symbol === symbol ? lookup.data.name : axios.isAxiosError(lookup.error) && lookup.error.response?.status === 404 ? '未找到标的' : '验证暂不可用'
          const statusClass = lookup.data?.symbol === symbol ? 'found' : lookup.isError && debouncedSymbols[index] === symbol ? 'unavailable' : ''
          return <div className="component-row" key={component.rowId}>
            <input aria-label={`成分 ${index + 1} 标的`} value={component.symbol} onChange={(event) => update(index, { symbol: event.target.value.toUpperCase() })} placeholder="例如 AAPL"/>
            <span className={`component-symbol-name ${statusClass}`} title={nameStatus} role="status">{nameStatus}</span>
            <div className="component-weight"><input aria-label={`成分 ${index + 1} 权重`} type="number" min="0.01" max="100" step="0.01" value={component.weight_percent} onChange={(event) => update(index, { weight_percent: Number(event.target.value) })}/><span>%</span></div>
            <button className="danger-ghost" type="button" disabled={components.length === 1} onClick={() => setComponents((items) => items.filter((_, position) => position !== index))}>移除</button>
          </div>
        })}
      </div>
      <div className="custom-index-actions"><button className="secondary" type="button" disabled={components.length >= 20} onClick={() => setComponents((items) => [...items, { rowId: newRowId(), symbol: '', weight_percent: 0 }])}>添加标的</button><span className={Math.abs(total - 100) <= .01 ? 'success' : 'error'}>权重合计 {total.toFixed(2)}%</span><button type="submit" disabled={!valid || save.isPending}>{save.isPending ? '保存中…' : config.data ? '保存新版本' : '创建自定义指数'}</button></div>
      {duplicate && <p className="error">标的代码不能重复。</p>}
      {save.isSuccess && <p className="success">自定义指数已保存；新标的将在下一轮行情采集中自动加入。</p>}
      {save.isError && <p className="error">{axios.isAxiosError(save.error) && typeof save.error.response?.data?.detail === 'string' ? save.error.response.data.detail : '保存失败，请稍后重试。'}</p>}
    </form>
  </section>
}
