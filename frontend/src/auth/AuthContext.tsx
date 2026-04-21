import React, { createContext, useContext, useState } from 'react'

export const AUTH_TOKEN_KEY = 'auth_token'

interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  login: (token: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem(AUTH_TOKEN_KEY),
  )

  const login = (t: string) => {
    localStorage.setItem(AUTH_TOKEN_KEY, t)
    setToken(t)
  }

  const logout = () => {
    localStorage.removeItem(AUTH_TOKEN_KEY)
    setToken(null)
  }

  return (
    <AuthContext.Provider value={{ token, isAuthenticated: !!token, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
