import { api } from './client'
import type { CustomIndexConfig, CustomIndexPayload, CustomIndexPoint } from '../types'

export const getCustomIndex = async () => (await api.get<CustomIndexConfig | null>('/custom-index')).data
export const saveCustomIndex = async (payload: CustomIndexPayload) => (await api.put<CustomIndexConfig>('/custom-index', payload)).data
export const getCurrentCustomIndex = async () => (await api.get<CustomIndexPoint>('/custom-index/current')).data
export const getCustomIndexHistory = async (startDate: string, endDate: string) => (await api.get<CustomIndexPoint[]>('/custom-index/history', { params: { start_date: startDate, end_date: endDate } })).data
export const getCustomIndexIntraday = async (sessionDate?: string) => (await api.get<CustomIndexPoint[]>('/custom-index/intraday', { params: sessionDate ? { session_date: sessionDate } : {} })).data
