import axios, { AxiosRequestConfig } from 'axios'
import { AUTH_TOKEN_KEY } from '../auth/AuthContext'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const axiosInstance = axios.create({
  baseURL: API_URL,
  withCredentials: true,
})

axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

function forceLogout(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY)
  window.location.href = '/'
}

axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status !== 401) {
      return Promise.reject(error)
    }

    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }

    if (originalRequest.url === '/auth/refresh' || originalRequest._retry) {
      forceLogout()
      return Promise.reject(error)
    }

    originalRequest._retry = true

    try {
      const { data } = await axiosInstance.post<{ token: string }>('/auth/refresh')
      localStorage.setItem(AUTH_TOKEN_KEY, data.token)
      if (originalRequest.headers) {
        originalRequest.headers.Authorization = `Bearer ${data.token}`
      }
      return axiosInstance(originalRequest)
    } catch {
      forceLogout()
      return Promise.reject(error)
    }
  },
)

export const customInstance = <T>(config: AxiosRequestConfig): Promise<T> =>
  axiosInstance(config).then(({ data }) => data as T)

export type ErrorType<Error> = Error
