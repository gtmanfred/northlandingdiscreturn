import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetMe,
  useAddPhone,
  useRemovePhone,
  getGetMeQueryKey,
} from '../api/northlanding'
import { PageHeader } from '../components/PageHeader'
import { LoadingState } from '../components/LoadingState'
import { PhoneInput } from '../components/PhoneInput'
import { PhoneNumberRow } from '../components/PhoneNumberRow'
import { ApiKeyCard } from '../components/ApiKeyCard'
import { normalizePhone } from '../utils/phone'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'

export function MyProfilePage() {
  const queryClient = useQueryClient()
  const { data: user, isLoading } = useGetMe()
  const addPhone = useAddPhone()
  const removePhone = useRemovePhone()
  const [newNumber, setNewNumber] = useState('')
  const [error, setError] = useState('')

  const refresh = () => queryClient.invalidateQueries({ queryKey: getGetMeQueryKey() })

  const handleAddPhone = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    let normalized: string
    try {
      normalized = normalizePhone(newNumber)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid phone number.')
      return
    }
    try {
      await addPhone.mutateAsync({ data: { number: normalized } })
      setNewNumber('')
      refresh()
    } catch {
      setError('Failed to send verification code.')
    }
  }

  const handleRemove = async (number: string) => {
    setError('')
    try {
      await removePhone.mutateAsync({ number })
      refresh()
    } catch {
      setError('Failed to remove phone number.')
    }
  }

  if (isLoading) return <LoadingState />

  return (
    <div className="max-w-xl">
      <PageHeader title="My Profile" />

      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-medium text-foreground">{user?.name}</p>
              <p className="text-sm text-muted-foreground">{user?.email}</p>
            </div>
            {user?.is_admin && (
              <Badge className="border-transparent bg-blue-100 text-blue-800 hover:bg-blue-100">
                Admin
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Linked Phone Numbers</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {user?.phone_numbers?.length ? (
            user.phone_numbers.map((p) => (
              <PhoneNumberRow
                key={p.id}
                number={p.number}
                verified={p.verified}
                onRemove={handleRemove}
                onVerified={refresh}
              />
            ))
          ) : (
            <p className="text-sm text-muted-foreground">No phone numbers linked yet.</p>
          )}

          <div className="pt-4">
            <form onSubmit={handleAddPhone} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="phone-new">Add a phone number</Label>
                <PhoneInput value={newNumber} onChange={setNewNumber} />
              </div>
              <Button type="submit" disabled={addPhone.isPending}>
                Add phone
              </Button>
            </form>
            {error && (
              <Alert variant="destructive" className="mt-3">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
        </CardContent>
      </Card>

      <ApiKeyCard />
    </div>
  )
}
