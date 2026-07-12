import { api } from './client'
import type { CalculationJob } from '../types'

export const createJob = async (payload: { start_date: string; end_date: string; frequency: 'daily' | 'weekly' }) => (await api.post<CalculationJob>('/jobs/create', payload)).data
export const getJobs = async () => (await api.get<CalculationJob[]>('/jobs')).data
