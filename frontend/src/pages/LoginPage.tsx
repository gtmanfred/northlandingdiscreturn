import { useAuth } from '../auth/AuthContext'
import { Navigate } from 'react-router-dom'
import { Disc3 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function LoginPage() {
  const { isAuthenticated } = useAuth()

  if (isAuthenticated) return <Navigate to="/my/discs" replace />

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <Disc3 className="mb-2 h-10 w-10 text-primary" aria-hidden="true" />
          <CardTitle className="text-2xl">North Landing Disc Return</CardTitle>
          <CardDescription>Lost your disc? Log in to see if we found it.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="outline" className="w-full gap-2">
            <a href={`${API_URL}/auth/google`}>
              <img src="https://www.google.com/favicon.ico" alt="" className="h-4 w-4" />
              Sign in with Google
            </a>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
