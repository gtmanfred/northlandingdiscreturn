import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { Navigate } from 'react-router-dom'
import { Disc3, CalendarDays, Check } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function LoginPage() {
  const { isAuthenticated } = useAuth()
  const [copied, setCopied] = useState(false)

  if (isAuthenticated) return <Navigate to="/my/discs" replace />

  const feedUrl = `${API_URL}/pickup-events.ics`
  const handleSubscribe = async () => {
    try {
      await navigator.clipboard.writeText(feedUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      window.open(feedUrl, '_blank')
    }
  }

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <Disc3 className="mb-2 h-10 w-10 text-primary" aria-hidden="true" />
          <CardTitle className="text-2xl">North Landing Disc Return</CardTitle>
          <CardDescription>Lost your disc? Log in to see if we found it.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Button asChild variant="outline" className="w-full gap-2">
            <a href={`${API_URL}/auth/google`}>
              <img src="https://www.google.com/favicon.ico" alt="" className="h-4 w-4" />
              Sign in with Google
            </a>
          </Button>
          <Button variant="ghost" className="w-full gap-2 text-sm" onClick={handleSubscribe}>
            {copied ? <Check className="h-4 w-4" /> : <CalendarDays className="h-4 w-4" />}
            {copied ? 'Link copied — paste into your calendar app' : 'Subscribe to pickup calendar'}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
