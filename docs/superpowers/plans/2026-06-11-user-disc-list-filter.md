# User Disc List Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a status filter to the user-facing disc list (`MyDiscsPage`) that defaults to showing only discs awaiting pickup (not yet returned).

**Architecture:** Pure frontend change. `GET /me/discs` already returns the full per-user list with no pagination, so filtering is client-side via local React state on the fetched array. No backend, API client, or schema changes.

**Tech Stack:** React, `useState`, existing `useGetMyDiscs` hook, shadcn `Select` (`@/components/ui/select`) and `Label` (`@/components/ui/label`) — the same controls used by the admin disc filter bar.

---

### Task 1: Filter the disc list and add the Select control

**Files:**
- Modify: `frontend/src/pages/MyDiscsPage.tsx`
- Test: `frontend/src/pages/MyDiscsPage.test.tsx`

The current `MyDiscsPage.tsx` (for reference — full current contents):

```tsx
import { Link } from 'react-router-dom'
import { useGetMyDiscs, useGetMe } from '../api/northlanding'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { StatusBadge, discStatus } from '../components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Disc3, Phone } from 'lucide-react'

export function MyDiscsPage() {
  const { data: discs, isLoading } = useGetMyDiscs()
  const { data: user, isLoading: userLoading } = useGetMe()

  const hasVerifiedPhone = user?.phone_numbers?.some((p) => p.verified) ?? false
  // ... render
}
```

The disc objects expose `is_returned: boolean | null` (used today by `discStatus`).

---

- [ ] **Step 1: Write the failing tests**

Add these tests to `frontend/src/pages/MyDiscsPage.test.tsx`. They reference `userEvent`; add the import at the top of the file if not present:

```tsx
import userEvent from '@testing-library/user-event'
```

Radix `Select` drives its dropdown with pointer-capture and `scrollIntoView`, neither of which jsdom implements — without stubs, clicking an option throws. Add this stub block at the top of the `describe('MyDiscsPage', () => { ... })` block, before the tests:

```tsx
beforeAll(() => {
  // jsdom lacks these; Radix Select needs them to open and select options.
  Element.prototype.hasPointerCapture = vi.fn()
  Element.prototype.scrollIntoView = vi.fn()
})
```

Ensure `beforeAll` is included in the `vitest` import at the top of the file:

```tsx
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
```

Add the following inside the `describe('MyDiscsPage', () => { ... })` block:

```tsx
const twoDiscs = [
  { id: '1', manufacturer: 'Innova', name: 'Destroyer', color: 'Red', is_returned: false, photos: [] },
  { id: '2', manufacturer: 'Discraft', name: 'Buzzz', color: 'Blue', is_returned: true, photos: [] },
]

it('defaults to showing only discs awaiting pickup', () => {
  vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: twoDiscs } as any)
  render(<MyDiscsPage />, { wrapper })
  expect(screen.getByText('Destroyer')).toBeInTheDocument()
  expect(screen.queryByText('Buzzz')).not.toBeInTheDocument()
})

it('shows only returned discs when the Returned filter is selected', async () => {
  vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: twoDiscs } as any)
  render(<MyDiscsPage />, { wrapper })
  await userEvent.click(screen.getByRole('combobox', { name: /show/i }))
  await userEvent.click(screen.getByRole('option', { name: 'Returned' }))
  expect(screen.getByText('Buzzz')).toBeInTheDocument()
  expect(screen.queryByText('Destroyer')).not.toBeInTheDocument()
})

it('shows all discs when the All filter is selected', async () => {
  vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: twoDiscs } as any)
  render(<MyDiscsPage />, { wrapper })
  await userEvent.click(screen.getByRole('combobox', { name: /show/i }))
  await userEvent.click(screen.getByRole('option', { name: 'All' }))
  expect(screen.getByText('Buzzz')).toBeInTheDocument()
  expect(screen.getByText('Destroyer')).toBeInTheDocument()
})

it('shows a no-match message when the filter hides every disc', async () => {
  const onlyReturned = [
    { id: '2', manufacturer: 'Discraft', name: 'Buzzz', color: 'Blue', is_returned: true, photos: [] },
  ]
  vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: onlyReturned } as any)
  render(<MyDiscsPage />, { wrapper })
  // Default 'awaiting' filter hides the only (returned) disc.
  expect(screen.getByText(/no discs match this filter/i)).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: /show/i })).toBeInTheDocument()
})

it('does not render the filter when there are zero discs', () => {
  vi.mocked(useGetMyDiscs).mockReturnValue({ isLoading: false, data: [] } as any)
  render(<MyDiscsPage />, { wrapper })
  expect(screen.queryByRole('combobox', { name: /show/i })).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/MyDiscsPage.test.tsx`
Expected: FAIL — the new tests can't find the "Show" combobox / still render both discs.

- [ ] **Step 3: Implement the filter in `MyDiscsPage.tsx`**

Replace the entire contents of `frontend/src/pages/MyDiscsPage.tsx` with:

```tsx
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
                      <span
                        className="inline-block h-4 w-4 rounded-full border border-border"
                        style={{ backgroundColor: disc.color.toLowerCase() }}
                        title={disc.color}
                      />
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/MyDiscsPage.test.tsx`
Expected: PASS — all new tests plus the pre-existing tests (loading, empty states, phone prompts, "shows disc details when data loads" — its disc has `is_returned: false`, so it stays visible under the default filter).

- [ ] **Step 5: Typecheck and lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/MyDiscsPage.tsx frontend/src/pages/MyDiscsPage.test.tsx
git commit -m "feat: filter user disc list, default to awaiting pickup"
```

---

## Self-Review

- **Spec coverage:** filter state (Task 1 Step 3), three filter options + logic (Step 3), Select shown only when discs exist (Step 3 conditional + Step 1 zero-discs test), no-match message (Step 3 + test), existing empty states preserved (unchanged markup + existing tests), tests (Step 1). All spec sections covered.
- **Placeholders:** none — full file contents and test code provided.
- **Type consistency:** `DiscFilter` type defined and used consistently; `filter`/`setFilter`/`visibleDiscs` names consistent throughout.
