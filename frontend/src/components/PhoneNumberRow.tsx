import { useState } from 'react'
import { useVerifyPhone, useAddPhone } from '../api/northlanding'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface PhoneNumberRowProps {
  number: string
  verified: boolean
  onRemove: (number: string) => void
  onVerified: () => void
}

type Message = { type: 'error' | 'success'; text: string } | null

export function PhoneNumberRow({ number, verified, onRemove, onVerified }: PhoneNumberRowProps) {
  const verifyPhone = useVerifyPhone()
  const addPhone = useAddPhone()
  const [code, setCode] = useState('')
  const [message, setMessage] = useState<Message>(null)

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setMessage(null)
    try {
      await verifyPhone.mutateAsync({ data: { number, code } })
      setCode('')
      onVerified()
    } catch {
      setMessage({ type: 'error', text: 'Invalid or expired verification code.' })
    }
  }

  const handleResend = async () => {
    setMessage(null)
    try {
      await addPhone.mutateAsync({ data: { number } })
      setMessage({ type: 'success', text: 'New code sent.' })
    } catch {
      setMessage({ type: 'error', text: 'Failed to send code.' })
    }
  }

  return (
    <div className="rounded-md border border-border px-3 py-2">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">{number}</p>
          {verified ? (
            <p className="text-xs text-green-700">Verified</p>
          ) : (
            <p className="text-xs text-yellow-700">Unverified</p>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="text-destructive hover:text-destructive"
          onClick={() => onRemove(number)}
        >
          Remove
        </Button>
      </div>

      {!verified && (
        <form onSubmit={handleVerify} className="mt-3 space-y-2">
          <div className="flex gap-2">
            <Input
              type="text"
              inputMode="numeric"
              placeholder="123456"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              aria-label={`Verification code for ${number}`}
            />
            <Button type="submit" disabled={code.length !== 6 || verifyPhone.isPending}>
              Verify
            </Button>
            <Button type="button" variant="outline" onClick={handleResend} disabled={addPhone.isPending}>
              Resend code
            </Button>
          </div>
          {message &&
            (message.type === 'error' ? (
              <Alert variant="destructive">
                <AlertDescription>{message.text}</AlertDescription>
              </Alert>
            ) : (
              <p role="status" className="text-xs text-green-700">{message.text}</p>
            ))}
        </form>
      )}
    </div>
  )
}
