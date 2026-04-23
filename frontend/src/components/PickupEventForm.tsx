import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { combineDateAndTime, splitIsoToLocal } from '../lib/courseTime'

export interface PickupEventFormValues {
  start_at: string
  end_at: string
  notes: string | null
}

interface Props {
  initial?: { start_at: string; end_at: string; notes: string | null }
  submitting?: boolean
  submitLabel: string
  onSubmit: (v: PickupEventFormValues) => void | Promise<void>
  onCancel?: () => void
}

export function PickupEventForm({ initial, submitting, submitLabel, onSubmit, onCancel }: Props) {
  const [date, setDate] = useState('')
  const [startTime, setStartTime] = useState('16:00')
  const [endTime, setEndTime] = useState('18:00')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (initial) {
      const s = splitIsoToLocal(initial.start_at)
      const e = splitIsoToLocal(initial.end_at)
      setDate(s.date)
      setStartTime(s.time)
      setEndTime(e.time)
      setNotes(initial.notes ?? '')
    }
  }, [initial])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const startIso = combineDateAndTime(date, startTime)
    const endIso = combineDateAndTime(date, endTime)
    if (new Date(endIso) <= new Date(startIso)) {
      setError('End time must be after start time.')
      return
    }
    await onSubmit({ start_at: startIso, end_at: endIso, notes: notes || null })
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
      <div className="flex min-w-32 flex-col gap-1.5">
        <Label htmlFor="pickup-date">Date *</Label>
        <Input
          id="pickup-date"
          type="date"
          required
          value={date}
          onChange={(ev) => setDate(ev.target.value)}
        />
      </div>
      <div className="flex min-w-28 flex-col gap-1.5">
        <Label htmlFor="pickup-start">Start *</Label>
        <Input
          id="pickup-start"
          type="time"
          required
          value={startTime}
          onChange={(ev) => setStartTime(ev.target.value)}
        />
      </div>
      <div className="flex min-w-28 flex-col gap-1.5">
        <Label htmlFor="pickup-end">End *</Label>
        <Input
          id="pickup-end"
          type="time"
          required
          value={endTime}
          onChange={(ev) => setEndTime(ev.target.value)}
        />
      </div>
      <div className="flex min-w-40 flex-1 flex-col gap-1.5">
        <Label htmlFor="pickup-notes">Notes</Label>
        <Input
          id="pickup-notes"
          placeholder="Optional notes"
          value={notes}
          onChange={(ev) => setNotes(ev.target.value)}
        />
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting}>{submitLabel}</Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
        )}
      </div>
      {error && <p className="w-full text-sm text-destructive">{error}</p>}
    </form>
  )
}
