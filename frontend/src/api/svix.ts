import { api } from './client'
import type { Components, SVIXPoint } from '../types'

export const getCurrentSVIX = async () => (await api.get<SVIXPoint>('/svix/current')).data
export const getHistory = async (startDate: string, endDate: string, frequency: 'daily' | 'weekly' = 'daily') => (await api.get<SVIXPoint[]>('/svix/history', { params: { start_date: startDate, end_date: endDate, frequency } })).data
export const getComponents = async () => (await api.get<Components>('/svix/components')).data
