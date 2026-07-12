import axios from 'axios'

let accessToken: string | null = null
let onUnauthorized: (() => void) | null = null

export const setAccessToken = (token: string | null) => { accessToken = token }
export const setUnauthorizedHandler = (handler: () => void) => { onUnauthorized = handler }

export const api = axios.create({ baseURL: '/api', withCredentials: true })
api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})
api.interceptors.response.use((response) => response, (error) => {
  if (error.response?.status === 401) onUnauthorized?.()
  return Promise.reject(error)
})
