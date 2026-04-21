import axios, { AxiosRequestConfig } from 'axios'
import { AUTH_TOKEN_KEY } from '../auth/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const axiosInstance = axios.create({ baseURL: API_URL })

axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export const customInstance = <T>(config: AxiosRequestConfig): Promise<T> =>
  axiosInstance(config).then(({ data }) => data as T)

export type ErrorType<Error> = Error
