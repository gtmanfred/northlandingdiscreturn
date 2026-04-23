import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Send, Pencil } from 'lucide-react'
import {
  useAdminListPickupEvents,
  useAdminCreatePickupEvent,
  useAdminUpdatePickupEvent,
  useAdminNotifyPickupEvent,
  getAdminListPickupEventsQueryKey,
} from '../api/northlanding'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PickupEventForm } from '../components/PickupEventForm'
import { SubscribeBox } from '../components/SubscribeBox'
import { formatWindow } from '../lib/courseTime'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'

export function AdminPickupEventsPage() {
  const queryClient = useQueryClient()
  const { data: events, isLoading } = useAdminListPickupEvents()
  const createMutation = useAdminCreatePickupEvent()
  const updateMutation = useAdminUpdatePickupEvent()
  const notifyMutation = useAdminNotifyPickupEvent()

  const [editingId, setEditingId] = useState<string | null>(null)
  const [notifyResult, setNotifyResult] = useState<{ sms_jobs_enqueued: number; discs_notified: number } | null>(null)
  const [error, setError] = useState('')

  const refresh = () => queryClient.invalidateQueries({ queryKey: getAdminListPickupEventsQueryKey() })

  const handleCreate = async (data: { start_at: string; end_at: string; notes: string | null }) => {
    setError('')
    try {
      await createMutation.mutateAsync({ data })
      refresh()
    } catch {
      setError('Failed to create pickup event.')
    }
  }

  const handleUpdate = async (eventId: string, data: { start_at: string; end_at: string; notes: string | null }) => {
    setError('')
    try {
      await updateMutation.mutateAsync({ eventId, data })
      setEditingId(null)
      refresh()
    } catch {
      setError('Failed to update pickup event.')
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

      <SubscribeBox />

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
          <PickupEventForm
            submitLabel="Create event"
            submitting={createMutation.isPending}
            onSubmit={handleCreate}
          />
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
              <CardContent className="p-4">
                {editingId === event.id ? (
                  <PickupEventForm
                    initial={{ start_at: event.start_at, end_at: event.end_at, notes: event.notes ?? null }}
                    submitLabel="Save"
                    submitting={updateMutation.isPending}
                    onSubmit={(v) => handleUpdate(event.id, v)}
                    onCancel={() => setEditingId(null)}
                  />
                ) : (
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-semibold text-foreground">
                        {formatWindow(event.start_at, event.end_at)}
                      </p>
                      {event.notes && <p className="text-sm text-muted-foreground">{event.notes}</p>}
                      {event.notifications_sent_at && (
                        <p className="mt-1 text-xs text-green-700">
                          Notifications sent {new Date(event.notifications_sent_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => setEditingId(event.id)}>
                        <Pencil className="mr-2 h-4 w-4" />
                        Edit
                      </Button>
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
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
