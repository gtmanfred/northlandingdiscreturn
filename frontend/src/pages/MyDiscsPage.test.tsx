import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { MyDiscsPage } from './MyDiscsPage'

vi.mock('../api/northlanding', () => ({
  useGetMyDiscs: vi.fn(),
  useGetMe: vi.fn(),
}))

import { useGetMyDiscs, useGetMe } from '../api/northlanding'

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}

describe('MyDiscsPage', () => {
  beforeAll(() => {
    // jsdom lacks these; Radix Select needs them to open and select options.
    Element.prototype.hasPointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    // Default: a verified phone number, so the register prompt stays hidden.
    vi.mocked(useGetMe).mockReturnValue({
      isLoading: false,
      data: { phone_numbers: [{ id: 'p1', number: '+15551234567', verified: true }] },
    } as any)
  })

  it('shows loading state', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: true, data: undefined } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('shows disc details when data loads', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({
      isLoading: false,
      data: [{ id: '1', manufacturer: 'Innova', name: 'Destroyer', colors: ['Red'], is_returned: false, photos: [] }],
    } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.getByText('Destroyer')).toBeInTheDocument()
    expect(screen.getByText('Innova')).toBeInTheDocument()
  })

  it('shows empty message when no discs and a verified phone is linked', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: [] } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.getByText(/no discs found/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /profile/i })).not.toBeInTheDocument()
  })

  it('prompts to register a phone when no discs and no verified phone', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: [] } as any)
    vi.mocked(useGetMe).mockReturnValue({
      isLoading: false,
      data: { phone_numbers: [] },
    } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.getByText(/add a phone number/i)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /profile/i })
    expect(link).toHaveAttribute('href', '/my/profile')
  })

  it('prompts to register when the only phone is unverified', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: [] } as any)
    vi.mocked(useGetMe).mockReturnValue({
      isLoading: false,
      data: { phone_numbers: [{ id: 'p1', number: '+15551234567', verified: false }] },
    } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.getByText(/add a phone number/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /profile/i })).toBeInTheDocument()
  })

  it('shows loading while the profile is still loading', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: [] } as any)
    vi.mocked(useGetMe).mockReturnValue({ isLoading: true, data: undefined } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  const twoDiscs = [
    { id: '1', manufacturer: 'Innova', name: 'Destroyer', colors: ['Red'], is_returned: false, photos: [] },
    { id: '2', manufacturer: 'Discraft', name: 'Buzzz', colors: ['Blue'], is_returned: true, photos: [] },
  ]

  it('defaults to showing only discs awaiting pickup', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: twoDiscs } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.getByText('Destroyer')).toBeInTheDocument()
    expect(screen.queryByText('Buzzz')).not.toBeInTheDocument()
  })

  it('shows only returned discs when the Returned filter is selected', async () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: twoDiscs } as any)
    render(<MyDiscsPage />, { wrapper })
    await userEvent.click(screen.getByRole('combobox', { name: /show/i }))
    await userEvent.click(screen.getByRole('option', { name: 'Returned' }))
    expect(screen.getByText('Buzzz')).toBeInTheDocument()
    expect(screen.queryByText('Destroyer')).not.toBeInTheDocument()
  })

  it('shows all discs when the All filter is selected', async () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: twoDiscs } as any)
    render(<MyDiscsPage />, { wrapper })
    await userEvent.click(screen.getByRole('combobox', { name: /show/i }))
    await userEvent.click(screen.getByRole('option', { name: 'All' }))
    expect(screen.getByText('Buzzz')).toBeInTheDocument()
    expect(screen.getByText('Destroyer')).toBeInTheDocument()
  })

  it('shows a no-match message when the filter hides every disc', async () => {
    const onlyReturned = [
      { id: '2', manufacturer: 'Discraft', name: 'Buzzz', colors: ['Blue'], is_returned: true, photos: [] },
    ]
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: onlyReturned } as any)
    render(<MyDiscsPage />, { wrapper })
    // Default 'awaiting' filter hides the only (returned) disc.
    expect(screen.getByText(/no discs match this filter/i)).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /show/i })).toBeInTheDocument()
  })

  it('does not render the filter when there are zero discs', () => {
    vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: [] } as any)
    render(<MyDiscsPage />, { wrapper })
    expect(screen.queryByRole('combobox', { name: /show/i })).not.toBeInTheDocument()
  })
})
