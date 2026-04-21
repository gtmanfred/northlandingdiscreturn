import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { LoadingSpinner } from '../components/LoadingSpinner'

export function AuthCallbackPage() {
  const [params] = useSearchParams()
  const { login } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    const token = params.get('token')
    if (token) {
      login(token)
      navigate('/my/discs', { replace: true })
    } else {
      navigate('/', { replace: true })
    }
  }, [])

  return <LoadingSpinner />
}
