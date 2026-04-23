import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { useGetMe } from '../api/northlanding'
import { LoadingState } from '../components/LoadingState'

interface Props {
  requireAdmin?: boolean
}

export function ProtectedRoute({ requireAdmin = false }: Props) {
  const { isAuthenticated, isInitializing } = useAuth()
  const location = useLocation()

  if (isInitializing) return <LoadingState />

  if (!isAuthenticated) {
    return <Navigate to="/" state={{ from: location }} replace />
  }

  if (requireAdmin) {
    return <AdminGuard />
  }

  return <Outlet />
}

function AdminGuard() {
  const { data: user, isLoading, isError } = useGetMe()

  if (isLoading) return <LoadingState />
  if (isError) return <Navigate to="/" replace />
  if (!user?.is_admin) return <Navigate to="/my/discs" replace />

  return <Outlet />
}
