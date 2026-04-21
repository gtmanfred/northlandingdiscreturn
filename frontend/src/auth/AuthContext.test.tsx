import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import React from 'react'
import { AuthProvider, useAuth } from './AuthContext'

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
)

beforeEach(() => localStorage.clear())

describe('AuthContext', () => {
  it('starts with null token', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.token).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
  })

  it('stores token in localStorage on login', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    act(() => result.current.login('test-jwt-token'))
    expect(result.current.token).toBe('test-jwt-token')
    expect(localStorage.getItem('auth_token')).toBe('test-jwt-token')
    expect(result.current.isAuthenticated).toBe(true)
  })

  it('clears token on logout', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    act(() => result.current.login('test-jwt-token'))
    act(() => result.current.logout())
    expect(result.current.token).toBeNull()
    expect(localStorage.getItem('auth_token')).toBeNull()
  })
})
