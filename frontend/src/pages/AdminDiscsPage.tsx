import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import {
  useListDiscs,
  useDeleteDisc,
  useUpdateDisc,
  getListDiscsQueryKey,
} from '../api/northlanding'
import { PageHeader } from '../components/PageHeader'
import { LoadingState } from '../components/LoadingState'
import { EmptyState } from '../components/EmptyState'
import { StatusBadge, discStatus } from '../components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

type Tri = 'all' | 'true' | 'false'

export function AdminDiscsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  const [isFoundFilter, setIsFoundFilter] = useState<boolean | undefined>(undefined)
  const [isReturnedFilter, setIsReturnedFilter] = useState<boolean | undefined>(undefined)
  const [ownerNameInput, setOwnerNameInput] = useState('')
  const [ownerNameFilter, setOwnerNameFilter] = useState<string | undefined>(undefined)

  const pageSize = 25

  const commitOwnerName = () => {
    const next = ownerNameInput || undefined
    if (next !== ownerNameFilter) {
      setOwnerNameFilter(next)
      setPage(1)
    }
  }

  const commitSearch = () => {
    if (searchInput !== search) setSearch(searchInput)
  }

  const { data, isLoading } = useListDiscs({
    page,
    page_size: pageSize,
    is_found: isFoundFilter,
    is_returned: isReturnedFilter,
    owner_name: ownerNameFilter,
  })
  const deleteMutation = useDeleteDisc()
  const updateMutation = useUpdateDisc()
  const [error, setError] = useState('')

  const setTri = (setter: (v: boolean | undefined) => void) => (val: Tri) => {
    setter(val === 'all' ? undefined : val === 'true')
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

  if (isLoading) return <LoadingState />

  const filteredDiscs = discs.filter((d) =>
    !search ||
    d.name.toLowerCase().includes(search.toLowerCase()) ||
    d.manufacturer.toLowerCase().includes(search.toLowerCase()),
  )

  const triValue = (v: boolean | undefined): Tri => (v === undefined ? 'all' : (String(v) as Tri))

  return (
    <div>
      <PageHeader
        title="Discs"
        actions={
          <Button asChild>
            <Link to="/admin/discs/new">
              <Plus className="mr-1 h-4 w-4" />
              Add Disc
            </Link>
          </Button>
        }
      />

      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-end gap-3 pt-6">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="filter-found">Found</Label>
            <Select value={triValue(isFoundFilter)} onValueChange={setTri(setIsFoundFilter)}>
              <SelectTrigger id="filter-found" aria-label="Found" className="w-32">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="true">Found</SelectItem>
                <SelectItem value="false">Not found</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="filter-returned">Returned</Label>
            <Select value={triValue(isReturnedFilter)} onValueChange={setTri(setIsReturnedFilter)}>
              <SelectTrigger id="filter-returned" aria-label="Returned" className="w-32">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="true">Returned</SelectItem>
                <SelectItem value="false">Not returned</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="filter-owner">Owner name</Label>
            <Input
              id="filter-owner"
              type="text"
              placeholder="Owner name…"
              value={ownerNameInput}
              onChange={(e) => setOwnerNameInput(e.target.value)}
              onBlur={commitOwnerName}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  commitOwnerName()
                }
              }}
              className="w-48"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="filter-search">Name / manufacturer</Label>
            <Input
              id="filter-search"
              type="search"
              placeholder="Filter…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onBlur={commitSearch}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  commitSearch()
                }
              }}
              className="w-56"
            />
          </div>
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive" className="mb-3">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {filteredDiscs.length === 0 ? (
        <EmptyState title="No discs found" description="Try adjusting your filters or add a new disc." />
      ) : (
        <>
          {/* Mobile card list */}
          <div className="space-y-3 md:hidden">
            {filteredDiscs.map((disc) => (
              <Card key={disc.id}>
                <CardContent className="p-4">
                  <div className="flex gap-3">
                    {disc.photos?.[0] ? (
                      <img
                        src={disc.photos[0].photo_path}
                        alt=""
                        className="h-16 w-16 flex-shrink-0 rounded-md object-cover"
                      />
                    ) : (
                      <div className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-md bg-muted text-center text-xs text-muted-foreground">
                        No photo
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-foreground">{disc.name}</p>
                      <p className="text-sm text-muted-foreground">{disc.manufacturer}</p>
                      <p className="text-sm text-muted-foreground">{disc.color}</p>
                      {disc.owner?.name && <p className="text-sm">{disc.owner.name}</p>}
                      {disc.owner?.phone_number && (
                        <p className="text-sm text-muted-foreground">{disc.owner.phone_number}</p>
                      )}
                      {disc.notes && (
                        <p className="text-sm text-muted-foreground italic">{disc.notes}</p>
                      )}
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <StatusBadge status={discStatus(disc)} />
                    <FoundToggle isFound={disc.is_found} onClick={() => handleToggleIsFound(disc.id, disc.is_found)} />
                    <label className="flex cursor-pointer items-center gap-1 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={disc.is_returned}
                        onChange={() => handleToggleIsReturned(disc.id, disc.is_returned)}
                        aria-label={disc.is_returned ? 'Mark as not returned' : 'Mark as returned'}
                      />
                      Returned
                    </label>
                    <div className="ml-auto flex gap-2">
                      <Button asChild variant="ghost" size="sm">
                        <Link to={`/admin/discs/${disc.id}/edit`}>Edit</Link>
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => handleDelete(disc.id, disc.name)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Desktop table */}
          <Card className="hidden overflow-hidden md:block">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Photo</TableHead>
                    <TableHead>Disc</TableHead>
                    <TableHead>Color</TableHead>
                    <TableHead>Phone</TableHead>
                    <TableHead>Owner</TableHead>
                    <TableHead>Notes</TableHead>
                    <TableHead>Found</TableHead>
                    <TableHead className="text-center">Returned</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredDiscs.map((disc) => (
                    <TableRow key={disc.id}>
                      <TableCell>
                        {disc.photos?.[0] ? (
                          <img
                            src={disc.photos[0].photo_path}
                            alt=""
                            className="h-10 w-10 rounded object-cover"
                          />
                        ) : (
                          <div className="flex h-10 w-10 items-center justify-center rounded bg-muted text-xs text-muted-foreground">
                            —
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="font-medium text-foreground">{disc.name}</div>
                        <div className="text-muted-foreground">{disc.manufacturer}</div>
                      </TableCell>
                      <TableCell>{disc.color}</TableCell>
                      <TableCell>{disc.owner?.phone_number ?? '—'}</TableCell>
                      <TableCell>{disc.owner?.name ?? '—'}</TableCell>
                      <TableCell className="max-w-[16rem] truncate text-muted-foreground" title={disc.notes ?? ''}>
                        {disc.notes ?? '—'}
                      </TableCell>
                      <TableCell>
                        <FoundToggle
                          isFound={disc.is_found}
                          onClick={() => handleToggleIsFound(disc.id, disc.is_found)}
                        />
                      </TableCell>
                      <TableCell className="text-center">
                        <input
                          type="checkbox"
                          checked={disc.is_returned}
                          onChange={() => handleToggleIsReturned(disc.id, disc.is_returned)}
                          aria-label={disc.is_returned ? 'Mark as not returned' : 'Mark as returned'}
                          className="cursor-pointer"
                        />
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={discStatus(disc)} />
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-right">
                        <Button asChild variant="ghost" size="sm">
                          <Link to={`/admin/discs/${disc.id}/edit`}>Edit</Link>
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => handleDelete(disc.id, disc.name)}
                        >
                          Delete
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Card>
        </>
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  )
}

function FoundToggle({ isFound, onClick }: { isFound: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={isFound ? 'Mark as not found' : 'Mark as found'}
      className={cn(
        'rounded px-2 py-0.5 text-xs font-medium transition-colors',
        isFound
          ? 'bg-green-100 text-green-800 hover:bg-green-200'
          : 'bg-muted text-muted-foreground hover:bg-muted/80',
      )}
    >
      {isFound ? 'Found' : 'Not found'}
    </button>
  )
}

