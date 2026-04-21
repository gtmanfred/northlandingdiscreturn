# Admin Disc List Filters & Status Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `is_found`/`is_returned`/`owner_name` filters to the admin `GET /discs` endpoint and enrich the admin disc table with an interactive found-toggle badge, a returned checkbox, and a filter bar.

**Architecture:** Backend adds three optional WHERE-clause filters to `DiscRepository.list_all` and `count_all`, forwarded from three new optional query params on `GET /discs`. The frontend regenerates its API client from the updated OpenAPI schema, then `AdminDiscsPage` adds filter state, a filter bar, and per-row interactive controls that call the existing `updateDisc` mutation and invalidate the list query on success.

**Tech Stack:** FastAPI, SQLAlchemy async (`ilike`), pytest-asyncio; React, TanStack Query v5, Tailwind CSS, orval-generated `northlanding.ts`.

---

## File Map

| File | Change |
|------|--------|
| `backend/app/repositories/disc.py` | Add `is_found`, `is_returned`, `owner_name` params to `list_all` and `count_all` |
| `backend/app/routers/discs.py` | Add three `Query` params to `list_discs`, forward to repo |
| `backend/tests/test_discs.py` | Add repository filter tests and endpoint filter tests |
| `frontend/openapi.json` | Regenerated (auto) |
| `frontend/src/api/northlanding.ts` | Regenerated (auto) |
| `frontend/src/pages/AdminDiscsPage.tsx` | Filter bar + `is_found` badge toggle + `is_returned` checkbox |

---

## Task 1: Repository filters — `list_all` and `count_all`

**Files:**
- Modify: `backend/app/repositories/disc.py:47-89`
- Test: `backend/tests/test_discs.py`

- [ ] **Step 1: Write the failing tests**

Add these tests at the bottom of `backend/tests/test_discs.py` (before the `# --- Endpoint tests ---` section):

```python
async def test_list_all_is_found_true(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="Found", color="W", input_date=date.today(), is_found=True)
    await repo.create(manufacturer="X", name="Wishlist", color="W", input_date=date.today(), is_found=False)
    results = await repo.list_all(is_found=True)
    assert all(d.is_found is True for d in results)
    names = [d.name for d in results]
    assert "Found" in names
    assert "Wishlist" not in names


async def test_list_all_is_found_false(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="Found2", color="W", input_date=date.today(), is_found=True)
    await repo.create(manufacturer="X", name="Wishlist2", color="W", input_date=date.today(), is_found=False)
    results = await repo.list_all(is_found=False)
    assert all(d.is_found is False for d in results)
    names = [d.name for d in results]
    assert "Wishlist2" in names
    assert "Found2" not in names


async def test_list_all_owner_name_filter(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="D1", color="W", input_date=date.today(), owner_name="Alice Smith")
    await repo.create(manufacturer="X", name="D2", color="W", input_date=date.today(), owner_name="Bob Jones")
    results = await repo.list_all(owner_name="alice")
    names = [d.name for d in results]
    assert "D1" in names
    assert "D2" not in names


async def test_list_all_combined_filters(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="Match", color="W", input_date=date.today(), is_found=True, owner_name="Carol")
    await repo.create(manufacturer="X", name="WrongOwner", color="W", input_date=date.today(), is_found=True, owner_name="Dave")
    await repo.create(manufacturer="X", name="WrongFound", color="W", input_date=date.today(), is_found=False, owner_name="Carol")
    results = await repo.list_all(is_found=True, owner_name="carol")
    names = [d.name for d in results]
    assert "Match" in names
    assert "WrongOwner" not in names
    assert "WrongFound" not in names


async def test_count_all_with_is_found_filter(db):
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="F1", color="W", input_date=date.today(), is_found=True)
    await repo.create(manufacturer="X", name="F2", color="W", input_date=date.today(), is_found=True)
    await repo.create(manufacturer="X", name="W1", color="W", input_date=date.today(), is_found=False)
    assert await repo.count_all(is_found=True) == 2
    assert await repo.count_all(is_found=False) == 1
    assert await repo.count_all() == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend
uv run pytest tests/test_discs.py::test_list_all_is_found_true tests/test_discs.py::test_list_all_is_found_false tests/test_discs.py::test_list_all_owner_name_filter tests/test_discs.py::test_list_all_combined_filters tests/test_discs.py::test_count_all_with_is_found_filter -v
```

Expected: FAIL with `TypeError: list_all() got an unexpected keyword argument 'is_found'`

- [ ] **Step 3: Implement the repository filters**

