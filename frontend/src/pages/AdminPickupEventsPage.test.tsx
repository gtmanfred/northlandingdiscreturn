import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AdminPickupEventsPage } from './AdminPickupEventsPage'

vi.mock('../api/northlanding', () => {
  const events = [
    {
      id: 'e1',
      start_at: '2026-05-01T20:00:00.000Z',
      end_at: '2026-05-01T22:00:00.000Z',
      notes: null,
      notifications_sent_at: null,
      sequence: 0,
      created_at: '2026-04-20T12:00:00.000Z',
    },
  ]
  const create = vi.fn(async () => ({}))
  return {
    useAdminListPickupEvents: () => ({ data: events, isLoading: false }),
    useAdminCreatePickupEvent: () => ({ mutateAsync: create, isPending: false }),
    useAdminUpdatePickupEvent: () => ({ mutateAsync: vi.fn(async () => ({})), isPending: false }),
    useAdminNotifyPickupEvent: () => ({ mutateAsync: vi.fn(async () => ({})), isPending: false }),
    getAdminListPickupEventsQueryKey: () => ['pickup-events'],
    __createSpy: create,
  }
})

function renderPage() {
  const qc = new QueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <AdminPickupEventsPage />
    </QueryClientProvider>,
  )
}

describe('AdminPickupEventsPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders the existing event window in course-local time', () => {
    renderPage()
    expect(screen.getByText(/May 1, 2026/)).toBeInTheDocument()
    expect(screen.getByText(/4:00/)).toBeInTheDocument()
    expect(screen.getByText(/6:00/)).toBeInTheDocument()
  })

  it('posts ISO UTC start/end when submitting', async () => {
    const api = await import('../api/northlanding')
    renderPage()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText(/Date/i), '2026-06-15')
    // leave defaults 16:00 / 18:00
    await user.click(screen.getByRole('button', { name: /Create event/i }))

    await waitFor(() => expect((api as any).__createSpy).toHaveBeenCalled())
    const body = (api as any).__createSpy.mock.calls[0][0].data
    expect(body.start_at).toBe('2026-06-15T20:00:00.000Z')
    expect(body.end_at).toBe('2026-06-15T22:00:00.000Z')
  })

  it('shows the subscribe feed URL', () => {
    renderPage()
    expect(screen.getByText(/pickup-events\.ics/)).toBeInTheDocument()
  })
})
