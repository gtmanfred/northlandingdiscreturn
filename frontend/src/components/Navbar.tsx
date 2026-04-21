import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useGetMe } from '../api/northlanding'

export function Navbar() {
  const { isAuthenticated, logout } = useAuth()
  const { data: user } = useGetMe({ query: { enabled: isAuthenticated } })
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  return (
    <nav className="bg-green-800 text-white px-6 py-3 flex items-center justify-between">
      <Link to="/" className="font-bold text-lg">North Landing Discs</Link>

      {isAuthenticated && (
        <div className="flex items-center gap-6 text-sm">
          <Link to="/my/discs" className="hover:underline">My Discs</Link>
          <Link to="/my/wishlist" className="hover:underline">Wishlist</Link>
          <Link to="/my/profile" className="hover:underline">Profile</Link>
          {user?.is_admin && (
            <>
              <Link to="/admin/discs" className="hover:underline">Admin: Discs</Link>
              <Link to="/admin/pickup-events" className="hover:underline">Pickup Events</Link>
              <Link to="/admin/users" className="hover:underline">Users</Link>
            </>
          )}
          <button onClick={handleLogout} className="hover:underline">
            Logout ({user?.name ?? '…'})
          </button>
        </div>
      )}
    </nav>
  )
}
