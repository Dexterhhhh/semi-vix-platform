import axios from 'axios'
import { api } from './client'

export type LoginState = { mfa_required?: boolean; mfa_setup_required?: boolean; temporary_token: string }
export const login = async (username: string, password: string) => (await api.post<LoginState>('/auth/login', { username, password })).data
export const beginMfaSetup = async (temporary_token: string) => (await api.post<{ provisioning_uri: string }>('/auth/setup-mfa', { temporary_token })).data
export const finishMfaSetup = async (temporary_token: string, totp_code: string) => (await api.post<{ access_token: string }>('/auth/setup-mfa', { temporary_token, totp_code })).data
export const verifyMfa = async (temporary_token: string, totp_code: string) => (await api.post<{ access_token: string }>('/auth/verify-mfa', { temporary_token, totp_code })).data

const sessionApi = axios.create({ baseURL: '/api', withCredentials: true })
export const refreshSession = async () => (await sessionApi.post<{ access_token: string; expires_in: number }>('/auth/refresh')).data
export const logoutSession = async () => { await sessionApi.post('/auth/logout') }
