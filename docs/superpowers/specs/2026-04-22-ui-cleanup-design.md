# UI Cleanup — shadcn/ui Refresh

**Date:** 2026-04-22
**Scope:** Frontend visual refresh. All pages. Light mode only. Green primary preserved.

## Goal

Make the app feel like a modern web app by adopting [shadcn/ui](https://ui.shadcn.com/) as the component foundation, tightening layout and typography, and introducing a small set of shared primitives so pages look consistent.

## Non-goals

- Dark mode.
- New features, route changes, API changes, or behavior changes.
- Internationalization.
- Visual animation beyond shadcn defaults.
- Replacing Tailwind or moving off Vite/React 18.

## Current state

- Frontend: React 18, Vite 5, TypeScript, Tailwind 3.4, React Router, React Query, Orval-generated API client.
- Styling is ad-hoc Tailwind with `green-800` accents, flat white cards, utilitarian spacing, hand-rolled mobile drawer in `Navbar`.
- Pages exist in `src/pages/*`; shared bits live in `src/components/*`.
- Tests use React Testing Library with text/role queries (mostly class-agnostic, so refactors are safe).

## Foundation

1. **Dependencies** (add to `frontend/package.json`):
   - `class-variance-authority`, `clsx`, `tailwind-merge`, `tailwindcss-animate`, `lucide-react`.
   - Radix primitives pulled in by each shadcn component we add (installed transitively by `npx shadcn add`).
2. **`src/lib/utils.ts`** — export `cn()` using `clsx` + `tailwind-merge` (shadcn convention).
3. **`components.json`** at `frontend/` root — configure shadcn CLI so `npx shadcn add <name>` writes to `src/components/ui/`, with TypeScript + RSC=false + baseColor=zinc + CSS-variables=true.
4. **`tailwind.config.ts`** — adopt shadcn's theme extension: map `colors.{background, foreground, primary, secondary, muted, accent, destructive, border, input, ring, card, popover}` to HSL CSS variables. Add `tailwindcss-animate` plugin. Add `borderRadius` tokens (`--radius`).
5. **`src/index.css`** — add `:root { ... }` block defining the HSL tokens. Primary = refined green (≈ `142 70% 30%`, i.e. forest green close to today's `green-800` but slightly more saturated). No `.dark { ... }` block.

## shadcn components to install

Initial set via `npx shadcn add`: `button`, `input`, `label`, `card`, `badge`, `dialog`, `dropdown-menu`, `sheet`, `table`, `select`, `textarea`, `sonner` (toast), `skeleton`, `separator`, `avatar`, `alert`, `tabs`.

These land in `src/components/ui/` and are treated as owned code (edited as needed).

## Shared app-level primitives

New thin wrappers in `src/components/` (not in `ui/`) — each has one clear job:

- **`PageHeader`** — `{ title, description?, actions? }`. Renders an `<h1>` with consistent size/weight, optional muted description, right-aligned actions slot. Replaces every page's hand-rolled heading.
- **`EmptyState`** — `{ icon?, title, description?, action? }`. Centered, muted. Replaces "No discs found…" style divs.
- **`LoadingState`** — variant that renders `Skeleton` lines for list pages or a centered spinner for page-level loads. Replaces current `LoadingSpinner` usage in most places (the existing `LoadingSpinner` component stays until all callers migrate, then can be deleted).
- **`StatusBadge`** — `{ status: 'returned' | 'final_notice' | 'waiting' }`. Wraps shadcn `Badge` with variant + label mapping so disc status looks the same everywhere.

## Layout & Navbar

### `Layout.tsx`

- Keep `Outlet` structure.
- Page background: `bg-background` (shadcn neutral) with subtle muted surface for contrast.
- Container: `max-w-6xl mx-auto` (widened from 5xl for admin tables) with responsive padding.
- Navbar becomes sticky (`sticky top-0 z-40`) with bottom border.

### `Navbar.tsx`

- Surface: white/`bg-background` with bottom border (replaces solid green bar).
- Brand: green logo mark + wordmark on the left.
- Desktop: nav links as `NavLink` styled with shadcn `buttonVariants({ variant: 'ghost' })`, with an active-route treatment (subtle background + foreground color).
- User area: shadcn `DropdownMenu` anchored to an `Avatar` showing user initials; menu contains Profile link and Logout.
- Mobile: replace the hand-rolled drawer + escape handler + refs with shadcn `Sheet` (handles focus trap, Escape, and backdrop for free). Hamburger trigger uses `lucide-react` `Menu` icon.
- Admin links remain gated on `user?.is_admin`.

## Page-by-page changes

For each page: replace raw `<h1>` with `PageHeader`, raw "Loading…" with `LoadingState`, raw "No …" divs with `EmptyState`, status spans with `StatusBadge`, form controls with shadcn `Input`/`Label`/`Select`/`Textarea`/`Button`, destructive confirmations with `Dialog`, success/error feedback with `sonner` `toast`.

- **`LoginPage`** — centered `Card` (max-w-sm) with brand mark, headline, provider button(s) using shadcn `Button`.
- **`AuthCallbackPage`** — minimal, uses `LoadingState`.
- **`MyDiscsPage`** — `PageHeader` + responsive grid of `Card`s, each with photo, name, manufacturer, color dot, owner, `StatusBadge`. `Skeleton` grid while loading; `EmptyState` when empty.
- **`MyWishlistPage`** — same treatment as MyDiscs.
- **`MyProfilePage`** — `Card` sections (profile info, phone numbers), shadcn form controls, `Button` for save, `toast` for success/error.
- **`AdminDiscsPage`** — shadcn `Table` for results; filters in a compact toolbar above the table; row actions in `DropdownMenu`; destructive actions in `Dialog`.
- **`AdminDiscFormPage`** — one `Card` per logical section (details, photos, notes); shadcn form controls throughout; action bar at the bottom that becomes sticky on mobile.
- **`AdminPickupEventsPage`** — `Table`-based list + `Dialog` for create/edit.
- **`AdminUsersPage`** — `Table` with role toggle controls.

## Mobile

All page layouts stay responsive. Admin tables wrap in an overflow-x container so they remain usable on narrow screens without redesigning them as cards. Form action buttons on `AdminDiscFormPage` stick to the bottom on small screens.

## Testing

- Existing tests primarily use text and role queries, which survive the migration. Expected breakage:
  - Navbar tests that query the drawer or hamburger by hand-rolled markup — update selectors to shadcn `Sheet`'s generated roles.
  - MyDiscs/AdminDiscs status assertions if the status label text changes (it should not; keep the same strings in `StatusBadge`).
- No new tests written as part of this refresh; fix selectors where the DOM shape changed.
- Run `npm test` after each page migration; run the dev server and click through before declaring done.

## Sequencing

1. **Foundation** — deps, `cn`, `components.json`, tokens in Tailwind config + `index.css`, install the initial shadcn components.
2. **Shared primitives** — `PageHeader`, `EmptyState`, `LoadingState`, `StatusBadge`.
3. **Layout + Navbar** — visible payoff, touches every screen.
4. **User-facing pages** — `LoginPage`, `AuthCallbackPage`, `MyDiscsPage`, `MyWishlistPage`, `MyProfilePage`.
5. **Admin pages** — `AdminDiscsPage`, `AdminDiscFormPage`, `AdminPickupEventsPage`, `AdminUsersPage`.
6. **Cleanup** — delete now-unused `LoadingSpinner` if all callers migrated; remove stale styles; final test + visual QA pass.

## Risks / trade-offs

- **Diff size**: touches every page and the navbar. Mitigation: land in the order above so each step is reviewable on its own.
- **Test churn**: a small number of Navbar/drawer tests will need selector updates. Acceptable.
- **shadcn lock-in**: shadcn components are copied into the repo, so the project owns them — no runtime library to upgrade, but also no automatic upgrades.
- **Design decisions still to make during implementation**: exact HSL for primary green, spacing scale fine-tuning, whether to keep the solid-green brand treatment anywhere (e.g., a small header strip). These are tuned in the browser during step 3 and do not need to be resolved upfront.
