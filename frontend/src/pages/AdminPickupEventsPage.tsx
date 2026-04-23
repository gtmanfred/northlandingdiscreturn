import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Send } from 'lucide-react'
import {
  useAdminListPickupEvents,
  useAdminCreatePickupEvent,
  useAdminNotifyPickupEvent,
  getAdminListPickupEventsQueryKey,
} from '../api/northlanding'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'

export function AdminPickupEventsPage() {
  const queryClient = useQueryClient()
  const { data: events, isLoading } = useAdminListPickupEvents()
  const createMutation = useAdminCreatePickupEvent()
  const notifyMutation = useAdminNotifyPickupEvent()

  const [form, setForm] = useState({ scheduled_date: '', notes: '' })
  const [notifyResult, setNotifyResult] = useState<{ sms_jobs_enqueued: number; discs_notified: number } | null>(null)
  const [error, setError] = useState('')

  const refresh = () => queryClient.invalidateQueries({ queryKey: getAdminListPickupEventsQueryKey() })

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      await createMutation.mutateAsync({ data: form })
      setForm({ scheduled_date: '', notes: '' })
      refresh()
    } catch {
      setError('Failed to create pickup event.')
    }
  }

  const handleNotify = async (eventId: string) => {
    if (!confirm('Send SMS notifications to all disc owners with unreturned discs?')) return
    setError('')
    try {
      const result = await notifyMutation.mutateAsync({ eventId })
      setNotifyResult(result)
      refresh()
    } catch {
      setError('Failed to send notifications.')
    }
  }

  if (isLoading) return <LoadingState />

  return (
    <div className="max-w-3xl">
      <PageHeader title="Pickup Events" />

      {notifyResult && (
        <Alert className="mb-4 border-green-200 bg-green-50 text-green-900">
          <AlertDescription className="flex items-center justify-between gap-3">
            <span>
              Notifications sent: {notifyResult.sms_jobs_enqueued} SMS jobs enqueued for{' '}
              {notifyResult.discs_notified} discs.
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-auto px-2 py-0.5 text-xs"
              onClick={() => setNotifyResult(null)}
            >
              Dismiss
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card className="mb-8">
        <CardContent className="pt-6">
          <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-40 flex-1 flex-col gap-1.5">
              <Label htmlFor="pickup-date">Pickup date *</Label>
              <Input
                id="pickup-date"
                type="date"
                required
                value={form.scheduled_date}
                onChange={(e) => setForm((f) => ({ ...f, scheduled_date: e.target.value }))}
              />
            </div>
            <div className="flex min-w-40 flex-1 flex-col gap-1.5">
              <Label htmlFor="pickup-notes">Notes</Label>
              <Input
                id="pickup-notes"
                placeholder="Optional notes"
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              />
            </div>
            <Button type="submit" disabled={createMutation.isPending}>
              Create event
            </Button>
          </form>
        </CardContent>
      </Card>

      {!events?.length ? (
        <EmptyState
          icon={<CalendarDays className="h-10 w-10" aria-hidden="true" />}
          title="No pickup events yet"
          description="Create one above to start scheduling pickups."
        />
      ) : (
        <div className="space-y-3">
          {events.map((event) => (
            <Card key={event.id}>
              <CardContent className="flex items-center justify-between gap-3 p-4">
                <div>
                  <p className="font-semibold text-foreground">{event.scheduled_date}</p>
                  {event.notes && <p className="text-sm text-muted-foreground">{event.notes}</p>}
                  {event.notifications_sent_at && (
                    <p className="mt-1 text-xs text-green-700">
                      Notifications sent {new Date(event.notifications_sent_at).toLocaleString()}
                    </p>
                  )}
                </div>
                {!event.notifications_sent_at && (
                  <Button
                    onClick={() => handleNotify(event.id)}
                    disabled={notifyMutation.isPending}
                    size="sm"
                  >
                    <Send className="mr-2 h-4 w-4" />
                    Send notifications
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
