import { api } from './client'
import type { DashboardSettings, LifecycleStatus, SystemStatus } from '../types'

export const getSettings = async () => (await api.get<DashboardSettings>('/settings')).data
export const saveSettings = async (payload: DashboardSettings) => (await api.put<DashboardSettings>('/settings', payload)).data
export const getSystemStatus = async () => (await api.get<SystemStatus>('/settings/system-status')).data
export const getLifecycleStatus = async () => (await api.get<LifecycleStatus>('/settings/data-lifecycle/status')).data
export const runLifecycleMaintenance = async () => (await api.post<{ status: string }>('/settings/data-lifecycle/run')).data
