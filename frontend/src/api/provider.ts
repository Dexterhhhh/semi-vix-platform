import { api } from './client'

export type ProviderName = 'IBKR' | 'FUTU'
export type ProviderStatus = { provider: ProviderName; configured: boolean; connected: boolean; last_checked_at: string | null; error: string | null }
export type ProviderCredentials = { api_key?: string; secret?: string; account_identifier?: string }

export const getProviderStatus = async () => (await api.get<ProviderStatus>('/provider/status')).data
export const configureProvider = async (provider: ProviderName, credentials: ProviderCredentials = {}) => (await api.post<{ provider: ProviderName; enabled: boolean }>('/provider/configure', { provider, credentials })).data