Replace `list_all` and `count_all` in `backend/app/repositories/disc.py`:

```python
async def list_all(
    self,
    *,
    page: int = 1,
    page_size: int = 50,
    is_found: bool | None = None,
    is_returned: bool | None = None,
    owner_name: str | None = None,
) -> list[Disc]:
    offset = (page - 1) * page_size
    stmt = (
        select(Disc)
        .options(selectinload(Disc.photos))
        .order_by(Disc.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    if is_found is not None:
        stmt = stmt.where(Disc.is_found == is_found)
    if is_returned is not None:
        stmt = stmt.where(Disc.is_returned == is_returned)
    if owner_name is not None:
        stmt = stmt.where(Disc.owner_name.ilike(f"%{owner_name}%"))
    result = await self.db.execute(stmt)
    return list(result.scalars().all())

async def count_all(
    self,
    *,
    is_found: bool | None = None,
    is_returned: bool | None = None,
    owner_name: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(Disc)
    if is_found is not None:
        stmt = stmt.where(Disc.is_found == is_found)
    if is_returned is not None:
        stmt = stmt.where(Disc.is_returned == is_returned)
    if owner_name is not None:
        stmt = stmt.where(Disc.owner_name.ilike(f"%{owner_name}%"))
    result = await self.db.execute(stmt)
    return result.scalar_one()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
uv run pytest tests/test_discs.py::test_list_all_is_found_true tests/test_discs.py::test_list_all_is_found_false tests/test_discs.py::test_list_all_owner_name_filter tests/test_discs.py::test_list_all_combined_filters tests/test_discs.py::test_count_all_with_is_found_filter -v
```

Expected: 5 PASSED

- [ ] **Step 5: Run the full test suite to verify no regressions**

```bash
cd backend
uv run pytest -v
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories/disc.py backend/tests/test_discs.py
git commit -m "feat: add is_found/is_returned/owner_name filters to DiscRepository.list_all and count_all"
```

---

## Task 2: Endpoint query params — `GET /discs`

**Files:**
- Modify: `backend/app/routers/discs.py:18-40`
- Test: `backend/tests/test_discs.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_discs.py` after the existing endpoint tests:

```python
async def test_admin_list_discs_is_found_filter(client, db):
    admin = await make_admin(db, name="Admin4", email="admin4@example.com", google_id="g-admin4")
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="FoundDisc", color="W", input_date=date.today(), is_found=True)
    await repo.create(manufacturer="X", name="WishlistDisc", color="W", input_date=date.today(), is_found=False)
    await db.commit()

    resp = await client.get("/discs?is_found=true", headers=admin_headers(admin.id))
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()["items"]]
    assert "FoundDisc" in names
    assert "WishlistDisc" not in names

    resp2 = await client.get("/discs?is_found=false", headers=admin_headers(admin.id))
    assert resp2.status_code == 200
    names2 = [d["name"] for d in resp2.json()["items"]]
    assert "WishlistDisc" in names2
    assert "FoundDisc" not in names2


async def test_admin_list_discs_owner_name_filter(client, db):
    admin = await make_admin(db, name="Admin5", email="admin5@example.com", google_id="g-admin5")
    repo = DiscRepository(db)
    await repo.create(manufacturer="X", name="AliceDisc", color="W", input_date=date.today(), owner_name="Alice")
    await repo.create(manufacturer="X", name="BobDisc", color="W", input_date=date.today(), owner_name="Bob")
    await db.commit()

    resp = await client.get("/discs?owner_name=alice", headers=admin_headers(admin.id))
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()["items"]]
    assert "AliceDisc" in names
    assert "BobDisc" not in names


async def test_non_admin_ignores_filter_params(client, db):
    user_repo = UserRepository(db)
    user = await user_repo.create(name="Regular2", email="reg2@example.com", google_id="g-reg2")
    await db.commit()

    # Non-admin with is_found filter — should 200 (params silently ignored, returns their discs)
    resp = await client.get("/discs?is_found=false", headers=admin_headers(user.id))
    assert resp.status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend
uv run pytest tests/test_discs.py::test_admin_list_discs_is_found_filter tests/test_discs.py::test_admin_list_discs_owner_name_filter tests/test_discs.py::test_non_admin_ignores_filter_params -v
```

Expected: FAIL (params not accepted by the endpoint yet)

- [ ] **Step 3: Add query params to the `list_discs` endpoint**

