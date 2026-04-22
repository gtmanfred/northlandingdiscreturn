import React, { createContext, useContext, useEffect, useState } from 'react'
import { API_URL } from '../api/client'

export const AUTH_TOKEN_KEY = 'auth_token'

interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  isInitializing: boolean
  login: (token: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1])) as { exp?: number }
    return payload.exp === undefined || Date.now() >= payload.exp * 1000
  } catch {
    return true
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem(AUTH_TOKEN_KEY),
  )
  const [isInitializing, setIsInitializing] = useState(true)

  useEffect(() => {
    const stored = localStorage.getItem(AUTH_TOKEN_KEY)
    if (stored && !isTokenExpired(stored)) {
      setIsInitializing(false)
      return
    }

    fetch(`${API_URL}/auth/refresh`, { method: 'POST', credentials: 'include' })
      .then((res) => {
        if (res.ok) return res.json() as Promise<{ token: string }>
        throw new Error('refresh failed')
      })
      .then(({ token: newToken }) => {
        localStorage.setItem(AUTH_TOKEN_KEY, newToken)
        setToken(newToken)
      })
      .catch(() => {
        localStorage.removeItem(AUTH_TOKEN_KEY)
        setToken(null)
      })
      .finally(() => setIsInitializing(false))
  }, [])

  const login = (t: string) => {
    localStorage.setItem(AUTH_TOKEN_KEY, t)
    setToken(t)
  }

  const logout = () => {
    fetch(`${API_URL}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {})
    localStorage.removeItem(AUTH_TOKEN_KEY)
    setToken(null)
  }

  return (
    <AuthContext.Provider value={{ token, isAuthenticated: !!token, isInitializing, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
