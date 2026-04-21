import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { Layout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { AuthCallbackPage } from './pages/AuthCallbackPage'
import { MyDiscsPage } from './pages/MyDiscsPage'
import { MyWishlistPage } from './pages/MyWishlistPage'
import { MyProfilePage } from './pages/MyProfilePage'
import { AdminDiscsPage } from './pages/AdminDiscsPage'
import { AdminDiscFormPage } from './pages/AdminDiscFormPage'
import { AdminPickupEventsPage } from './pages/AdminPickupEventsPage'
import { AdminUsersPage } from './pages/AdminUsersPage'

const router = createBrowserRouter(
  [
    {
      element: <AuthProvider><Layout /></AuthProvider>,
      children: [
        { path: '/', element: <LoginPage /> },
        { path: '/auth/callback', element: <AuthCallbackPage /> },
        {
          element: <ProtectedRoute />,
          children: [
            { path: '/my/discs', element: <MyDiscsPage /> },
            { path: '/my/wishlist', element: <MyWishlistPage /> },
            { path: '/my/profile', element: <MyProfilePage /> },
          ],
        },
        {
          element: <ProtectedRoute requireAdmin />,
          children: [
            { path: '/admin/discs', element: <AdminDiscsPage /> },
            { path: '/admin/discs/new', element: <AdminDiscFormPage /> },
            { path: '/admin/discs/:discId/edit', element: <AdminDiscFormPage /> },
            { path: '/admin/pickup-events', element: <AdminPickupEventsPage /> },
            { path: '/admin/users', element: <AdminUsersPage /> },
          ],
        },
      ],
    },
  ],
  { basename: import.meta.env.BASE_URL },
)

export default function App() {
  return <RouterProvider router={router} />
}
