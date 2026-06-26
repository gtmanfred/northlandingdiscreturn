import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MyProfilePage } from './MyProfilePage'

vi.mock('../api/northlanding', () => ({
  useGetMe: vi.fn(),
  useAddPhone: vi.fn(),
  useVerifyPhone: vi.fn(),
  useRemovePhone: vi.fn(),
  getGetMeQueryKey: () => ['/users/me'],
}))

// ApiKeyCard pulls in more hooks; stub it so this test stays focused on phones.
vi.mock('../components/ApiKeyCard', () => ({ ApiKeyCard: () => null }))

import {
  useGetMe,
  useAddPhone,
  useVerifyPhone,
  useRemovePhone,
} from '../api/northlanding'

const addMutate = vi.fn()

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
}

beforeEach(() => {
  addMutate.mockReset().mockResolvedValue({})
  vi.mocked(useAddPhone).mockReturnValue({ mutateAsync: addMutate, isPending: false } as any)
  vi.mocked(useVerifyPhone).mockReturnValue({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false } as any)
  vi.mocked(useRemovePhone).mockReturnValue({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false } as any)
  vi.mocked(useGetMe).mockReturnValue({
    isLoading: false,
    data: { name: 'Jane', email: 'jane@example.com', phone_numbers: [] },
  } as any)
})

describe('MyProfilePage', () => {
  it('renders an inline verify row for an unverified number from the server', () => {
    vi.mocked(useGetMe).mockReturnValue({
      isLoading: false,
      data: {
        name: 'Jane',
        email: 'jane@example.com',
        phone_numbers: [{ id: 'p1', number: '+15551234567', verified: false }],
      },
    } as any)
    render(<MyProfilePage />, { wrapper })
    expect(screen.getByText('+15551234567')).toBeInTheDocument()
    expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /resend code/i })).toBeInTheDocument()
  })

  it('a verified number has no code field', () => {
    vi.mocked(useGetMe).mockReturnValue({
      isLoading: false,
      data: {
        name: 'Jane',
        email: 'jane@example.com',
        phone_numbers: [{ id: 'p1', number: '+15551234567', verified: true }],
      },
    } as any)
    render(<MyProfilePage />, { wrapper })
    expect(screen.getByText('Verified')).toBeInTheDocument()
    expect(screen.queryByLabelText(/verification code/i)).not.toBeInTheDocument()
  })

  it('add-new-number form submits the normalized number', async () => {
    const user = userEvent.setup()
    render(<MyProfilePage />, { wrapper })
    await user.type(screen.getByLabelText(/area code/i), '555')
    await user.type(screen.getByLabelText(/exchange/i), '123')
    await user.type(screen.getByLabelText(/line number/i), '4567')
    await user.click(screen.getByRole('button', { name: /add phone/i }))
    expect(addMutate).toHaveBeenCalledWith({ data: { number: '+15551234567' } })
  })
})
