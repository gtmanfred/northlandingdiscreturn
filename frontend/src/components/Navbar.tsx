import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useGetMe } from '../api/northlanding'

export function Navbar() {
  const { isAuthenticated, logout } = useAuth()
  const { data: user } = useGetMe({ query: { enabled: isAuthenticated } })
  const navigate = useNavigate()
  const [drawerOpen, setDrawerOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/')
    setDrawerOpen(false)
  }

  const close = () => setDrawerOpen(false)

  const navLinks = isAuthenticated ? (
    <>
      <Link to="/my/discs" onClick={close} className="hover:underline block">My Discs</Link>
      <Link to="/my/wishlist" onClick={close} className="hover:underline block">Wishlist</Link>
      <Link to="/my/profile" onClick={close} className="hover:underline block">Profile</Link>
      {user?.is_admin && (
        <>
          <Link to="/admin/discs" onClick={close} className="hover:underline block">Admin: Discs</Link>
          <Link to="/admin/pickup-events" onClick={close} className="hover:underline block">Pickup Events</Link>
          <Link to="/admin/users" onClick={close} className="hover:underline block">Users</Link>
        </>
      )}
      <button onClick={handleLogout} className="hover:underline text-left block">
        Logout ({user?.name ?? '…'})
      </button>
    </>
  ) : null

  return (
    <>
      <nav className="bg-green-800 text-white px-6 py-3 flex items-center justify-between">
        <Link to="/" className="font-bold text-lg">North Landing Discs</Link>

        {isAuthenticated && (
          <>
            {/* Desktop nav */}
            <div className="hidden md:flex items-center gap-6 text-sm">
              {navLinks}
            </div>

            {/* Mobile hamburger */}
            <button
              className="md:hidden text-white text-2xl leading-none"
              aria-label="Open menu"
              onClick={() => setDrawerOpen(true)}
            >
              ☰
            </button>
          </>
        )}
      </nav>

      {drawerOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40 bg-black/40"
            onClick={close}
            aria-hidden="true"
          />

          {/* Drawer */}
          <div
            role="dialog"
            aria-label="Navigation menu"
            aria-modal="true"
            className="fixed top-0 right-0 h-full w-64 bg-green-800 text-white z-50 flex flex-col p-6 gap-5 text-sm"
          >
            <button
              className="self-end text-2xl leading-none"
              aria-label="Close menu"
              onClick={close}
            >
              ✕
            </button>
            {navLinks}
          </div>
        </>
      )}
    </>
  )
}
