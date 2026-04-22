import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true, logout: vi.fn() }),
}))
vi.mock('../api/northlanding', () => ({
  useGetMe: () => ({ data: { name: 'Alice', is_admin: false } }),
}))

import { Navbar } from './Navbar'

function renderNavbar() {
  render(
    <MemoryRouter>
      <Navbar />
    </MemoryRouter>
  )
}

it('shows hamburger button for authenticated users', () => {
  renderNavbar()
  expect(screen.getByRole('button', { name: 'Open menu' })).toBeInTheDocument()
})

it('drawer is not shown by default', () => {
  renderNavbar()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('drawer opens when hamburger is clicked', async () => {
  const user = userEvent.setup()
  renderNavbar()
  await user.click(screen.getByRole('button', { name: 'Open menu' }))
  expect(screen.getByRole('dialog', { name: 'Navigation menu' })).toBeInTheDocument()
})

it('drawer closes when close button is clicked', async () => {
  const user = userEvent.setup()
  renderNavbar()
  await user.click(screen.getByRole('button', { name: 'Open menu' }))
  await user.click(screen.getByRole('button', { name: 'Close menu' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('drawer contains nav links', async () => {
  const user = userEvent.setup()
  renderNavbar()
  await user.click(screen.getByRole('button', { name: 'Open menu' }))
  const dialog = screen.getByRole('dialog', { name: 'Navigation menu' })
  expect(dialog).toHaveTextContent('My Discs')
  expect(dialog).toHaveTextContent('Wishlist')
  expect(dialog).toHaveTextContent('Profile')
})
