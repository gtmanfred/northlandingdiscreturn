import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  useListDiscs,
  useDeleteDisc,
  useUpdateDisc,
  getListDiscsQueryKey,
} from '../api/northlanding'
import { LoadingSpinner } from '../components/LoadingSpinner'

export function AdminDiscsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')

  // Filter state
  const [isFoundFilter, setIsFoundFilter] = useState<boolean | undefined>(undefined)
  const [isReturnedFilter, setIsReturnedFilter] = useState<boolean | undefined>(undefined)
  const [ownerNameInput, setOwnerNameInput] = useState('')
  const [ownerNameFilter, setOwnerNameFilter] = useState<string | undefined>(undefined)

  const pageSize = 25

  // Debounce owner name 300ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setOwnerNameFilter(ownerNameInput || undefined)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [ownerNameInput])

  const { data, isLoading } = useListDiscs({
    page,
    page_size: pageSize,
    is_found: isFoundFilter,      // undefined → omitted from URL query string
    is_returned: isReturnedFilter,
    owner_name: ownerNameFilter,
  })
  const deleteMutation = useDeleteDisc()
  const updateMutation = useUpdateDisc()
  const [error, setError] = useState('')

  const handleFilterChange = (setter: (v: boolean | undefined) => void) => (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value
    setter(val === '' ? undefined : val === 'true')
    setPage(1)
  }

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

  const handleToggleIsFound = async (discId: string, current: boolean) => {
    try {
      await updateMutation.mutateAsync({ discId, data: { is_found: !current } })
      queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
    } catch {
      setError('Failed to update disc.')
    }
  }

  const handleToggleIsReturned = async (discId: string, current: boolean) => {
    try {
      await updateMutation.mutateAsync({ discId, data: { is_returned: !current } })
      queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
    } catch {
      setError('Failed to update disc.')
    }
  }

  const discs = data?.items ?? []
  const totalPages = data ? Math.ceil(data.total / pageSize) : 1

  if (isLoading) return <LoadingSpinner />

  const filteredDiscs = discs.filter((d) =>
    !search ||
    d.name.toLowerCase().includes(search.toLowerCase()) ||
    d.manufacturer.toLowerCase().includes(search.toLowerCase()),
  )

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

      {/* Filter bar */}
      <div className="flex flex-wrap gap-3 mb-4 items-end">
        <div>
          <label htmlFor="filter-found" className="block text-xs text-gray-500 mb-1">Found</label>
          <select
            id="filter-found"
            aria-label="Found"
            value={isFoundFilter === undefined ? '' : String(isFoundFilter)}
            onChange={handleFilterChange(setIsFoundFilter)}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm"
          >
            <option value="">All</option>
            <option value="true">Found</option>
            <option value="false">Not found</option>
          </select>
        </div>
        <div>
          <label htmlFor="filter-returned" className="block text-xs text-gray-500 mb-1">Returned</label>
          <select
            id="filter-returned"
            aria-label="Returned"
            value={isReturnedFilter === undefined ? '' : String(isReturnedFilter)}
            onChange={handleFilterChange(setIsReturnedFilter)}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm"
          >
            <option value="">All</option>
            <option value="true">Returned</option>
            <option value="false">Not returned</option>
          </select>
        </div>
        <div>
          <label htmlFor="filter-owner" className="block text-xs text-gray-500 mb-1">Owner name</label>
          <input
            id="filter-owner"
            type="text"
            placeholder="Owner name…"
            value={ownerNameInput}
            onChange={(e) => setOwnerNameInput(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm w-48"
          />
        </div>
        <div>
          <label htmlFor="filter-search" className="block text-xs text-gray-500 mb-1">Name / manufacturer</label>
          <input
            id="filter-search"
            type="search"
            placeholder="Filter by name, manufacturer…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm w-56"
          />
        </div>
      </div>

      {error && <p className="text-red-600 text-sm mb-2">{error}</p>}

      {/* Mobile card list */}
      <div className="md:hidden space-y-3">
        {filteredDiscs.map((disc) => (
          <div key={disc.id} className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
            <div className="flex gap-3">
              {disc.photos?.[0] ? (
                <img
                  src={disc.photos[0].photo_path}
                  alt=""
                  className="w-16 h-16 object-cover rounded flex-shrink-0"
                />
              ) : (
                <div className="w-16 h-16 bg-gray-200 rounded flex-shrink-0 flex items-center justify-center text-gray-400 text-xs text-center">
                  No photo
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-900">{disc.name}</p>
                <p className="text-sm text-gray-500">{disc.manufacturer}</p>
                <p className="text-sm text-gray-600">{disc.color}</p>
                {disc.owner_name && <p className="text-sm text-gray-700">{disc.owner_name}</p>}
                {disc.phone_number && <p className="text-sm text-gray-500">{disc.phone_number}</p>}
              </div>
            </div>
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              {disc.is_returned ? (
                <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs">Returned</span>
              ) : disc.final_notice_sent ? (
                <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs">Final notice</span>
              ) : (
                <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded text-xs">Holding</span>
              )}
              <button
                onClick={() => handleToggleIsFound(disc.id, disc.is_found)}
                className={`px-2 py-0.5 rounded text-xs font-medium border-0 ${
                  disc.is_found
                    ? 'bg-green-100 text-green-700 hover:bg-green-200'
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                }`}
              >
                {disc.is_found ? 'Found' : 'Not found'}
              </button>
              <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer">
                <input
                  type="checkbox"
                  checked={disc.is_returned}
                  onChange={() => handleToggleIsReturned(disc.id, disc.is_returned)}
                  aria-label={disc.is_returned ? 'Mark as not returned' : 'Mark as returned'}
                />
                Returned
              </label>
              <div className="flex gap-3 ml-auto">
                <Link to={`/admin/discs/${disc.id}/edit`} className="text-blue-600 text-sm hover:underline">
                  Edit
                </Link>
                <button
                  onClick={() => handleDelete(disc.id, disc.name)}
                  className="text-red-500 text-sm hover:text-red-700"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
        {filteredDiscs.length === 0 && (
          <p className="text-gray-500 text-sm py-4 text-center">No discs found.</p>
        )}
      </div>

      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-100 text-left">
              <th className="px-3 py-2 border border-gray-200">Photo</th>
              <th className="px-3 py-2 border border-gray-200">Disc</th>
              <th className="px-3 py-2 border border-gray-200">Color</th>
              <th className="px-3 py-2 border border-gray-200">Phone</th>
              <th className="px-3 py-2 border border-gray-200">Owner</th>
              <th className="px-3 py-2 border border-gray-200">Found</th>
              <th className="px-3 py-2 border border-gray-200">Returned</th>
              <th className="px-3 py-2 border border-gray-200">Status</th>
              <th className="px-3 py-2 border border-gray-200">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredDiscs.map((disc) => (
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
                  <button
                    onClick={() => handleToggleIsFound(disc.id, disc.is_found)}
                    className={`px-2 py-0.5 rounded text-xs font-medium cursor-pointer border-0 ${
                      disc.is_found
                        ? 'bg-green-100 text-green-700 hover:bg-green-200'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                    }`}
                    title={disc.is_found ? 'Mark as not found' : 'Mark as found'}
                  >
                    {disc.is_found ? 'Found' : 'Not found'}
                  </button>
                </td>
                <td className="px-3 py-2 border border-gray-200 text-center">
                  <input
                    type="checkbox"
                    checked={disc.is_returned}
                    onChange={() => handleToggleIsReturned(disc.id, disc.is_returned)}
                    aria-label={disc.is_returned ? 'Mark as not returned' : 'Mark as returned'}
                    className="cursor-pointer"
                  />
                </td>
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
