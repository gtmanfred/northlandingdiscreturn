import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { AdminDiscsPage } from './AdminDiscsPage'
import { useListDiscs } from '../api/northlanding'

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

const DISC_ID = '11111111-2222-3333-4444-555555555555'

function mockOneDisc() {
  vi.mocked(useListDiscs).mockReturnValue({
    data: {
      items: [
        {
          id: DISC_ID,
          name: 'Destroyer',
          manufacturer: 'Innova',
          colors: ['red'],
          notes: null,
          is_found: true,
          is_returned: false,
          photos: [],
          owner: null,
        },
      ],
      total: 1,
      page: 1,
      page_size: 25,
    },
    isLoading: false,
  } as unknown as ReturnType<typeof useListDiscs>)
}

test('desktop table has an ID column showing the full disc id', () => {
  mockOneDisc()
  render(<AdminDiscsPage />, { wrapper })
  expect(screen.getByRole('columnheader', { name: /^id$/i })).toBeInTheDocument()
  // full uuid present in the DOM so admins can copy it to match the spreadsheet
  expect(screen.getAllByText(DISC_ID).length).toBeGreaterThan(0)
})

test('mobile card shows the disc id', () => {
  mockOneDisc()
  render(<AdminDiscsPage />, { wrapper })
  expect(screen.getAllByTitle(DISC_ID).length).toBeGreaterThan(0)
})
