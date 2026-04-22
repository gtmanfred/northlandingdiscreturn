import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MyDiscsPage } from './MyDiscsPage'

vi.mock('../api/northlanding', () => ({
  useGetMyDiscs: vi.fn(),
}))

import { useGetMyDiscs } from '../api/northlanding'

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      {children}
    </QueryClientProvider>
  )
}

describe('MyDiscsPage', () => {
  it('shows loading state', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: true, data: undefined } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('shows disc details when data loads', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({
      isLoading: false,
      data: [{ id: '1', manufacturer: 'Innova', name: 'Destroyer', color: 'Red', is_returned: false, photos: [] }],
    } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.getByText('Destroyer')).toBeInTheDocument()
    expect(screen.getByText('Innova')).toBeInTheDocument()
  })

  it('shows empty message when no discs', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({
      isLoading: false,
      data: [],
    } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.getByText(/no discs/i)).toBeInTheDocument()
  })
})
