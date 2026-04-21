import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useAdminListPickupEvents,
  useAdminCreatePickupEvent,
  useAdminNotifyPickupEvent,
  getAdminListPickupEventsQueryKey,
} from '../api/northlanding'
import { LoadingSpinner } from '../components/LoadingSpinner'

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

  if (isLoading) return <LoadingSpinner />

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-6 text-green-800">Pickup Events</h1>

      {notifyResult && (
        <div className="bg-green-50 border border-green-200 rounded p-3 mb-4 text-sm">
          Notifications sent: {notifyResult.sms_jobs_enqueued} SMS jobs enqueued for {notifyResult.discs_notified} discs.
          <button onClick={() => setNotifyResult(null)} className="ml-3 text-gray-500 hover:text-gray-700">×</button>
        </div>
      )}
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <form onSubmit={handleCreate} className="bg-white border border-gray-200 rounded-lg p-4 mb-8 flex gap-3 flex-wrap">
        <div className="flex-1 min-w-40">
          <label className="block text-xs text-gray-500 mb-1">Pickup Date *</label>
          <input
            type="date"
            required
            value={form.scheduled_date}
            onChange={(e) => setForm((f) => ({ ...f, scheduled_date: e.target.value }))}
            className="w-full border border-gray-300 rounded px-3 py-2"
          />
        </div>
        <div className="flex-1 min-w-40">
          <label className="block text-xs text-gray-500 mb-1">Notes</label>
          <input
            placeholder="Optional notes"
            value={form.notes}
            onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            className="w-full border border-gray-300 rounded px-3 py-2"
          />
        </div>
        <div className="flex items-end">
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="bg-green-700 text-white px-4 py-2 rounded hover:bg-green-800 disabled:opacity-50"
          >
            Create Event
          </button>
        </div>
      </form>

      {!events?.length ? (
        <p className="text-gray-500">No pickup events yet.</p>
      ) : (
        <div className="space-y-3">
          {events.map((event) => (
            <div key={event.id} className="bg-white border border-gray-200 rounded-lg p-4 flex items-center justify-between">
              <div>
                <p className="font-semibold">{event.scheduled_date}</p>
                {event.notes && <p className="text-sm text-gray-500">{event.notes}</p>}
                {event.notifications_sent_at && (
                  <p className="text-xs text-green-600">
                    Notifications sent {new Date(event.notifications_sent_at).toLocaleString()}
                  </p>
                )}
              </div>
              {!event.notifications_sent_at && (
                <button
                  onClick={() => handleNotify(event.id)}
                  disabled={notifyMutation.isPending}
                  className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 text-sm disabled:opacity-50"
                >
                  Send Notifications
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