Replace the `list_discs` function in `backend/app/routers/discs.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File

@router.get("", response_model=DiscPage, operation_id="listDiscs")
async def list_discs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    page_size: int = 50,
    is_found: bool | None = Query(default=None),
    is_returned: bool | None = Query(default=None),
    owner_name: str | None = Query(default=None),
):
    repo = DiscRepository(db)
    if current_user.is_admin:
        discs = await repo.list_all(
            page=page,
            page_size=page_size,
            is_found=is_found,
            is_returned=is_returned,
            owner_name=owner_name,
        )
        total = await repo.count_all(
            is_found=is_found,
            is_returned=is_returned,
            owner_name=owner_name,
        )
    else:
        user_repo = UserRepository(db)
        phones = await user_repo.get_verified_numbers(current_user.id)
        numbers = [p.number for p in phones]
        discs = await repo.list_by_phones(numbers)
        total = await repo.count_by_phones(numbers)
    return DiscPage(
        items=[DiscOut.model_validate(d) for d in discs],
        page=page,
        page_size=page_size,
        total=total,
    )
```

Note: add `Query` to the `fastapi` import at the top of the file — the existing import line is:
```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
```
Change it to:
```python
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
uv run pytest tests/test_discs.py::test_admin_list_discs_is_found_filter tests/test_discs.py::test_admin_list_discs_owner_name_filter tests/test_discs.py::test_non_admin_ignores_filter_params -v
```

Expected: 3 PASSED

- [ ] **Step 5: Run the full test suite**

```bash
cd backend
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/discs.py backend/tests/test_discs.py
git commit -m "feat: add is_found/is_returned/owner_name query params to GET /discs admin path"
```

---

## Task 3: Regenerate the frontend API client

**Files:**
- Regenerate: `frontend/openapi.json`
- Regenerate: `frontend/src/api/northlanding.ts`

The frontend API client is generated by orval from `openapi.json`. After adding the new backend query params, we must regenerate both files so `ListDiscsParams` includes the new fields.

- [ ] **Step 1: Generate the updated OpenAPI schema**

Run from the repo root:

```bash
cd frontend && npm run generate:schema
```

This runs `uv run python scripts/generate-openapi.py` which imports the FastAPI app, exports its OpenAPI schema, and writes it to `frontend/openapi.json`.

Expected output: `Wrote /path/to/frontend/openapi.json`

- [ ] **Step 2: Verify the new params appear in openapi.json**

```bash
grep -A3 '"is_found"' frontend/openapi.json | head -20
grep '"owner_name"' frontend/openapi.json | head -5
```

Expected: the `/discs` GET endpoint parameters now include `is_found`, `is_returned`, `owner_name` as optional query params.

- [ ] **Step 3: Regenerate northlanding.ts**

```bash
cd frontend && npm run generate
```

Expected: orval reads `openapi.json` and overwrites `src/api/northlanding.ts`. No errors.

- [ ] **Step 4: Verify `ListDiscsParams` now includes the new fields**

```bash
grep -A8 "^export type ListDiscsParams" frontend/src/api/northlanding.ts
```

Expected output:
```typescript
export type ListDiscsParams = {
page?: number;
page_size?: number;
is_found?: boolean | null;
is_returned?: boolean | null;
owner_name?: string | null;
};
```

- [ ] **Step 5: Commit**

```bash
git add frontend/openapi.json frontend/src/api/northlanding.ts
git commit -m "chore: regenerate API client with is_found/is_returned/owner_name filter params"
```

---

## Task 4: Admin filter bar

**Files:**
- Modify: `frontend/src/pages/AdminDiscsPage.tsx`

Add three filter controls above the disc table: Found dropdown, Returned dropdown, Owner name text input (300ms debounced). Changing any filter resets pagination to page 1.

- [ ] **Step 1: Write the test**

Add to `frontend/src/pages/AdminDiscsPage.test.tsx` (create this file):

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { AdminDiscsPage } from './AdminDiscsPage'

// Mock the API hooks
vi.mock('../api/northlanding', () => ({
  useListDiscs: vi.fn(() => ({
    data: { items: [], total: 0, page: 1, page_size: 25 },
    isLoading: false,
  })),
  useDeleteDisc: vi.fn(() => ({ mutateAsync: vi.fn() })),
  useUpdateDisc: vi.fn(() => ({ mutateAsync: vi.fn() })),
  getListDiscsQueryKey: vi.fn(() => ['/discs']),
}))

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

