import { api } from './client'
import type { DashboardSettings, SystemStatus } from '../types'

export const getSettings = async () => (await api.get<DashboardSettings>('/settings')).data
export const saveSettings = async (payload: DashboardSettings) => (await api.put<DashboardSettings>('/settings', payload)).data
export const getSystemStatus = async () => (await api.get<SystemStatus>('/settings/system-status')).data
