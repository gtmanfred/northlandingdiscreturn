import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetMyWishlist,
  useAddWishlistDisc,
  useRemoveWishlistDisc,
  getGetMyWishlistQueryKey,
} from '../api/northlanding'
import { LoadingSpinner } from '../components/LoadingSpinner'

export function MyWishlistPage() {
  const queryClient = useQueryClient()
  const { data: discs, isLoading } = useGetMyWishlist()
  const addMutation = useAddWishlistDisc()
  const removeMutation = useRemoveWishlistDisc()
  const [form, setForm] = useState({ manufacturer: '', name: '', color: '' })

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    await addMutation.mutateAsync({ data: form })
    queryClient.invalidateQueries({ queryKey: getGetMyWishlistQueryKey() })
    setForm({ manufacturer: '', name: '', color: '' })
  }

  const handleRemove = async (discId: string) => {
    await removeMutation.mutateAsync({ discId })
    queryClient.invalidateQueries({ queryKey: getGetMyWishlistQueryKey() })
  }

  if (isLoading) return <LoadingSpinner />

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6 text-green-800">My Wishlist</h1>
      <p className="text-sm text-gray-600 mb-6">
        Log discs you lost at North Landing so staff can match them if found.
      </p>

      <form onSubmit={handleAdd} className="bg-white border border-gray-200 rounded-lg p-4 mb-8 flex gap-3 flex-wrap">
        <input
          className="border border-gray-300 rounded px-3 py-2 flex-1 min-w-32"
          placeholder="Manufacturer"
          value={form.manufacturer}
          onChange={(e) => setForm((f) => ({ ...f, manufacturer: e.target.value }))}
        />
        <input
          className="border border-gray-300 rounded px-3 py-2 flex-1 min-w-32"
          placeholder="Disc name"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
        />
        <input
          className="border border-gray-300 rounded px-3 py-2 flex-1 min-w-24"
          placeholder="Color"
          value={form.color}
          onChange={(e) => setForm((f) => ({ ...f, color: e.target.value }))}
        />
        <button
          type="submit"
          disabled={addMutation.isPending}
          className="bg-green-700 text-white px-4 py-2 rounded hover:bg-green-800 disabled:opacity-50"
        >
          Add
        </button>
      </form>

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
