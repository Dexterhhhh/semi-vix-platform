export type ProviderName = 'IBKR' | 'FUTU'

export type ProviderStatus = { provider: ProviderName | null; connected: boolean }
export type ProviderCredentials = { api_key?: string; secret?: string; account_identifier?: string }

export async function providerStatus(accessToken: string): Promise<ProviderStatus> {
  const response = await fetch('/api/provider/status', { headers: { Authorization: `Bearer ${accessToken}` }, credentials: 'include' })
  if (!response.ok) throw new Error('无法读取行情提供商状态')
  return response.json()
}

export async function configureProvider(accessToken: string, provider: ProviderName, credentials: ProviderCredentials): Promise<{ provider: ProviderName; enabled: boolean }> {
  const response = await fetch('/api/provider/configure', { method: 'POST', headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ provider, credentials }) })
  if (!response.ok) throw new Error('无法保存行情提供商配置')
  return response.json()
}
