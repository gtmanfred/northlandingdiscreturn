# Inline Phone Verify & Resend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user verify or re-request a code for any unverified phone number on the profile page, not just immediately after adding it.

**Architecture:** Extract a `PhoneNumberRow` component that owns per-row code input, verify/resend mutations, and a per-row message. `MyProfilePage` maps each linked number to a row and drops its transient `code-sent` step. Backend is unchanged — `POST /me/phones` already re-issues a code for an existing unverified number, and `POST /me/phones/verify` validates it.

**Tech Stack:** React + TypeScript, TanStack Query (generated Orval hooks in `frontend/src/api/northlanding.ts`), Vitest + @testing-library/react.

---

## File Structure

- **Create:** `frontend/src/components/PhoneNumberRow.tsx` — one linked-number row. Verified → number + "Verified" + Remove. Unverified → adds code input, Verify, Resend code, per-row message.
- **Create:** `frontend/src/components/PhoneNumberRow.test.tsx` — unit tests for the row.
- **Modify:** `frontend/src/pages/MyProfilePage.tsx` — use `PhoneNumberRow`; remove `step`/`pendingNumber`/`code` state and the `code-sent` branch.
- **Create:** `frontend/src/pages/MyProfilePage.test.tsx` — page-level tests (none exists today).

### Hook signatures (from `frontend/src/api/northlanding.ts`, do not change)

- `useAddPhone()` → `UseMutationResult` with `mutateAsync({ data: { number: string } })`, `isPending`.
- `useVerifyPhone()` → `mutateAsync({ data: { number: string, code: string } })`, `isPending`.
- `useRemovePhone()` → `mutateAsync({ number: string })`.
- `useGetMe()` → `{ data, isLoading }`, `data.phone_numbers: { id, number, verified }[]`.
- `getGetMeQueryKey()` → query key for invalidation.

---

## Task 1: PhoneNumberRow component

**Files:**
- Create: `frontend/src/components/PhoneNumberRow.tsx`
- Test: `frontend/src/components/PhoneNumberRow.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/PhoneNumberRow.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PhoneNumberRow } from './PhoneNumberRow'

vi.mock('../api/northlanding', () => ({
  useVerifyPhone: vi.fn(),
  useAddPhone: vi.fn(),
}))

import { useVerifyPhone, useAddPhone } from '../api/northlanding'

const verifyMutate = vi.fn()
const addMutate = vi.fn()

beforeEach(() => {
  verifyMutate.mockReset().mockResolvedValue({})
  addMutate.mockReset().mockResolvedValue({})
  vi.mocked(useVerifyPhone).mockReturnValue({ mutateAsync: verifyMutate, isPending: false } as any)
  vi.mocked(useAddPhone).mockReturnValue({ mutateAsync: addMutate, isPending: false } as any)
})

const baseProps = {
  number: '+15551234567',
  onRemove: vi.fn(),
  onVerified: vi.fn(),
}

describe('PhoneNumberRow', () => {
  it('verified row shows no code field', () => {
    render(<PhoneNumberRow {...baseProps} verified />)
    expect(screen.getByText('Verified')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /verify/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /remove/i })).toBeInTheDocument()
  })

  it('unverified row shows code field, Verify and Resend', () => {
    render(<PhoneNumberRow {...baseProps} verified={false} />)
    expect(screen.getByText('Unverified')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^verify$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /resend code/i })).toBeInTheDocument()
  })

  it('Verify is disabled until 6 digits entered', async () => {
    const user = userEvent.setup()
    render(<PhoneNumberRow {...baseProps} verified={false} />)
    const verifyBtn = screen.getByRole('button', { name: /^verify$/i })
    expect(verifyBtn).toBeDisabled()
    await user.type(screen.getByLabelText(/verification code/i), '123456')
    expect(verifyBtn).toBeEnabled()
  })

  it('submitting the code calls verifyPhone and onVerified on success', async () => {
    const user = userEvent.setup()
    const onVerified = vi.fn()
    render(<PhoneNumberRow {...baseProps} verified={false} onVerified={onVerified} />)
    await user.type(screen.getByLabelText(/verification code/i), '123456')
    await user.click(screen.getByRole('button', { name: /^verify$/i }))
    expect(verifyMutate).toHaveBeenCalledWith({ data: { number: '+15551234567', code: '123456' } })
    expect(onVerified).toHaveBeenCalled()
  })

  it('shows an error when verify fails', async () => {
    const user = userEvent.setup()
    verifyMutate.mockRejectedValue(new Error('bad'))
    render(<PhoneNumberRow {...baseProps} verified={false} />)
    await user.type(screen.getByLabelText(/verification code/i), '000000')
    await user.click(screen.getByRole('button', { name: /^verify$/i }))
    expect(await screen.findByText(/invalid or expired verification code/i)).toBeInTheDocument()
  })

  it('Resend calls addPhone and shows a success message', async () => {
    const user = userEvent.setup()
    render(<PhoneNumberRow {...baseProps} verified={false} />)
    await user.click(screen.getByRole('button', { name: /resend code/i }))
    expect(addMutate).toHaveBeenCalledWith({ data: { number: '+15551234567' } })
    expect(await screen.findByText(/new code sent/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/PhoneNumberRow.test.tsx`
