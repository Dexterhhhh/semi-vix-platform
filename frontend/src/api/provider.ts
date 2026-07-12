import { api } from './client'

export type ProviderName = 'IBKR' | 'FUTU'
export type ProviderStatus = { provider: ProviderName; configured: boolean; connected: boolean; last_checked_at: string | null; error: string | null }
export type ProviderCredentials = { api_key?: string; secret?: string; account_identifier?: string }
export type ProviderConfiguration = { provider: ProviderName; configured: boolean; host: string; port: number; client_id: number | null; credentials_present: boolean }
export type ProviderConfigurationInput = { provider: ProviderName; host: string; port: number; client_id?: number; credentials?: ProviderCredentials }

export const getProviderStatus = async () => (await api.get<ProviderStatus>('/provider/status')).data
export const getProviderConfiguration = async (provider: ProviderName) => (await api.get<ProviderConfiguration>('/provider/configuration', { params: { provider } })).data
export const configureProvider = async (configuration: ProviderConfigurationInput) => (await api.post<{ provider: ProviderName; enabled: boolean }>('/provider/configure', configuration)).data
export const testProviderConnection = async () => (await api.post<ProviderStatus>('/provider/test-connection')).data
