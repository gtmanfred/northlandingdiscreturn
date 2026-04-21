import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetMyWishlist,
  useAddWishlistDisc,
  useRemoveWishlistDisc,
  useGetSuggestions,
  useGetMe,
  getGetMyWishlistQueryKey,
} from '../api/northlanding'
import { AutocompleteInput } from '../components/AutocompleteInput'
import { LoadingSpinner } from '../components/LoadingSpinner'

export function MyWishlistPage() {
  const queryClient = useQueryClient()
  const { data: user, isLoading: userLoading } = useGetMe()
  const { data: discs, isLoading: discsLoading } = useGetMyWishlist()
  const addMutation = useAddWishlistDisc()
  const removeMutation = useRemoveWishlistDisc()
  const { data: manufacturerSuggestions = [] } = useGetSuggestions({ field: 'manufacturer' })
  const { data: nameSuggestions = [] } = useGetSuggestions({ field: 'name' })
  const { data: colorSuggestions = [] } = useGetSuggestions({ field: 'color' })

  const verifiedNumbers = user?.phone_numbers?.filter((p) => p.verified) ?? []

  const [form, setForm] = useState({ manufacturer: '', name: '', color: '' })
  const [selectedPhone, setSelectedPhone] = useState<string>('')

  const phoneNumber = selectedPhone || verifiedNumbers[0]?.number || ''

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    await addMutation.mutateAsync({
      data: {
        ...form,
        phone_number: phoneNumber,
        owner_name: user?.name ?? undefined,
      },
    })
    queryClient.invalidateQueries({ queryKey: getGetMyWishlistQueryKey() })
    setForm({ manufacturer: '', name: '', color: '' })
  }

  const handleRemove = async (discId: string) => {
    await removeMutation.mutateAsync({ discId })
    queryClient.invalidateQueries({ queryKey: getGetMyWishlistQueryKey() })
  }

  if (userLoading || discsLoading) return <LoadingSpinner />

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6 text-green-800">My Wishlist</h1>
      <p className="text-sm text-gray-600 mb-6">
        Log discs you lost at North Landing so staff can match them if found.
      </p>

      {verifiedNumbers.length === 0 ? (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-8 text-yellow-800 text-sm">
          Add and verify a phone number in your account settings before adding discs to your wishlist.
        </div>
      ) : (
        <form onSubmit={handleAdd} className="bg-white border border-gray-200 rounded-lg p-4 mb-8 flex gap-3 flex-wrap">
          <AutocompleteInput
            containerClassName="flex-1 min-w-32"
            className="w-full border border-gray-300 rounded px-3 py-2"
            placeholder="Manufacturer"
            value={form.manufacturer}
            suggestions={manufacturerSuggestions.map((v) => ({ value: v }))}
            onValueChange={(v) => setForm((f) => ({ ...f, manufacturer: v }))}
          />
          <AutocompleteInput
            containerClassName="flex-1 min-w-32"
            className="w-full border border-gray-300 rounded px-3 py-2"
            placeholder="Disc name"
            value={form.name}
            suggestions={nameSuggestions.map((v) => ({ value: v }))}
            onValueChange={(v) => setForm((f) => ({ ...f, name: v }))}
          />
          <AutocompleteInput
            containerClassName="flex-1 min-w-24"
            className="w-full border border-gray-300 rounded px-3 py-2"
            placeholder="Color"
            value={form.color}
            suggestions={colorSuggestions.map((v) => ({ value: v }))}
            onValueChange={(v) => setForm((f) => ({ ...f, color: v }))}
          />
          {verifiedNumbers.length > 1 ? (
            <select
              value={phoneNumber}
              onChange={(e) => setSelectedPhone(e.target.value)}
              className="border border-gray-300 rounded px-3 py-2 bg-white"
              aria-label="Phone number"
            >
              {verifiedNumbers.map((p) => (
                <option key={p.id} value={p.number}>{p.number}</option>
              ))}
            </select>
          ) : (
            <span className="flex items-center px-3 py-2 text-sm text-gray-500 border border-gray-200 rounded bg-gray-50">
              {verifiedNumbers[0].number}
            </span>
          )}
          <button
            type="submit"
            disabled={addMutation.isPending}
            className="bg-green-700 text-white px-4 py-2 rounded hover:bg-green-800 disabled:opacity-50"
          >
            Add
          </button>
        </form>
      )}

      {!discs?.length ? (
        <p className="text-gray-500">Your wishlist is empty.</p>
      ) : (
        <ul className="space-y-2">
          {discs.map((disc) => (
            <li key={disc.id} className="bg-white border border-gray-200 rounded-lg p-3 flex items-center justify-between">
              <span>
                <span className="font-medium">{disc.name}</span>
                {disc.manufacturer && <span className="text-gray-500 ml-2 text-sm">{disc.manufacturer}</span>}
                {disc.color && <span className="text-gray-400 ml-2 text-sm">· {disc.color}</span>}
              </span>
              <button
                onClick={() => handleRemove(disc.id)}
                disabled={removeMutation.isPending}
                className="text-red-500 hover:text-red-700 text-sm disabled:opacity-50"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
