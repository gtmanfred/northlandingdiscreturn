import { render, screen, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'
import { ImportPreviewDialog, type ImportPlan } from './ImportPreviewDialog'

const plan: ImportPlan = {
  created: [{ row_number: 4, manufacturer: 'Discraft', model: 'Heat', colors: ['purple'], owner: 'Jane Doe / +14049518881', will_notify: true, skip_reason: null, duplicate_warning: null }],
  updated: [{ row_number: 5, manufacturer: 'Innova', model: 'Roc', colors: ['blue'], owner: null,
    diffs: [{ field: 'notes', old: 'x', new: 'changed' }] }],
  unchanged: 3,
  errors: [{ row: { row_number: 7, manufacturer: 'Axiom', model: 'Fireball', notes: 'x' }, reason: 'missing or invalid Date found' }],
  counts: { created: 1, updated: 1, unchanged: 3, errors: 1, will_notify: 1, possible_duplicates: 0 },
}

test('renders counts, buckets, diffs, and full error rows', () => {
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={plan} busy={false}
    onApprove={() => {}} onCancel={() => {}} />)
  expect(screen.getByText(/1 new/i)).toBeInTheDocument()
  expect(screen.getByText(/1 updated/i)).toBeInTheDocument()
  expect(screen.getByText(/3 unchanged/i)).toBeInTheDocument()
  expect(screen.getByText(/1 error/i)).toBeInTheDocument()
  expect(screen.getByText('Heat')).toBeInTheDocument()
  expect(screen.getByText(/notes: x/i)).toBeInTheDocument()
  expect(screen.getByText(/→ changed/)).toBeInTheDocument()
  expect(screen.getByText(/missing or invalid Date found/)).toBeInTheDocument()
  expect(screen.getByText('Fireball')).toBeInTheDocument()
})

test('splits new discs into will-text and no-text sub-groups', () => {
  const plan2: ImportPlan = {
    created: [
      { row_number: 4, manufacturer: 'Discraft', model: 'Heat', colors: ['purple'], owner: 'Jane Doe / +14049518881', will_notify: true, skip_reason: null, duplicate_warning: null },
      { row_number: 6, manufacturer: 'Innova', model: 'Leopard', colors: ['red'], owner: 'Bob', will_notify: false, skip_reason: 'returned', duplicate_warning: null },
    ],
    updated: [],
    unchanged: 0,
    errors: [],
    counts: { created: 2, updated: 0, unchanged: 0, errors: 0, will_notify: 1, possible_duplicates: 0 },
  }
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={plan2} busy={false}
    onApprove={() => {}} onCancel={() => {}} />)
  expect(screen.getByText(/will text owner \(1\)/i)).toBeInTheDocument()
  expect(screen.getByText(/no text \(1\)/i)).toBeInTheDocument()
  expect(screen.getByText(/\(returned\)/i)).toBeInTheDocument()
})

test('approve and cancel fire their handlers', () => {
  const onApprove = vi.fn()
  const onCancel = vi.fn()
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={plan} busy={false}
    onApprove={onApprove} onCancel={onCancel} />)
  fireEvent.click(screen.getByRole('button', { name: /approve & merge/i }))
  expect(onApprove).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }))
  expect(onCancel).toHaveBeenCalledOnce()
})

test('shows the possible-duplicate count and per-row warning', () => {
  const warned: ImportPlan = {
    created: [{
      row_number: 4, manufacturer: 'Discraft', model: 'Heat', colors: ['purple'],
      owner: 'Jane Doe / +14049518881', will_notify: true, skip_reason: null,
      duplicate_warning: 'possible duplicate — new ID but matches existing disc abc-123',
    }],
    updated: [],
    unchanged: 0,
    errors: [],
    counts: { created: 1, updated: 0, unchanged: 0, errors: 0, will_notify: 1, possible_duplicates: 1 },
  }
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={warned} busy={false}
    onApprove={() => {}} onCancel={() => {}} />)
  expect(screen.getByText(/1 possible duplicate/i)).toBeInTheDocument()
  expect(screen.getByText(/matches existing disc abc-123/)).toBeInTheDocument()
})

test('hides the possible-duplicate chip when there are none', () => {
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={plan} busy={false}
    onApprove={() => {}} onCancel={() => {}} />)
  expect(screen.queryByText(/possible duplicate/i)).not.toBeInTheDocument()
})

test('error rows show the disc_id column', () => {
  const bad: ImportPlan = {
    created: [], updated: [], unchanged: 0,
    errors: [{ row: { row_number: 9, model: 'Heat', disc_id: 'not-a-uuid' }, reason: 'invalid ID' }],
    counts: { created: 0, updated: 0, unchanged: 0, errors: 1, will_notify: 0, possible_duplicates: 0 },
  }
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={bad} busy={false}
    onApprove={() => {}} onCancel={() => {}} />)
  expect(screen.getByText('disc_id')).toBeInTheDocument()
  expect(screen.getByText('not-a-uuid')).toBeInTheDocument()
  expect(screen.getByText('invalid ID')).toBeInTheDocument()
})
