import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

export type PlanDiff = { field: string; old: unknown; new: unknown }
export type PlannedDisc = {
  row_number: number
  manufacturer: string
  model: string
  colors: string[]
  owner: string | null
}
export type PlannedNew = PlannedDisc & { will_notify: boolean; skip_reason: string | null }
export type PlannedUpdate = PlannedDisc & { diffs: PlanDiff[] }
export type PlanError = { row: Record<string, unknown>; reason: string }
export type ImportPlan = {
  created: PlannedNew[]
  updated: PlannedUpdate[]
  unchanged: number
  errors: PlanError[]
  counts: { created: number; updated: number; unchanged: number; errors: number; will_notify: number }
}

const fmt = (v: unknown): string =>
  v === null || v === undefined ? '—' : Array.isArray(v) ? v.join(' ') : String(v)

const ERROR_COLS = [
  'row_number', 'first_name', 'last_name', 'phone', 'manufacturer',
  'model', 'colors', 'notes', 'input_date', 'returned', 'returned_date',
]

export function ImportPreviewDialog({
  open,
  filename,
  plan,
  busy,
  onApprove,
  onCancel,
}: {
  open: boolean
  filename: string
  plan: ImportPlan | null
  busy: boolean
  onApprove: () => void
  onCancel: () => void
}) {
  if (!plan) return null
  const c = plan.counts
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel() }}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Review import — {filename}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-wrap gap-2 text-sm">
          <span className="rounded bg-muted px-2 py-1">{c.created} new</span>
          <span className="rounded bg-muted px-2 py-1">{c.updated} updated</span>
          <span className="rounded bg-muted px-2 py-1">{c.unchanged} unchanged</span>
          <span className="rounded bg-muted px-2 py-1">{c.errors} error{c.errors === 1 ? '' : 's'}</span>
        </div>

        {plan.created.length > 0 && (() => {
          const willText = plan.created.filter((d) => d.will_notify)
          const noText = plan.created.filter((d) => !d.will_notify)
          const line = (d: PlannedNew) => (
            <>
              {d.manufacturer} <span>{d.model}</span> [{d.colors.join(' ')}]{d.owner ? ` — ${d.owner}` : ''}
            </>
          )
          return (
            <>
              {willText.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer font-medium">
                    New — will text owner ({willText.length})
                  </summary>
                  <ul className="mt-1 space-y-1 text-sm">
                    {willText.map((d) => (
                      <li key={`cw-${d.row_number}`}>{line(d)}</li>
                    ))}
                  </ul>
                </details>
              )}
              {noText.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer font-medium">
                    New — no text ({noText.length})
                  </summary>
                  <ul className="mt-1 space-y-1 text-sm">
                    {noText.map((d) => (
                      <li key={`cn-${d.row_number}`}>
                        {line(d)}{' '}
                        <span className="text-muted-foreground">({d.skip_reason})</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )
        })()}

        {plan.updated.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer font-medium">Updated discs ({plan.updated.length})</summary>
            <ul className="mt-1 space-y-2 text-sm">
              {plan.updated.map((d) => (
                <li key={`u-${d.row_number}`}>
                  <div>{d.manufacturer} {d.model} [{d.colors.join(' ')}]</div>
                  <ul className="ml-4 list-disc text-muted-foreground">
                    {d.diffs.map((diff, i) => (
                      <li key={i}>{diff.field}: {fmt(diff.old)} → {fmt(diff.new)}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </details>
        )}

        {plan.errors.length > 0 && (
          <div className="mt-2">
            <p className="font-medium text-destructive">Error rows ({plan.errors.length})</p>
            <div className="overflow-x-auto">
              <table className="mt-1 w-full border-collapse text-xs">
                <thead>
                  <tr>
                    {ERROR_COLS.map((col) => (
                      <th key={col} className="border px-1 py-0.5 text-left">{col}</th>
                    ))}
                    <th className="border px-1 py-0.5 text-left">reason</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.errors.map((e, i) => (
                    <tr key={i}>
                      {ERROR_COLS.map((col) => (
                        <td key={col} className="border px-1 py-0.5">{fmt(e.row[col])}</td>
                      ))}
                      <td className="border px-1 py-0.5 text-destructive">{e.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button onClick={onApprove} disabled={busy}>Approve &amp; merge</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