test('renders filter bar with Found, Returned selects and Owner name input', () => {
  render(<AdminDiscsPage />, { wrapper })
  expect(screen.getByRole('combobox', { name: /found/i })).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: /returned/i })).toBeInTheDocument()
  expect(screen.getByPlaceholderText(/owner name/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/pages/AdminDiscsPage.test.tsx
```

Expected: FAIL — `AdminDiscsPage.test.tsx` not found or filter controls not rendered.

- [ ] **Step 3: Add filter state and filter bar to `AdminDiscsPage.tsx`**

Replace the full content of `frontend/src/pages/AdminDiscsPage.tsx`:

```tsx
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  useListDiscs,
  useDeleteDisc,
  useUpdateDisc,
  getListDiscsQueryKey,
} from '../api/northlanding'
import { LoadingSpinner } from '../components/LoadingSpinner'

export function AdminDiscsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')

  // Filter state
  const [isFoundFilter, setIsFoundFilter] = useState<boolean | undefined>(undefined)
  const [isReturnedFilter, setIsReturnedFilter] = useState<boolean | undefined>(undefined)
  const [ownerNameInput, setOwnerNameInput] = useState('')
  const [ownerNameFilter, setOwnerNameFilter] = useState<string | undefined>(undefined)

  const pageSize = 25

  // Debounce owner name 300ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setOwnerNameFilter(ownerNameInput || undefined)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [ownerNameInput])

  const { data, isLoading } = useListDiscs({
    page,
    page_size: pageSize,
    is_found: isFoundFilter,      // undefined → omitted from URL query string
    is_returned: isReturnedFilter,
    owner_name: ownerNameFilter,
  })
  const deleteMutation = useDeleteDisc()
  const updateMutation = useUpdateDisc()
  const [error, setError] = useState('')

  const handleFilterChange = (setter: (v: boolean | undefined) => void) => (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value
    setter(val === '' ? undefined : val === 'true')
    setPage(1)
  }

  const handleDelete = async (discId: string, name: string) => {
    if (!confirm(`Delete ${name}?`)) return
    setError('')
    try {
      await deleteMutation.mutateAsync({ discId })
      queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
    } catch {
      setError(`Failed to delete ${name}.`)
    }
  }

  const handleToggleIsFound = async (discId: string, current: boolean) => {
    try {
      await updateMutation.mutateAsync({ discId, data: { is_found: !current } })
      queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
    } catch {
      setError('Failed to update disc.')
    }
  }

  const handleToggleIsReturned = async (discId: string, current: boolean) => {
    try {
      await updateMutation.mutateAsync({ discId, data: { is_returned: !current } })
      queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
    } catch {
      setError('Failed to update disc.')
    }
  }

  const discs = data?.items ?? []
  const totalPages = data ? Math.ceil(data.total / pageSize) : 1

  if (isLoading) return <LoadingSpinner />

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-green-800">Discs</h1>
        <Link
          to="/admin/discs/new"
          className="bg-green-700 text-white px-4 py-2 rounded hover:bg-green-800"
        >
          + Add Disc
        </Link>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap gap-3 mb-4 items-end">
        <div>
          <label htmlFor="filter-found" className="block text-xs text-gray-500 mb-1">Found</label>
          <select
            id="filter-found"
            aria-label="Found"
            value={isFoundFilter === undefined ? '' : String(isFoundFilter)}
            onChange={handleFilterChange(setIsFoundFilter)}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm"
          >
            <option value="">All</option>
            <option value="true">Found</option>
            <option value="false">Not found</option>
          </select>
        </div>
        <div>
          <label htmlFor="filter-returned" className="block text-xs text-gray-500 mb-1">Returned</label>
          <select
            id="filter-returned"
            aria-label="Returned"
            value={isReturnedFilter === undefined ? '' : String(isReturnedFilter)}
            onChange={handleFilterChange(setIsReturnedFilter)}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm"
          >
            <option value="">All</option>
            <option value="true">Returned</option>
            <option value="false">Not returned</option>
          </select>
        </div>
        <div>
          <label htmlFor="filter-owner" className="block text-xs text-gray-500 mb-1">Owner name</label>
          <input
            id="filter-owner"
            type="text"
            placeholder="Owner name…"
            value={ownerNameInput}
            onChange={(e) => setOwnerNameInput(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm w-48"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Name / manufacturer</label>
          <input
            type="search"
            placeholder="Filter by name, manufacturer…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm w-56"
          />
        </div>
      </div>

      {error && <p className="text-red-600 text-sm mb-2">{error}</p>}

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-100 text-left">
              <th className="px-3 py-2 border border-gray-200">Photo</th>
              <th className="px-3 py-2 border border-gray-200">Disc</th>
              <th className="px-3 py-2 border border-gray-200">Color</th>
              <th className="px-3 py-2 border border-gray-200">Phone</th>
              <th className="px-3 py-2 border border-gray-200">Owner</th>
              <th className="px-3 py-2 border border-gray-200">Found</th>
              <th className="px-3 py-2 border border-gray-200">Returned</th>
              <th className="px-3 py-2 border border-gray-200">Status</th>
              <th className="px-3 py-2 border border-gray-200">Actions</th>
            </tr>
          </thead>
          <tbody>
            {discs
              .filter((d) =>
                !search ||
                d.name.toLowerCase().includes(search.toLowerCase()) ||
                d.manufacturer.toLowerCase().includes(search.toLowerCase()),
              )
              .map((disc) => (
                <tr key={disc.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2 border border-gray-200">
                    {disc.photos?.[0] ? (
                      <img src={disc.photos[0].photo_path} alt="" className="w-10 h-10 object-cover rounded" />
                    ) : (
                      <div className="w-10 h-10 bg-gray-200 rounded flex items-center justify-center text-gray-400 text-xs">No photo</div>
                    )}
                  </td>
                  <td className="px-3 py-2 border border-gray-200">
                    <span className="font-medium">{disc.name}</span>
                    <br />
                    <span className="text-gray-500">{disc.manufacturer}</span>
                  </td>
                  <td className="px-3 py-2 border border-gray-200">{disc.color}</td>
                  <td className="px-3 py-2 border border-gray-200">{disc.phone_number ?? '—'}</td>
                  <td className="px-3 py-2 border border-gray-200">{disc.owner_name ?? '—'}</td>
                  <td className="px-3 py-2 border border-gray-200">
                    <button
                      onClick={() => handleToggleIsFound(disc.id, disc.is_found)}
                      className={`px-2 py-0.5 rounded text-xs font-medium cursor-pointer border-0 ${
                        disc.is_found
                          ? 'bg-green-100 text-green-700 hover:bg-green-200'
                          : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                      }`}
                      title={disc.is_found ? 'Mark as not found' : 'Mark as found'}
                    >
                      {disc.is_found ? 'Found' : 'Not found'}
                    </button>
                  </td>
                  <td className="px-3 py-2 border border-gray-200 text-center">
                    <input
                      type="checkbox"
                      checked={disc.is_returned}
                      onChange={() => handleToggleIsReturned(disc.id, disc.is_returned)}
                      title={disc.is_returned ? 'Mark as not returned' : 'Mark as returned'}
                      className="cursor-pointer"
                    />
                  </td>
                  <td className="px-3 py-2 border border-gray-200">
                    {disc.is_returned ? (
                      <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs">Returned</span>
                    ) : disc.final_notice_sent ? (
                      <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs">Final notice</span>
                    ) : (
                      <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded text-xs">Holding</span>
                    )}
                  </td>
                  <td className="px-3 py-2 border border-gray-200 whitespace-nowrap">
                    <Link
                      to={`/admin/discs/${disc.id}/edit`}
                      className="text-blue-600 hover:underline mr-3"
                    >
                      Edit
                    </Link>
                    <button
                      onClick={() => handleDelete(disc.id, disc.name)}
                      className="text-red-500 hover:text-red-700"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex gap-2 mt-4 items-center">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 border rounded disabled:opacity-50"
          >
            ←
          </button>
          <span className="text-sm text-gray-600">Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1 border rounded disabled:opacity-50"
          >
            →
          </button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/pages/AdminDiscsPage.test.tsx
```

Expected: PASS

- [ ] **Step 5: Run the full frontend test suite**

```bash
cd frontend && npx vitest run
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AdminDiscsPage.tsx frontend/src/pages/AdminDiscsPage.test.tsx
git commit -m "feat: add filter bar and interactive found/returned controls to admin disc table"
```

---

## Final verification

- [ ] **Step 1: Start the stack and smoke-test**

```bash
docker compose up
```

Open http://localhost:5173, log in as an admin, navigate to the Discs admin page.

Verify:
1. Filter bar renders (Found dropdown, Returned dropdown, Owner name input, name/manufacturer search).
2. Selecting "Not found" from Found dropdown shows only wishlist discs.
3. Typing an owner name filters the table after ~300ms.
4. Clicking a "Found" / "Not found" badge toggles it and the row updates.
5. Checking/unchecking the Returned checkbox toggles it and the row updates.
6. Changing any filter resets to page 1.
