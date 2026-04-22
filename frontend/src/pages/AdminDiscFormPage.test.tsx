import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('../api/northlanding', () => ({
  useCreateDisc: () => ({ mutateAsync: vi.fn().mockResolvedValue({ id: 'new-disc-id' }), isPending: false }),
  useUpdateDisc: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUploadDiscPhoto: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useListDiscs: () => ({ data: undefined, isLoading: false }),
  useGetSuggestions: () => ({ data: [] }),
  useGetPhoneSuggestions: () => ({ data: [] }),
  getListDiscsQueryKey: () => ['listDiscs'],
  getGetSuggestionsQueryKey: () => ['getSuggestions'],
}))

import { AdminDiscFormPage } from './AdminDiscFormPage'

function renderCreateForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/discs/new']}>
        <Routes>
          <Route path="/admin/discs/new" element={<AdminDiscFormPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

it('shows Save and Add Another button in create mode', () => {
  renderCreateForm()
  expect(screen.getByRole('button', { name: 'Save and Add Another' })).toBeInTheDocument()
})

it('shows Create button in create mode', () => {
  renderCreateForm()
  expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument()
})

it('shows Add Photos button in create mode', () => {
  renderCreateForm()
  expect(screen.getByRole('button', { name: /add photos/i })).toBeInTheDocument()
})
