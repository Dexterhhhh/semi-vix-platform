import axios, { type InternalAxiosRequestConfig } from 'axios'

let accessToken: string | null = null
let onUnauthorized: (() => void) | null = null
let refreshHandler: (() => Promise<string | null>) | null = null
let refreshInFlight: Promise<string | null> | null = null

type RetryConfig = InternalAxiosRequestConfig & { _svixRetry?: boolean }

export const setAccessToken = (token: string | null) => { accessToken = token }
export const setUnauthorizedHandler = (handler: () => void) => { onUnauthorized = handler }
export const setRefreshHandler = (handler: () => Promise<string | null>) => { refreshHandler = handler }

export const api = axios.create({ baseURL: '/api', withCredentials: true })
api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})
api.interceptors.response.use((response) => response, async (error) => {
  const config = error.config as RetryConfig | undefined
  if (error.response?.status === 401 && config && !config.url?.startsWith('/auth/') && !config._svixRetry && refreshHandler) {
    config._svixRetry = true
    if (!refreshInFlight) refreshInFlight = refreshHandler().finally(() => { refreshInFlight = null })
    const refreshedToken = await refreshInFlight
    if (refreshedToken) {
      config.headers.Authorization = `Bearer ${refreshedToken}`
      return api.request(config)
    }
  }
  if (error.response?.status === 401) onUnauthorized?.()
  return Promise.reject(error)
})