Expected: FAIL — `Failed to resolve import './PhoneNumberRow'` (component not created yet).

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/PhoneNumberRow.tsx`:

```tsx
import { useState } from 'react'
import { useVerifyPhone, useAddPhone } from '../api/northlanding'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface PhoneNumberRowProps {
  number: string
  verified: boolean
  onRemove: (number: string) => void
  onVerified: () => void
}

type Message = { type: 'error' | 'success'; text: string } | null

export function PhoneNumberRow({ number, verified, onRemove, onVerified }: PhoneNumberRowProps) {
  const verifyPhone = useVerifyPhone()
  const addPhone = useAddPhone()
  const [code, setCode] = useState('')
  const [message, setMessage] = useState<Message>(null)

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setMessage(null)
    try {
      await verifyPhone.mutateAsync({ data: { number, code } })
      setCode('')
      onVerified()
    } catch {
      setMessage({ type: 'error', text: 'Invalid or expired verification code.' })
    }
  }

  const handleResend = async () => {
    setMessage(null)
    try {
      await addPhone.mutateAsync({ data: { number } })
      setMessage({ type: 'success', text: 'New code sent.' })
    } catch {
      setMessage({ type: 'error', text: 'Failed to send code.' })
    }
  }

  return (
    <div className="rounded-md border border-border px-3 py-2">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">{number}</p>
          {verified ? (
            <p className="text-xs text-green-700">Verified</p>
          ) : (
            <p className="text-xs text-yellow-700">Unverified</p>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="text-destructive hover:text-destructive"
          onClick={() => onRemove(number)}
        >
          Remove
        </Button>
      </div>

      {!verified && (
        <form onSubmit={handleVerify} className="mt-3 space-y-2">
          <div className="flex gap-2">
            <Input
              type="text"
              inputMode="numeric"
              placeholder="123456"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              aria-label={`Verification code for ${number}`}
            />
            <Button type="submit" disabled={code.length !== 6 || verifyPhone.isPending}>
              Verify
            </Button>
            <Button type="button" variant="outline" onClick={handleResend} disabled={addPhone.isPending}>
              Resend code
            </Button>
          </div>
          {message &&
            (message.type === 'error' ? (
              <Alert variant="destructive">
                <AlertDescription>{message.text}</AlertDescription>
              </Alert>
            ) : (
              <p className="text-xs text-green-700">{message.text}</p>
            ))}
        </form>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/PhoneNumberRow.test.tsx`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/PhoneNumberRow.tsx frontend/src/components/PhoneNumberRow.test.tsx
git commit -m "feat: PhoneNumberRow with inline verify and resend"
```

---

## Task 2: Wire PhoneNumberRow into MyProfilePage

**Files:**
- Modify: `frontend/src/pages/MyProfilePage.tsx`
- Test: `frontend/src/pages/MyProfilePage.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/MyProfilePage.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MyProfilePage } from './MyProfilePage'

vi.mock('../api/northlanding', () => ({
  useGetMe: vi.fn(),
  useAddPhone: vi.fn(),
  useVerifyPhone: vi.fn(),
  useRemovePhone: vi.fn(),
  getGetMeQueryKey: () => ['/users/me'],
}))

// ApiKeyCard pulls in more hooks; stub it so this test stays focused on phones.
vi.mock('../components/ApiKeyCard', () => ({ ApiKeyCard: () => null }))

import {
  useGetMe,
  useAddPhone,
  useVerifyPhone,
  useRemovePhone,
} from '../api/northlanding'

const addMutate = vi.fn()

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
}

beforeEach(() => {
  addMutate.mockReset().mockResolvedValue({})
  vi.mocked(useAddPhone).mockReturnValue({ mutateAsync: addMutate, isPending: false } as any)
  vi.mocked(useVerifyPhone).mockReturnValue({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false } as any)
  vi.mocked(useRemovePhone).mockReturnValue({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false } as any)
  vi.mocked(useGetMe).mockReturnValue({
    isLoading: false,
    data: { name: 'Jane', email: 'jane@example.com', phone_numbers: [] },
  } as any)
})

describe('MyProfilePage', () => {
  it('renders an inline verify row for an unverified number from the server', () => {
    vi.mocked(useGetMe).mockReturnValue({
      isLoading: false,
      data: {
        name: 'Jane',
        email: 'jane@example.com',
        phone_numbers: [{ id: 'p1', number: '+15551234567', verified: false }],
      },
    } as any)
    render(<MyProfilePage />, { wrapper })
    expect(screen.getByText('+15551234567')).toBeInTheDocument()
    expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /resend code/i })).toBeInTheDocument()
  })

  it('a verified number has no code field', () => {
    vi.mocked(useGetMe).mockReturnValue({
      isLoading: false,
      data: {
        name: 'Jane',
        email: 'jane@example.com',
        phone_numbers: [{ id: 'p1', number: '+15551234567', verified: true }],
      },
    } as any)
    render(<MyProfilePage />, { wrapper })
    expect(screen.getByText('Verified')).toBeInTheDocument()
    expect(screen.queryByLabelText(/verification code/i)).not.toBeInTheDocument()
  })

  it('add-new-number form submits the normalized number', async () => {
    const user = userEvent.setup()
    render(<MyProfilePage />, { wrapper })
    await user.type(screen.getByLabelText(/area code/i), '555')
    await user.type(screen.getByLabelText(/exchange/i), '123')
    await user.type(screen.getByLabelText(/line number/i), '4567')
    await user.click(screen.getByRole('button', { name: /add phone/i }))
    expect(addMutate).toHaveBeenCalledWith({ data: { number: '+15551234567' } })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/MyProfilePage.test.tsx`
Expected: FAIL — the unverified row currently renders only "Unverified" + Remove (no code field unless `step === 'code-sent'`), so the first test fails on the missing verification-code field.

- [ ] **Step 3: Edit MyProfilePage — imports and state**

In `frontend/src/pages/MyProfilePage.tsx`, replace the hook/state block. Remove `useVerifyPhone`, `Step`, `pendingNumber`, `code`, `step`. Add the `PhoneNumberRow` import.

Replace lines beginning at the imports through the `error` state declaration with:

```tsx
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetMe,
  useAddPhone,
  useRemovePhone,
  getGetMeQueryKey,
} from '../api/northlanding'
import { PageHeader } from '../components/PageHeader'
import { LoadingState } from '../components/LoadingState'
import { PhoneInput } from '../components/PhoneInput'
import { PhoneNumberRow } from '../components/PhoneNumberRow'
import { ApiKeyCard } from '../components/ApiKeyCard'
import { normalizePhone } from '../utils/phone'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'

export function MyProfilePage() {
  const queryClient = useQueryClient()
  const { data: user, isLoading } = useGetMe()
  const addPhone = useAddPhone()
  const removePhone = useRemovePhone()
  const [newNumber, setNewNumber] = useState('')
  const [error, setError] = useState('')

  const refresh = () => queryClient.invalidateQueries({ queryKey: getGetMeQueryKey() })

  const handleAddPhone = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    let normalized: string
    try {
      normalized = normalizePhone(newNumber)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid phone number.')
      return
    }
    try {
      await addPhone.mutateAsync({ data: { number: normalized } })
      setNewNumber('')
      refresh()
    } catch {
      setError('Failed to send verification code.')
    }
  }

  const handleRemove = async (number: string) => {
    await removePhone.mutateAsync({ number })
    refresh()
  }
```

Note: the old `Input` import is dropped (the row owns its own input); keep `Label` and `Alert` for the add form.

- [ ] **Step 4: Edit MyProfilePage — replace the list and the verify-step block**

Replace the phone-list `.map(...)` block AND the `{step === 'idle' ? ... : ...}` form block with the row list plus an always-present add form. The `CardContent` body becomes:

```tsx
        <CardContent className="space-y-2">
          {user?.phone_numbers?.length ? (
            user.phone_numbers.map((p) => (
              <PhoneNumberRow
                key={p.id}
                number={p.number}
                verified={p.verified}
                onRemove={handleRemove}
                onVerified={refresh}
              />
            ))
          ) : (
            <p className="text-sm text-muted-foreground">No phone numbers linked yet.</p>
          )}

          <div className="pt-4">
            <form onSubmit={handleAddPhone} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="phone-new">Add a phone number</Label>
                <PhoneInput value={newNumber} onChange={setNewNumber} />
              </div>
              <Button type="submit" disabled={addPhone.isPending}>
                Add phone
              </Button>
            </form>
            {error && (
              <Alert variant="destructive" className="mt-3">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
        </CardContent>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/MyProfilePage.test.tsx src/components/PhoneNumberRow.test.tsx`
Expected: PASS (all tests in both files).

- [ ] **Step 6: Typecheck and lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors. (Confirms the removed `useVerifyPhone`/`Input`/`Step` references are fully gone.)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/MyProfilePage.tsx frontend/src/pages/MyProfilePage.test.tsx
git commit -m "feat: inline verify and resend for unverified phone numbers"
```

---

## Self-Review

- **Spec coverage:**
  - Inline verify/resend per unverified row → Task 1 (component) + Task 2 (wiring). ✓
  - Drop `code-sent` step, add-new just refreshes → Task 2 Steps 3-4. ✓
  - Per-row state/message, own mutations → Task 1 component. ✓
  - Verify disabled until 6 digits → Task 1 (`disabled={code.length !== 6 ...}`) + test. ✓
  - Resend disabled while pending → Task 1 (`disabled={addPhone.isPending}`). ✓
  - Testing: PhoneNumberRow.test.tsx + MyProfilePage.test.tsx → both created. ✓
- **Placeholder scan:** none — all steps contain full code/commands.
- **Type consistency:** `onVerified`/`onRemove` prop names match between component, page wiring, and tests. `mutateAsync` payloads match generated hook signatures (`{ data: { number, code } }`, `{ data: { number } }`, `{ number }`).
- **Spec deviation noted:** spec said "update `MyProfilePage.test.tsx`"; that file does not exist, so Task 2 creates it and stubs `ApiKeyCard` to keep the page test focused.
