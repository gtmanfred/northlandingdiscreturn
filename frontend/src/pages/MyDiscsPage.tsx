import { useGetMyDiscs } from '../api/northlanding'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { StatusBadge, discStatus } from '../components/StatusBadge'
import { Card } from '@/components/ui/card'
import { Disc3 } from 'lucide-react'

export function MyDiscsPage() {
  const { data: discs, isLoading } = useGetMyDiscs()

  return (
    <div>
      <PageHeader title="My Discs" description="Discs matching your linked phone numbers." />

      {isLoading ? (
        <LoadingState variant="list" rows={3} />
      ) : !discs?.length ? (
        <EmptyState
          icon={<Disc3 className="h-10 w-10" aria-hidden="true" />}
          title="No discs found"
          description="Nothing is linked to your verified phone numbers yet."
        />
      ) : (
        <div className="space-y-3">
          {discs.map((disc) => (
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
                  <span
                    className="inline-block h-4 w-4 rounded-full border border-border"
                    style={{ backgroundColor: disc.color.toLowerCase() }}
                    title={disc.color}
                  />
                </div>
                {disc.owner_name && (
                  <p className="mt-0.5 text-sm text-muted-foreground">Owner: {disc.owner_name}</p>
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
  )
}
