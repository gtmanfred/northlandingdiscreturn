# Autocomplete for Disc Form Fields

**Date:** 2026-04-21
**Status:** Approved

## Overview

Add freeform autocomplete to text fields across the app so that values previously entered by any user are available as suggestions. Users can still type any value not in the list. Phone number suggestions cascade off the selected owner name and include registered user context (name + email) to distinguish same-named owners.

## Scope

### Fields receiving autocomplete

| Field | Form(s) | Source |
|---|---|---|
| `manufacturer` | AdminDiscFormPage, MyWishlistPage | Distinct values from `discs.manufacturer` |
| `name` | AdminDiscFormPage, MyWishlistPage | Distinct values from `discs.name` |
| `color` | AdminDiscFormPage, MyWishlistPage | Distinct values from `discs.color` |
| `owner_name` | AdminDiscFormPage | Distinct values from `discs.owner_name` |
| `phone_number` | AdminDiscFormPage | Merged from `phone_numbers` + `discs.phone_number`, filtered by owner name |

### Fields excluded from autocomplete

- `phone_number` on MyProfilePage — user is registering their own number, not selecting from records
- `notes` on AdminPickupEventsPage — low value, freeform prose
- `scheduled_date` — date picker
- Checkboxes, verification code input

## Backend

### New routes

#### `GET /api/suggestions?field={field_name}`

Returns a sorted, case-insensitively deduplicated list of distinct string values for the given field drawn from the `discs` table.

**Supported field values:** `manufacturer`, `name`, `color`, `owner_name`

**Response:**
```json
["Discraft", "Innova", "Latitude 64"]
```

**Auth:** `manufacturer`, `name`, `color` — requires authentication. `owner_name` — admin only; owner names should not be enumerable by non-admins.

#### `GET /api/suggestions/phone?owner_name={name}`

Returns phone number suggestions for a given owner name, merging two sources:

1. `phone_numbers` table joined with `users` where `users.name ILIKE :owner_name` (verified registered numbers)
2. `discs.phone_number` where `discs.owner_name ILIKE :owner_name` (numbers from past disc entries)

Duplicates (same number appearing in both sources) are collapsed — the registered-user label wins.

**Response:**
```json
[
  { "number": "+15551234567", "label": "+15551234567 — Jane Smith (jane@example.com)" },
  { "number": "+15559876543", "label": "+15559876543 — Jane Smith (jane2@example.com)" }
]
```

**Auth:** Admin only (this route is only used from AdminDiscFormPage).

## Frontend

### `AutocompleteInput` component

**Location:** `frontend/src/components/AutocompleteInput.tsx`

A drop-in replacement for bare `<input>` elements where autocomplete is needed.

```ts
interface Suggestion {
  value: string;   // written into the input on selection
  label?: string;  // rich display text shown in dropdown (falls back to value)
}

interface AutocompleteInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  suggestions: Suggestion[];
  onValueChange: (value: string) => void;
}
```

**Behavior:**
- Renders with the same Tailwind classes as existing inputs: `w-full border border-gray-300 rounded px-3 py-2`
- Dropdown appears below the input when the typed value matches one or more suggestions (client-side filter, case-insensitive prefix/substring match)
- Keyboard navigation: arrow keys move selection, Enter confirms, Escape closes
- Click outside closes the dropdown
- Freeform: if the user types a value not in the list and blurs, the value is accepted as-is
- When a suggestion has a `label`, the dropdown renders the label; the input receives `value`

**Accessibility:**
- Input: `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-activedescendant`
- Dropdown: `role="listbox"`
- Each option: `role="option"`, `aria-selected`

### Data fetching

The parent form fetches suggestions via TanStack Query and passes them into `AutocompleteInput`. The component itself has no data-fetching logic.

#### AdminDiscFormPage queries

```ts
// Independent queries — run on mount
useQuery(['suggestions', 'manufacturer'], () => fetchSuggestions('manufacturer'))
useQuery(['suggestions', 'name'],         () => fetchSuggestions('name'))
useQuery(['suggestions', 'color'],        () => fetchSuggestions('color'))
useQuery(['suggestions', 'owner_name'],   () => fetchSuggestions('owner_name'))

// Dependent query — only runs when owner_name is set
useQuery(
  ['suggestions', 'phone', ownerName],
  () => fetchPhoneSuggestions(ownerName),
  { enabled: !!ownerName }
)
```

When `owner_name` changes:
1. The phone field is cleared
2. The phone suggestions query re-fetches with the new owner name

#### MyWishlistPage queries

Same three independent queries for `manufacturer`, `name`, `color`. Query results can be shared with AdminDiscFormPage via TanStack Query's cache (same query keys).

### Forms unchanged

`MyProfilePage` — no changes. The phone input there is for the user registering their own verified number.

`AdminPickupEventsPage` — no changes.

## Data flow summary

```
User types in field
  → AutocompleteInput filters suggestions client-side
  → Dropdown shows matching options
  → User selects or types freeform value
  → onValueChange called with selected value
  → (phone field only) if owner_name changed, phone field cleared + phone query re-fetches
```

## Out of scope

- Server-side filtering (all filtering is client-side; suggestion lists are small enough)
- Fuzzy matching (substring match is sufficient)
- Caching TTL tuning (TanStack Query defaults are fine)
- Suggestion management UI (no ability to delete or curate past values)
