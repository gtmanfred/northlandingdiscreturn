import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetMe,
  useAddPhone,
  useVerifyPhone,
  useRemovePhone,
  getGetMeQueryKey,
} from '../api/northlanding'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { normalizePhone } from '../utils/phone'

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

  if (isLoading) return <LoadingSpinner />

  return (
    <div className="max-w-md">
      <h1 className="text-2xl font-bold mb-6 text-green-800">My Profile</h1>

      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
        <p className="font-medium">{user?.name}</p>
        <p className="text-gray-500 text-sm">{user?.email}</p>
        {user?.is_admin && <span className="inline-block mt-1 px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">Admin</span>}
      </div>

      <h2 className="text-lg font-semibold mb-3">Linked Phone Numbers</h2>

      {user?.phone_numbers?.map((p) => (
        <div key={p.id} className="flex items-center justify-between py-2 border-b border-gray-100">
          <span>{p.number} {p.verified ? '✓' : <span className="text-yellow-600 text-xs">(unverified)</span>}</span>
          <button
            onClick={() => handleRemove(p.number)}
            className="text-red-500 text-sm hover:text-red-700"
          >
            Remove
          </button>
        </div>
      ))}

      <div className="mt-6">
        {step === 'idle' ? (
          <form onSubmit={handleAddPhone} className="flex flex-col gap-2">
            <div className="flex gap-2">
              <input
                type="tel"
                placeholder="(555) 123-4567"
                value={newNumber}
                onChange={(e) => setNewNumber(e.target.value)}
                className="border border-gray-300 rounded px-3 py-2 flex-1"
              />
              <button
                type="submit"
                disabled={addPhone.isPending}
                className="bg-green-700 text-white px-4 py-2 rounded hover:bg-green-800 disabled:opacity-50"
              >
                Add Phone
              </button>
            </div>
            <p className="text-xs text-gray-400">US numbers only — any format accepted.</p>
          </form>
        ) : (
          <form onSubmit={handleVerify} className="flex flex-col gap-2">
            <p className="text-sm text-gray-600">
              Enter the 6-digit code sent to {pendingNumber}:
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="123456"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="border border-gray-300 rounded px-3 py-2 flex-1"
              />
              <button
                type="submit"
                disabled={verifyPhone.isPending}
                className="bg-green-700 text-white px-4 py-2 rounded hover:bg-green-800 disabled:opacity-50"
              >
                Verify
              </button>
            </div>
          </form>
        )}
        {error && <p className="mt-2 text-red-600 text-sm">{error}</p>}
      </div>
    </div>
  )
}
