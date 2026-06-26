import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useGetMyDiscs, useGetMe } from '../api/northlanding'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { StatusBadge, discStatus } from '../components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Disc3, Phone } from 'lucide-react'

type DiscFilter = 'awaiting' | 'returned' | 'all'

export function MyDiscsPage() {
  const { data: discs, isLoading } = useGetMyDiscs()
  const { data: user, isLoading: userLoading } = useGetMe()
  const [filter, setFilter] = useState<DiscFilter>('awaiting')

  const hasVerifiedPhone = user?.phone_numbers?.some((p) => p.verified) ?? false

  const visibleDiscs = (discs ?? []).filter((d) => {
    if (filter === 'awaiting') return !d.is_returned
    if (filter === 'returned') return d.is_returned
    return true
  })

  return (
    <div>
      <PageHeader title="My Discs" description="Discs matching your linked phone numbers." />

      {isLoading || userLoading ? (
        <LoadingState variant="list" rows={3} />
      ) : !discs?.length ? (
        !hasVerifiedPhone ? (
          <EmptyState
            icon={<Phone className="h-10 w-10" aria-hidden="true" />}
            title="Add a phone number"
            description="Discs are matched to your verified phone number. Register one on your profile to see your discs here."
            action={
              <Button asChild>
                <Link to="/my/profile">Go to profile</Link>
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={<Disc3 className="h-10 w-10" aria-hidden="true" />}
            title="No discs found"
            description="Nothing is linked to your verified phone numbers yet."
          />
        )
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Label htmlFor="disc-filter">Show</Label>
            <Select value={filter} onValueChange={(v) => setFilter(v as DiscFilter)}>
              <SelectTrigger id="disc-filter" aria-label="Show" className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="awaiting">Awaiting pickup</SelectItem>
                <SelectItem value="returned">Returned</SelectItem>
                <SelectItem value="all">All</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {!visibleDiscs.length ? (
            <p className="text-sm text-muted-foreground">No discs match this filter.</p>
          ) : (
            <div className="space-y-3">
              {visibleDiscs.map((disc) => (
                <Card key={disc.id} className="flex items-start gap-4 p-4">
                  {disc.photos?.[0] && (
                    <img
                      src={disc.photos[0].photo_path}
                      alt={disc.name}
                      className="h-20 w-20 flex-shrink-0 rounded-md object-cover"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-foreground">{disc.name}</span>
                      <span className="text-sm text-muted-foreground">{disc.manufacturer}</span>
                      <span className="inline-flex items-center gap-1" title={disc.colors.join(', ')}>
                        {disc.colors.map((c, i) => (
                          <span
                            key={`${c}-${i}`}
                            className="inline-block h-4 w-4 rounded-full border border-border"
                            style={{ backgroundColor: c.toLowerCase() }}
                          />
                        ))}
                      </span>
                    </div>
                    {disc.owner?.name && (
                      <p className="mt-0.5 text-sm text-muted-foreground">Owner: {disc.owner.name}</p>
                    )}
                    <div className="mt-2">
                      <StatusBadge status={discStatus(disc)} />
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
