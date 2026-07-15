import { render, screen, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'
import { ImportPreviewDialog, type ImportPlan } from './ImportPreviewDialog'

const plan: ImportPlan = {
  created: [{ row_number: 4, manufacturer: 'Discraft', model: 'Heat', colors: ['purple'], owner: 'Jane Doe / +14049518881' }],
  updated: [{ row_number: 5, manufacturer: 'Innova', model: 'Roc', colors: ['blue'], owner: null,
    diffs: [{ field: 'notes', old: 'x', new: 'changed' }] }],
  unchanged: 3,
  errors: [{ row: { row_number: 7, manufacturer: 'Axiom', model: 'Fireball', notes: 'x' }, reason: 'missing or invalid Date found' }],
  counts: { created: 1, updated: 1, unchanged: 3, errors: 1 },
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
