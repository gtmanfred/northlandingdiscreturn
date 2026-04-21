import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useListDiscs, useDeleteDisc, getListDiscsQueryKey } from '../api/northlanding'
import { LoadingSpinner } from '../components/LoadingSpinner'

export function AdminDiscsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const pageSize = 25

  const { data, isLoading } = useListDiscs({ page, page_size: pageSize })
  const deleteMutation = useDeleteDisc()
  const [error, setError] = useState('')

  const handleDelete = async (discId: string, name: string) => {
    if (!confirm(`Delete ${name}?`)) return
    setError('')
    try {
      await deleteMutation.mutateAsync({ discId })
      queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
    } catch {
      setError(`Failed to delete ${name}.`)
    }
  }

  const discs = data?.items ?? []
  const totalPages = data ? Math.ceil(data.total / pageSize) : 1

  if (isLoading) return <LoadingSpinner />

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-green-800">Discs</h1>
        <Link
          to="/admin/discs/new"
          className="bg-green-700 text-white px-4 py-2 rounded hover:bg-green-800"
        >
          + Add Disc
        </Link>
      </div>

      <input
        type="search"
        placeholder="Filter by name, manufacturer…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="border border-gray-300 rounded px-3 py-2 mb-4 w-full max-w-sm"
      />
      {error && <p className="text-red-600 text-sm mb-2">{error}</p>}

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-100 text-left">
              <th className="px-3 py-2 border border-gray-200">Photo</th>
              <th className="px-3 py-2 border border-gray-200">Disc</th>
              <th className="px-3 py-2 border border-gray-200">Color</th>
              <th className="px-3 py-2 border border-gray-200">Phone</th>
              <th className="px-3 py-2 border border-gray-200">Owner</th>
              <th className="px-3 py-2 border border-gray-200">Status</th>
              <th className="px-3 py-2 border border-gray-200">Actions</th>
            </tr>
          </thead>
          <tbody>
            {discs
              .filter((d) =>
                !search ||
                d.name.toLowerCase().includes(search.toLowerCase()) ||
                d.manufacturer.toLowerCase().includes(search.toLowerCase()),
              )
              .map((disc) => (
                <tr key={disc.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2 border border-gray-200">
                    {disc.photos?.[0] ? (
                      <img src={disc.photos[0].photo_path} alt="" className="w-10 h-10 object-cover rounded" />
                    ) : (
                      <div className="w-10 h-10 bg-gray-200 rounded flex items-center justify-center text-gray-400 text-xs">No photo</div>
                    )}
                  </td>
                  <td className="px-3 py-2 border border-gray-200">
                    <span className="font-medium">{disc.name}</span>
                    <br />
                    <span className="text-gray-500">{disc.manufacturer}</span>
                  </td>
                  <td className="px-3 py-2 border border-gray-200">{disc.color}</td>
                  <td className="px-3 py-2 border border-gray-200">{disc.phone_number ?? '—'}</td>
                  <td className="px-3 py-2 border border-gray-200">{disc.owner_name ?? '—'}</td>
                  <td className="px-3 py-2 border border-gray-200">
                    {disc.is_returned ? (
                      <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs">Returned</span>
                    ) : disc.final_notice_sent ? (
                      <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs">Final notice</span>
                    ) : (
                      <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded text-xs">Holding</span>
                    )}
                  </td>
                  <td className="px-3 py-2 border border-gray-200 whitespace-nowrap">
                    <Link
                      to={`/admin/discs/${disc.id}/edit`}
                      className="text-blue-600 hover:underline mr-3"
                    >
                      Edit
                    </Link>
                    <button
                      onClick={() => handleDelete(disc.id, disc.name)}
                      className="text-red-500 hover:text-red-700"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex gap-2 mt-4 items-center">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 border rounded disabled:opacity-50"
          >
            ←
          </button>
          <span className="text-sm text-gray-600">Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1 border rounded disabled:opacity-50"
          >
            →
          </button>
        </div>
      )}
    </div>
  )
}
