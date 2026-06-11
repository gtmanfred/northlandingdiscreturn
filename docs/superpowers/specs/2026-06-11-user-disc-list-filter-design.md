# User Disc List Filter — Design

**Goal:** Add a status filter to the user-facing disc list (`MyDiscsPage`). By default it shows only discs awaiting pickup (not yet returned).

**Architecture:** Pure frontend change. The `GET /me/discs` endpoint already returns the full per-user list of found discs with no pagination, so filtering happens client-side on the already-fetched data. No backend, API client, or schema changes.

**Tech Stack:** React, local `useState`, existing `useGetMyDiscs` hook, shadcn `Select` component (`@/components/ui/select`) — same control used by the admin disc filter bar.

---

## Component — MyDiscsPage

### Filter state

A single local state value:

```tsx
const [filter, setFilter] = useState<'awaiting' | 'returned' | 'all'>('awaiting')
```

Default `'awaiting'` — list opens showing only discs still needing pickup.

### Filter logic

Applied to the fetched `discs` array:

- `awaiting` → `!disc.is_returned` (includes both "Waiting for pickup" and "Final notice sent" discs)
- `returned` → `disc.is_returned`
- `all` → no filter

```tsx
const visibleDiscs = (discs ?? []).filter((d) => {
  if (filter === 'awaiting') return !d.is_returned
  if (filter === 'returned') return d.is_returned
  return true
})
```

### Filter control

A `Select` rendered above the disc list, labeled "Show":

| Option label    | value      |
|-----------------|------------|
| Awaiting pickup | `awaiting` |
| Returned        | `returned` |
| All             | `all`      |

The Select renders only when there is at least one disc to filter. On the no-discs-at-all empty states (see below) it is omitted, since there is nothing to filter.

### Render states

1. **Loading** — existing `LoadingState`. Unchanged.
2. **Zero discs total** — existing empty states, unchanged:
   - No verified phone → "Add a phone number" prompt with profile link.
   - Verified phone, no discs → "No discs found".
   - No Select shown.
3. **Discs exist** — render the Select, then:
   - `visibleDiscs.length > 0` → the disc card list (existing card markup).
   - `visibleDiscs.length === 0` (filter hides everything) → a lightweight inline message, e.g. "No discs match this filter." The Select stays visible so the user can switch back.

---

## Testing

`MyDiscsPage.test.tsx`, using the existing `vi.mock('../api/northlanding')` setup:

- Default filter shows only not-returned discs; a returned disc is hidden.
- Switching the Select to "Returned" shows only returned discs.
- Switching to "All" shows both returned and not-returned discs.
- When the active filter hides every disc, the "No discs match this filter." message renders and the Select is still present.
- The Select is not rendered when there are zero discs total (existing empty-state behavior preserved).

Existing tests (loading, empty states, phone prompts) must continue to pass; the "shows disc details when data loads" test uses a not-returned disc, so it remains visible under the default filter.
