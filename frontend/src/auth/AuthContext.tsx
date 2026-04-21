import React, { createContext, useContext, useState } from 'react'

interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  login: (token: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem('auth_token'),
  )

  const login = (t: string) => {
    localStorage.setItem('auth_token', t)
    setToken(t)
  }

  const logout = () => {
    localStorage.removeItem('auth_token')
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
