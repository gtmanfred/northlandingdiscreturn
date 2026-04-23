import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetMe,
  useAddPhone,
  useVerifyPhone,
  useRemovePhone,
  getGetMeQueryKey,
} from '../api/northlanding'
import { PageHeader } from '../components/PageHeader'
import { LoadingState } from '../components/LoadingState'
import { PhoneInput } from '../components/PhoneInput'
import { normalizePhone } from '../utils/phone'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'

type Step = 'idle' | 'code-sent'

export function MyProfilePage() {
  const queryClient = useQueryClient()
  const { data: user, isLoading } = useGetMe()
  const addPhone = useAddPhone()
  const verifyPhone = useVerifyPhone()
  const removePhone = useRemovePhone()
  const [newNumber, setNewNumber] = useState('')
  const [pendingNumber, setPendingNumber] = useState('')
  const [code, setCode] = useState('')
  const [step, setStep] = useState<Step>('idle')
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
      setPendingNumber(normalized)
      setNewNumber('')
      setStep('code-sent')
    } catch {
      setError('Failed to send verification code.')
    }
  }

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      await verifyPhone.mutateAsync({ data: { number: pendingNumber, code } })
      setStep('idle')
      setCode('')
      setPendingNumber('')
      refresh()
    } catch {
      setError('Invalid or expired verification code.')
    }
  }

  const handleRemove = async (number: string) => {
    await removePhone.mutateAsync({ number })
    refresh()
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
              <div
                key={p.id}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2"
              >
                <div>
                  <p className="text-sm font-medium">{p.number}</p>
                  {p.verified ? (
                    <p className="text-xs text-green-700">Verified</p>
                  ) : (
                    <p className="text-xs text-yellow-700">Unverified</p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={() => handleRemove(p.number)}
                >
                  Remove
                </Button>
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">No phone numbers linked yet.</p>
          )}

          <div className="pt-4">
            {step === 'idle' ? (
              <form onSubmit={handleAddPhone} className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="phone-new">Add a phone number</Label>
                  <PhoneInput value={newNumber} onChange={setNewNumber} />
                </div>
                <Button type="submit" disabled={addPhone.isPending}>
                  Add phone
                </Button>
              </form>
            ) : (
              <form onSubmit={handleVerify} className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Enter the 6-digit code sent to {pendingNumber}:
                </p>
                <div className="flex gap-2">
                  <Input
                    type="text"
                    inputMode="numeric"
                    placeholder="123456"
                    maxLength={6}
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                  />
                  <Button type="submit" disabled={verifyPhone.isPending}>
                    Verify
                  </Button>
                </div>
              </form>
            )}
            {error && (
              <Alert variant="destructive" className="mt-3">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
