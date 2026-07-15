# Import Preview SMS Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** In the import preview, split new discs into those that will text the owner on apply and those that won't (with a reason).

**Architecture:** Add a row-only `will_notify` predicate to `plan_import`'s created items and a `will_notify` count; render two sub-groups in `ImportPreviewDialog`.

**Tech Stack:** FastAPI/SQLAlchemy (backend), React + TS + Vitest (frontend).

## Global Constraints

- Predicate: `will_notify = (not row.returned) and bool(row.phone)`; `skip_reason` = `"returned"` if `row.returned` else `"no phone"` if not `row.phone` else `None`.
- No new DB reads in `plan_import` (it stays read-only, no writes, no SMS).
- Apply behavior is NOT changed. Only the plan's created items and the dialog change.
- Backend tests: `cd backend && teststack run -s tests -- tests/<file>.py -v` (live mount; full suite `-- -q`).
- Frontend tests: `cd frontend && npx vitest run <path>`; typecheck `npx tsc -b`.

---

### Task 1: `plan_import` created items carry `will_notify` + `skip_reason`

**Files:**
- Modify: `backend/app/services/disc_import.py` (`ImportPlan.to_dict`, `plan_import` created append)
- Test: `backend/tests/test_disc_plan.py`

**Interfaces:**
- Produces: created plan items gain `will_notify: bool`, `skip_reason: str | None`.
- Produces: `ImportPlan.to_dict()["counts"]["will_notify"]: int`.

- [ ] **Step 1: Write failing tests** — append to `backend/tests/test_disc_plan.py`:

```python
async def test_plan_created_will_notify_when_phone_and_not_returned(db):
    plan = await plan_import([_row(phone="+15551234567", returned=False)], db)
    d = plan.to_dict()
    item = d["created"][0]
    assert item["will_notify"] is True
    assert item["skip_reason"] is None
    assert d["counts"]["will_notify"] == 1


async def test_plan_created_returned_does_not_notify(db):
    plan = await plan_import(
        [_row(phone="+15551234567", returned=True, returned_date=_date(2026, 6, 5))], db
    )
    item = plan.to_dict()["created"][0]
    assert item["will_notify"] is False
    assert item["skip_reason"] == "returned"
    assert plan.to_dict()["counts"]["will_notify"] == 0


async def test_plan_created_no_phone_does_not_notify(db):
    plan = await plan_import([_row(phone=None)], db)
    item = plan.to_dict()["created"][0]
    assert item["will_notify"] is False
    assert item["skip_reason"] == "no phone"
```

- [ ] **Step 2: Run — RED**

Run: `cd backend && teststack run -s tests -- tests/test_disc_plan.py -v`
Expected: 3 new tests fail with `KeyError: 'will_notify'`.

- [ ] **Step 3: Implement** in `backend/app/services/disc_import.py`.

Add a helper above `ImportPlan`:

```python
def _notify_status(row: ParsedDiscRow) -> tuple[bool, str | None]:
    """Whether apply would text this new disc's owner, and if not, why. Row-only."""
    if row.returned:
        return False, "returned"
    if not row.phone:
        return False, "no phone"
    return True, None
```

In `ImportPlan.to_dict()`, add `will_notify` to the `counts` dict:

```python
            "counts": {
                "created": len(self.created),
                "updated": len(self.updated),
                "unchanged": self.unchanged,
                "errors": len(self.errors),
                "will_notify": sum(1 for c in self.created if c["will_notify"]),
            },
```

In `plan_import`, enrich the created append (replace the `if existing is None:` branch):

```python
        if existing is None:
            will_notify, skip_reason = _notify_status(row)
            plan.created.append(
                {**label, "will_notify": will_notify, "skip_reason": skip_reason}
            )
```

(The `label` and the `updated`/`unchanged` branches are unchanged.)

- [ ] **Step 4: Run — GREEN + full suite**

Run: `cd backend && teststack run -s tests -- tests/test_disc_plan.py -v` (all pass), then `teststack run -s tests -- -q` (no regressions).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/disc_import.py backend/tests/test_disc_plan.py
git commit -m "feat(import): flag new discs that will text owner in plan"
```

---

### Task 2: Dialog shows will-text / no-text sub-groups

**Files:**
- Modify: `frontend/src/components/ImportPreviewDialog.tsx`
- Test: `frontend/src/components/ImportPreviewDialog.test.tsx`

**Interfaces:**
- Consumes: `PlannedNew` items now carry `will_notify: boolean`, `skip_reason: string | null`.

- [ ] **Step 1: Extend the type.** In `ImportPreviewDialog.tsx`, add to `PlannedNew`:

```tsx
export type PlannedNew = {
  row_number: number
  manufacturer: string
  model: string
  colors: string[]
  owner: string | null
  will_notify: boolean
  skip_reason: string | null
}
```

- [ ] **Step 2: Write the failing test.** Update the mock `plan` in `frontend/src/components/ImportPreviewDialog.test.tsx` so the `created` array has two items — one `will_notify: true, skip_reason: null` and one `will_notify: false, skip_reason: 'returned'` — and set `counts.will_notify: 1`. Add a test:

```tsx
test('splits new discs into will-text and no-text sub-groups', () => {
  render(<ImportPreviewDialog open filename="discs.xlsx" plan={plan} busy={false}
    onApprove={() => {}} onCancel={() => {}} />)
  expect(screen.getByText(/will text owner \(1\)/i)).toBeInTheDocument()
  expect(screen.getByText(/no text \(1\)/i)).toBeInTheDocument()
  expect(screen.getByText(/returned/i)).toBeInTheDocument()
})
```

(Keep the existing created item(s) referenced by other tests valid — ensure every `created` item has the two new fields so `tsc` passes.)

- [ ] **Step 3: Run — RED**

Run: `cd frontend && npx vitest run src/components/ImportPreviewDialog.test.tsx`
Expected: new test fails (sub-group headers absent).

- [ ] **Step 4: Implement.** Replace the single New-discs `<details>` block with two sub-groups. New render (drop-in for the current `{plan.created.length > 0 && (...)}` block):

```tsx
        {plan.created.length > 0 && (() => {
          const willText = plan.created.filter((d) => d.will_notify)
          const noText = plan.created.filter((d) => !d.will_notify)
          const line = (d: PlannedNew) =>
            `${d.manufacturer} ${d.model} [${d.colors.join(' ')}]${d.owner ? ` — ${d.owner}` : ''}`
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
```

- [ ] **Step 5: Run — GREEN + regression + typecheck**

Run: `cd frontend && npx vitest run src/components/ImportPreviewDialog.test.tsx` (pass), `npx vitest run src/pages/AdminDiscsPage.test.tsx` (still passes), `npx tsc -b` (clean).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ImportPreviewDialog.tsx frontend/src/components/ImportPreviewDialog.test.tsx
git commit -m "feat(import): split preview new discs into will-text / no-text groups"
```

---

## Self-Review

- Spec coverage: predicate + counts (Task 1); two sub-groups with reason (Task 2). ✅
- Placeholders: none. ✅
- Type consistency: backend `will_notify`/`skip_reason` keys match frontend `PlannedNew` fields and the `counts.will_notify` count. ✅
