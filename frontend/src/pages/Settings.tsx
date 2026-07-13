import { FormEvent, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { configureProvider, getProviderConfiguration, getProviderStatus, testProviderConnection, type AlpacaFeed, type ProviderCredentials, type ProviderName } from '../api/provider'
import { getLifecycleStatus, getSettings, getSystemStatus, runLifecycleMaintenance, saveSettings } from '../api/settings'
import type { DashboardSettings } from '../types'
import '../provider.css'
import { CustomIndexEditor } from '../components/CustomIndexEditor'

const symbols = ['SOXX', 'MU', 'SKHY', 'NVDA', 'AMD', 'AVGO']

export function Settings() {
  const client = useQueryClient()
  const settingsQuery = useQuery({ queryKey: ['settings'], queryFn: getSettings })
  const system = useQuery({ queryKey: ['system-status'], queryFn: getSystemStatus, refetchInterval: 10000 })
  const lifecycle = useQuery({ queryKey: ['lifecycle-status'], queryFn: getLifecycleStatus, refetchInterval: 15000 })
  const providerStatus = useQuery({ queryKey: ['provider-status'], queryFn: getProviderStatus, retry: false })
  const [selectedProvider, setSelectedProvider] = useState<ProviderName>('IBKR')
  const configuration = useQuery({ queryKey: ['provider-configuration', selectedProvider], queryFn: () => getProviderConfiguration(selectedProvider) })
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [clientId, setClientId] = useState('19')
  const [apiKey, setApiKey] = useState('')
  const [secret, setSecret] = useState('')
  const [accountIdentifier, setAccountIdentifier] = useState('')
  const [alpacaFeed, setAlpacaFeed] = useState<AlpacaFeed>('indicative')

  useEffect(() => {
    if (providerStatus.data?.provider) setSelectedProvider(providerStatus.data.provider)
  }, [providerStatus.data?.provider])

  useEffect(() => {
    if (!configuration.data) return
    setHost(configuration.data.host)
    setPort(String(configuration.data.port))
    setClientId(String(configuration.data.client_id ?? 19))
    setApiKey('')
    setSecret('')
    setAccountIdentifier('')
    setAlpacaFeed(configuration.data.data_feed ?? 'indicative')
  }, [configuration.data])

  const saveSettingsMutation = useMutation({ mutationFn: saveSettings, onSuccess: () => client.invalidateQueries({ queryKey: ['settings'] }) })
  const saveProvider = useMutation({
    mutationFn: configureProvider,
    onSuccess: async () => {
      setApiKey(''); setSecret(''); setAccountIdentifier('')
      await Promise.all([
        client.invalidateQueries({ queryKey: ['provider-status'] }),
        client.invalidateQueries({ queryKey: ['provider-configuration', selectedProvider] }),
        client.invalidateQueries({ queryKey: ['system-status'] }),
      ])
    },
  })
  const testConnection = useMutation({ mutationFn: testProviderConnection, onSuccess: (status) => client.setQueryData(['provider-status'], status) })
  const runMaintenance = useMutation({ mutationFn: runLifecycleMaintenance, onSuccess: () => client.invalidateQueries({ queryKey: ['lifecycle-status'] }) })
  const settings = settingsQuery.data
  const updateLifecycle = (values: Partial<DashboardSettings>) => settings && saveSettingsMutation.mutate({ ...settings, ...values })
  const formatSize = (bytes: number | null) => bytes === null ? '—' : `${(bytes / 1024 / 1024).toFixed(1)} MB`
  const toggle = (symbol: string) => settings && saveSettingsMutation.mutate({ ...settings, selected_symbols: settings.selected_symbols.includes(symbol) ? settings.selected_symbols.filter((item) => item !== symbol) : [...settings.selected_symbols, symbol] })

  const submitProvider = (event: FormEvent) => {
    event.preventDefault()
    const credentials: ProviderCredentials = {}
    if (apiKey) credentials.api_key = apiKey
    if (secret) credentials.secret = secret
    if (accountIdentifier) credentials.account_identifier = accountIdentifier
    saveProvider.mutate({ provider: selectedProvider, host: host.trim(), port: selectedProvider === 'ALPACA' ? 443 : Number(port), ...(selectedProvider === 'IBKR' ? { client_id: Number(clientId) } : {}), ...(selectedProvider === 'ALPACA' ? { data_feed: alpacaFeed } : {}), credentials })
  }

  const currentStatus = providerStatus.data
  const connectionResult = testConnection.data
  return <main>
    <header><div><p className="eyebrow">CONFIGURATION</p><h1>设置与系统状态</h1></div></header>
    <section className="panel provider-panel">
      <div className="panel-title"><div><h3>数据提供商</h3><p>连接参数和可选凭据由服务器保存；凭据使用 AES-256-GCM 加密且不会回显。</p></div><span className={`connection-badge ${currentStatus?.connected ? 'online' : ''}`}>{currentStatus?.connected ? '已连接' : currentStatus?.configured ? '已配置' : '未配置'}</span></div>
      <form className="provider-form" onSubmit={submitProvider}>
        <label>提供商<select value={selectedProvider} onChange={(event) => setSelectedProvider(event.target.value as ProviderName)}><option value="IBKR">Interactive Brokers</option><option value="FUTU">Futu OpenD</option><option value="ALPACA">Alpaca Market Data</option></select></label>
        <label>{selectedProvider === 'IBKR' ? 'TWS / Gateway Host' : selectedProvider === 'FUTU' ? 'OpenD Host' : 'API Base URL（固定官方地址）'}<input required readOnly={selectedProvider === 'ALPACA'} value={host} onChange={(event) => setHost(event.target.value)} placeholder={selectedProvider === 'ALPACA' ? 'https://data.alpaca.markets' : 'host.docker.internal'} /></label>
        {selectedProvider !== 'ALPACA' && <label>端口<input required type="number" min="1" max="65535" value={port} onChange={(event) => setPort(event.target.value)} /></label>}
        {selectedProvider === 'IBKR' && <label>Client ID<input required type="number" min="0" value={clientId} onChange={(event) => setClientId(event.target.value)} /></label>}
        {selectedProvider === 'ALPACA' && <label>期权数据源<select value={alpacaFeed} onChange={(event) => setAlpacaFeed(event.target.value as AlpacaFeed)}><option value="indicative">Indicative（免费测试）</option><option value="opra">OPRA（付费正式）</option></select></label>}
        <div className="credential-grid">
          <label>API Key{selectedProvider === 'ALPACA' ? '（必填）' : '（可选）'}<input type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={configuration.data?.credentials_present ? '已保存；留空保持不变' : '未设置'} /></label>
          <label>API Secret{selectedProvider === 'ALPACA' ? '（必填）' : '（可选）'}<input type="password" autoComplete="off" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder={configuration.data?.credentials_present ? '已保存；留空保持不变' : '未设置'} /></label>
          {selectedProvider !== 'ALPACA' && <label>账户标识（可选）<input type="password" autoComplete="off" value={accountIdentifier} onChange={(event) => setAccountIdentifier(event.target.value)} placeholder={configuration.data?.credentials_present ? '已保存；留空保持不变' : '未设置'} /></label>}
        </div>
        {selectedProvider === 'ALPACA' && alpacaFeed === 'indicative' && <p className="provider-warning">免费 Indicative 的 bid/ask 是经过修改的数据。系统允许计算 SVIX，但会降低质量分；历史计算使用期权日线收盘价代理历史 BBO。</p>}
        {selectedProvider === 'ALPACA' && alpacaFeed === 'opra' && <p className="success">OPRA 为正式实时行情，需要 Alpaca 有效的付费市场数据订阅。</p>}
        <div className="form-actions"><button disabled={saveProvider.isPending || !host || !port} type="submit">{saveProvider.isPending ? '保存中…' : '保存并启用'}</button><button className="secondary" disabled={testConnection.isPending || !currentStatus?.configured} type="button" onClick={() => testConnection.mutate()}>{testConnection.isPending ? '测试中…' : '测试连接'}</button></div>
        {saveProvider.isSuccess && <p className="success">配置已加密保存并启用。</p>}
        {saveProvider.isError && <p className="error">保存失败，请检查 Host、端口和凭据格式。</p>}
        {connectionResult && <p className={connectionResult.connected ? (connectionResult.production_ready ? 'success' : 'provider-warning') : 'error'}>{connectionResult.connected ? `连接测试成功。${connectionResult.warning ?? ''}` : `连接失败：${connectionResult.error ?? '服务不可用'}`}</p>}
      </form>
    </section>
    <section className="panel form"><h3>计算设置</h3><label>历史/常规刷新频率<select value={settings?.refresh_frequency_minutes ?? 15} onChange={(event) => settings && saveSettingsMutation.mutate({ ...settings, refresh_frequency_minutes: Number(event.target.value) })}><option value="5">5 分钟</option><option value="15">15 分钟</option><option value="30">30 分钟</option><option value="1440">每日</option></select></label><label>日内独立计算频率<select value={settings?.intraday_refresh_seconds ?? 300} onChange={(event) => settings && saveSettingsMutation.mutate({ ...settings, intraday_refresh_seconds: Number(event.target.value) })}><option value="30">每 30 秒</option><option value="60">每 60 秒</option><option value="120">每 2 分钟</option><option value="300">每 5 分钟</option><option value="900">每 15 分钟</option></select><small>仅在 NYSE 交易窗口内生效；免费源最低建议30秒</small></label><p>标的范围</p><div className="symbols">{symbols.map((symbol) => <label key={symbol}><input type="checkbox" checked={settings?.selected_symbols.includes(symbol) ?? false} onChange={() => toggle(symbol)}/> {symbol}</label>)}</div></section>
    <CustomIndexEditor/>
    <section className="panel lifecycle-panel">
      <div className="panel-title"><div><h3>数据生命周期</h3><p>先完成每日聚合，再分批清理已有成功计算覆盖的原始期权数据。</p></div><button className="secondary" disabled={runMaintenance.isPending} onClick={() => runMaintenance.mutate()}>{runMaintenance.isPending ? '已加入队列…' : '立即维护'}</button></div>
      <div className="lifecycle-grid">
        <label><span><input type="checkbox" checked={settings?.option_cleanup_enabled ?? true} onChange={(event) => updateLifecycle({ option_cleanup_enabled: event.target.checked })}/> 自动清理期权快照</span><small>仅删除已有计算结果的日期</small></label>
        <label>原始期权保留天数<input type="number" min="1" max="30" value={settings?.option_retention_days ?? 3} onChange={(event) => updateLifecycle({ option_retention_days: Number(event.target.value) })}/></label>
        <label><span><input type="checkbox" checked={settings?.svix_downsample_enabled ?? true} onChange={(event) => updateLifecycle({ svix_downsample_enabled: event.target.checked })}/> 自动降采样</span><small>长期保存每日 OHLC</small></label>
        <label>详细结果保留天数<input type="number" min="1" max="365" value={settings?.detailed_retention_days ?? 7} onChange={(event) => updateLifecycle({ detailed_retention_days: Number(event.target.value) })}/></label>
        <label>每日维护时间（UTC）<input type="time" value={settings?.maintenance_time_utc ?? '03:30'} onChange={(event) => updateLifecycle({ maintenance_time_utc: event.target.value })}/></label>
      </div>
      {lifecycle.data && <div className="storage-grid"><div><span>期权快照</span><strong>{lifecycle.data.option_snapshot_rows.toLocaleString()} 行</strong><small>{formatSize(lifecycle.data.option_snapshot_bytes)}</small></div><div><span>详细 SVIX</span><strong>{lifecycle.data.svix_history_rows.toLocaleString()} 行</strong><small>{formatSize(lifecycle.data.svix_history_bytes)}</small></div><div><span>每日 SVIX</span><strong>{lifecycle.data.svix_daily_rows.toLocaleString()} 行</strong><small>{formatSize(lifecycle.data.svix_daily_bytes)}</small></div></div>}
      {lifecycle.data?.last_run && <p>最近维护：{lifecycle.data.last_run.status} · 删除期权 {lifecycle.data.last_run.option_rows_deleted} 行 · 聚合详细结果 {lifecycle.data.last_run.history_rows_aggregated} 行</p>}
      {runMaintenance.isSuccess && <p className="success">维护任务已加入后台队列。</p>}
    </section>
    <section className="panel"><h3>系统状态</h3>{system.data && Object.entries(system.data).map(([key, value]) => <div className="status-row" key={key}><span>{key}</span><strong>{value ? String(value) : '—'}</strong></div>)}</section>
  </main>
}
