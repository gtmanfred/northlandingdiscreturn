import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { AuthProvider, useAuth } from './AuthContext'

function makeJwt(expOffsetSeconds: number): string {
  const exp = Math.floor(Date.now() / 1000) + expOffsetSeconds
  const payload = btoa(JSON.stringify({ sub: 'u1', exp }))
  return `h.${payload}.s`
}

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
)

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('startup: no stored token', () => {
  it('attempts silent refresh, stays unauthenticated when it fails', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.isInitializing).toBe(true)
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.token).toBeNull()
  })
})

describe('startup: valid token in localStorage', () => {
  it('skips refresh and sets authenticated immediately', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const jwt = makeJwt(3600)
    localStorage.setItem('auth_token', jwt)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.token).toBe(jwt)
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('startup: expired token in localStorage', () => {
  it('silently refreshes and updates the token', async () => {
    localStorage.setItem('auth_token', makeJwt(-3600))
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ token: 'fresh-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    expect(result.current.token).toBe('fresh-token')
    expect(result.current.isAuthenticated).toBe(true)
    expect(localStorage.getItem('auth_token')).toBe('fresh-token')
  })

  it('clears stale token and stays unauthenticated when refresh fails', async () => {
    localStorage.setItem('auth_token', makeJwt(-3600))
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    expect(result.current.token).toBeNull()
    expect(localStorage.getItem('auth_token')).toBeNull()
  })
})

describe('login', () => {
  it('stores token in state and localStorage', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    act(() => result.current.login('my-token'))
    expect(result.current.token).toBe('my-token')
    expect(result.current.isAuthenticated).toBe(true)
    expect(localStorage.getItem('auth_token')).toBe('my-token')
  })
})

describe('logout', () => {
  it('clears token from state and localStorage', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    act(() => result.current.login('my-token'))
    act(() => result.current.logout())
    expect(result.current.token).toBeNull()
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('calls POST /auth/logout with credentials', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitializing).toBe(false))
    act(() => result.current.login('my-token'))

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ message: 'logged out' }), { status: 200 }),
    )
    act(() => result.current.logout())

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/auth/logout'),
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
  })
})
