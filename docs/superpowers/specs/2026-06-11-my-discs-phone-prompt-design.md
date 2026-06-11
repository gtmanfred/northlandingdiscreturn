# My Discs — phone-number registration prompt

## Problem

The "My Discs" page (`frontend/src/pages/MyDiscsPage.tsx`) lists discs matched to a
user's **verified** phone numbers. A user with no verified number will always see an
empty list with no explanation of *why* it's empty or how to fix it.

## Goal

When the page has zero discs **and** the user has no verified phone number, prompt them
to go to their profile and register a number.

## Trigger logic

In `MyDiscsPage`:

- Fetch `useGetMe()` alongside `useGetMyDiscs()`.
- `hasVerifiedPhone = user?.phone_numbers?.some((p) => p.verified) ?? false`
- Empty-discs branch (`!discs?.length`) splits:
  - **No verified phone** → register-phone empty state (see below).
  - **Has verified phone** → existing empty state, unchanged.

"No discs ready to be picked up" is interpreted as **zero discs at all** (the existing
empty-state case), per design decision. "A number attached" means a **verified** number.

## Presentation

Reuse the existing `EmptyState` component — it already exposes an `action` slot, so no
component change is required.

Phone-prompt variant:

- icon: `Phone` (lucide-react)
- title: "Add a phone number"
- description: discs are matched to your verified phone number; register one on your
  profile to see your discs here.
- action: `Button` (`asChild`) wrapping a react-router `Link to="/my/profile"` labelled
  "Go to profile".

## Loading

Show `LoadingState` while **either** query is loading, so the prompt does not flash
before `useGetMe` resolves.

## Testing (TDD, red/green)

`frontend/src/pages/MyDiscsPage.test.tsx`:

- Add `useGetMe` to the `vi.mock('../api/northlanding', ...)`.
- Wrap renders in `MemoryRouter` (required by `Link`).
- Provide a default `useGetMe` mock for existing tests.
- New cases:
  - no discs + no verified phone → register prompt and profile link visible.
  - no discs + verified phone → original empty state, no prompt.
  - has discs → list renders regardless of phone state.

## Out of scope

- Backend changes.
- Prompting when the user has discs.
- Distinguishing unverified-number users with a different message (they get the register
  prompt; copy says "verified" so it stays accurate).
