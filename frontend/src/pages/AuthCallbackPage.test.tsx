import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthCallbackPage } from './AuthCallbackPage'
import { AuthProvider } from '../auth/AuthContext'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

function renderCallback(search: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[`/auth/callback${search}`]}>
        <Routes>
          <Route path="/auth/callback" element={<AuthCallbackPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
}

beforeEach(() => {
  localStorage.clear()
  mockNavigate.mockClear()
})

describe('AuthCallbackPage', () => {
  it('stores token and redirects to /my/discs', () => {
    renderCallback('?token=my-test-jwt')
    expect(localStorage.getItem('auth_token')).toBe('my-test-jwt')
    expect(mockNavigate).toHaveBeenCalledWith('/my/discs', { replace: true })
  })

  it('redirects to / when no token in URL', () => {
    renderCallback('')
    expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
  })
})
