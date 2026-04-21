import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { AdminDiscsPage } from './AdminDiscsPage'

vi.mock('../api/northlanding', () => ({
  useListDiscs: vi.fn(() => ({
    data: { items: [], total: 0, page: 1, page_size: 25 },
    isLoading: false,
  })),
  useDeleteDisc: vi.fn(() => ({ mutateAsync: vi.fn() })),
  useUpdateDisc: vi.fn(() => ({ mutateAsync: vi.fn() })),
  getListDiscsQueryKey: vi.fn(() => ['/discs']),
}))

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

test('renders filter bar with Found, Returned selects and Owner name input', () => {
  render(<AdminDiscsPage />, { wrapper })
  expect(screen.getByRole('combobox', { name: /found/i })).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: /returned/i })).toBeInTheDocument()
  expect(screen.getByPlaceholderText(/owner name/i)).toBeInTheDocument()
})
