# Phone verification — inline verify & resend on profile

## Problem

On the profile page (`frontend/src/pages/MyProfilePage.tsx`), a user can only enter a
verification code in a transient form shown immediately after adding a number (the
`step === 'code-sent'` branch, driven by `step`/`pendingNumber`/`code` state). If the
user reloads or navigates away, an unverified number renders only as "Unverified" with a
**Remove** button — there is no way to enter the code or request a new one. The code also
expires server-side, leaving the user stuck.

## Goal

For any **unverified** phone number in the list, let the user enter a verification code or
request a new code, regardless of whether the number was just added or loaded from a prior
session.

## Scope

Frontend only. The backend already supports both actions:

- `POST /me/phones` (`addPhone`) — for an existing unverified number, reuses the row and
  generates + sends a fresh code (`backend/app/routers/users.py:42-52`). Used as "resend".
- `POST /me/phones/verify` (`verifyPhone`) — validates the code, marks verified, rejects
  expired/invalid codes with HTTP 400.

No backend changes.

## Component structure

Extract a **`PhoneNumberRow`** component → `frontend/src/components/PhoneNumberRow.tsx`.
`MyProfilePage` is already ~175 lines; per-row verify/resend logic does not belong inline.
Each row owns its own state and mutation hooks.

- **Verified row:** number, "Verified" label, **Remove** button (current display).
- **Unverified row:** number, "Unverified" label, a **code input**, **Verify** button,
  **Resend code** button, **Remove** button, and a per-row message slot.

Props: `{ number: string, verified: boolean, onRemove: (number: string) => void,
onVerified: () => void }`. The row calls `useVerifyPhone()` and `useAddPhone()` internally
so `isPending` and errors are scoped per row (no cross-row button disabling). On successful
verify it calls `onVerified`, which the page wires to `refresh`.

## State & data flow

Each `PhoneNumberRow` holds local `useState`:

- `code: string`
- `message: { type: 'error' | 'success', text: string } | null`

and its own `useVerifyPhone()` / `useAddPhone()` instances.

`MyProfilePage` retains: `useGetMe`, a page-level `useAddPhone` for the add-new form,
`useRemovePhone`, and `refresh = () => queryClient.invalidateQueries({ queryKey: getGetMeQueryKey() })`.
The page passes `onVerified={refresh}` and `onRemove={handleRemove}` to each row. The page
**drops** the `step`, `pendingNumber`, `code` state and the `code-sent` branch entirely.

## Handlers (in row)

- **Verify:** `verifyPhone.mutateAsync({ data: { number, code } })`.
  - Success → trigger `refresh` so the row re-renders as verified.
  - Failure → `message = { type: 'error', text: 'Invalid or expired verification code.' }`.
- **Resend:** `addPhone.mutateAsync({ data: { number } })` (backend issues a fresh code for
  the existing unverified number).
  - Success → `message = { type: 'success', text: 'New code sent.' }`.
  - Failure → `message = { type: 'error', text: 'Failed to send code.' }`.

## Add-new-number form

Stays in `MyProfilePage`, unchanged in placement. On success → `refresh()` only; no step
transition. The new number appears in the list as an unverified `PhoneNumberRow` with its
own inline code field.

## Edge cases / decisions

- **Resend rate-limit:** none server-side; out of scope. Disable the Resend button while its
  mutation `isPending` to prevent double-fire.
- **Code length:** Verify button disabled until 6 numeric digits entered (input is
  `inputMode="numeric"`, `maxLength={6}`).
- **Code expiry:** backend returns HTTP 400 ("expired"); surfaced as the row error message.
  User clicks Resend to get a new code.
- **Multiple unverified rows:** each is fully independent (own state, own mutations, own
  message).

## Testing (TDD, red/green)

New `frontend/src/components/PhoneNumberRow.test.tsx`:

- verified number → no code field; Remove present.
- unverified number → code field + Verify + Resend visible.
- enter 6-digit code + Verify → calls `verifyPhone` with `{ number, code }`.
- Verify disabled until 6 digits entered.
- Resend → calls `addPhone` with `{ number }`; shows "New code sent." success message.
- verify failure → row shows "Invalid or expired verification code."

Update `frontend/src/pages/MyProfilePage.test.tsx`:

- Drop assertions tied to the `code-sent` step.
- Add-new-number flow still submits and refreshes.
- An unverified number present in the fetched user renders an inline verify row.

## Out of scope

- Backend changes (endpoints already support verify + resend).
- Server-side resend rate-limiting.
- Changing verified-number presentation.
