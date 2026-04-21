import { useAuth } from '../auth/AuthContext'
import { Navigate } from 'react-router-dom'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function LoginPage() {
  const { isAuthenticated } = useAuth()

  if (isAuthenticated) return <Navigate to="/my/discs" replace />

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-green-800 mb-2">North Landing Disc Return</h1>
        <p className="text-gray-600">Lost your disc? Log in to see if we found it.</p>
      </div>
      <a
        href={`${API_URL}/auth/google`}
        className="bg-white border border-gray-300 rounded-lg px-6 py-3 flex items-center gap-3 shadow hover:shadow-md transition-shadow font-medium"
      >
        <img src="https://www.google.com/favicon.ico" alt="" className="w-5 h-5" />
        Sign in with Google
      </a>
    </div>
  )
}
