# North Landing Disc Return — Design Spec

**Date:** 2026-04-19  
**Status:** Approved

## Context

North Landing disc golf course recovers discs from the course and lake. Staff need a way to log recovered discs, match them to owners by phone number, notify owners about scheduled pickup events, and track whether discs have been returned. Users (disc owners) should be able to log in via Google, link their phone number, and see which of their discs the course is holding.

---

## Architecture

**Option chosen:** API-first Layered Monolith

- Single FastAPI application with layers: routers → services → repositories → models
- Separate Fly.io worker process for SMS notification jobs (shares same models/DB config)
- Supabase for Postgres database and file storage (disc photos)
- React + Vite frontend, statically hosted on GitHub Pages
- Frontend fetches all data via an OpenAPI-generated TypeScript client

---

## Repository Structure (Monorepo)

```
northlandingdiscreturn/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory
│   │   ├── config.py            # Settings via pydantic-settings
│   │   ├── database.py          # Async SQLAlchemy engine + session
│   │   ├── models/              # ORM models
│   │   │   ├── disc.py
│   │   │   ├── user.py
│   │   │   ├── phone.py
│   │   │   └── pickup_event.py
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── routers/             # FastAPI routers
│   │   │   ├── auth.py
│   │   │   ├── discs.py
│   │   │   ├── users.py
│   │   │   ├── admin.py
│   │   │   └── webhooks.py
│   │   ├── services/            # Business logic
│   │   └── repositories/       # DB query layer
│   ├── worker/
│   │   └── main.py              # Polls SMSJob queue + APScheduler for future scheduled jobs
│   ├── alembic/                 # DB migrations
│   ├── Dockerfile
│   ├── Dockerfile.worker
│   ├── fly.toml
│   └── fly.worker.toml
├── frontend/
│   ├── src/
│   │   ├── api/                 # OpenAPI-generated TypeScript client (auto-generated)
│   │   ├── pages/
│   │   │   ├── AdminDiscs.tsx
│   │   │   ├── AdminPickupEvents.tsx
│   │   │   ├── AdminUsers.tsx
│   │   │   ├── UserDiscs.tsx
│   │   │   ├── UserWishlist.tsx
│   │   │   ├── UserProfile.tsx
│   │   │   └── Login.tsx
│   │   └── components/
│   ├── vite.config.ts
│   └── Dockerfile              # nginx serving static build (for local dev)
├── docker-compose.yml
└── .github/workflows/
    ├── deploy-frontend.yml      # Build + deploy to GitHub Pages
    └── deploy-backend.yml       # Build Docker + fly deploy
```

---

## Data Models

### User
```
id              UUID PK
name            str
email           str (unique — from Google OAuth)
google_id       str (unique)
is_admin        bool (default False)
created_at      datetime
```

### PhoneNumber
```
id                  UUID PK
user_id             FK → User
number              str (E.164 format, e.g. +15551234567)
verified            bool (default False)
verification_code   str (nullable — temporary 6-digit code)
verification_expires_at  datetime (nullable — 10-minute TTL)
verified_at         datetime (nullable)
UNIQUE constraint:  (user_id, number)
```

Note: The same phone number can be linked to multiple users (e.g. family members). The unique constraint is per-user, not global.

### Disc
```
id                  UUID PK
manufacturer        str
name                str
color               str
owner_name          str (nullable — typed at disc entry, may be updated later)
phone_number        str (nullable — E.164, used to match PhoneNumber records)
is_clear            bool
input_date          date
is_found            bool (False = wishlist entry for a lost disc not yet recovered)
is_returned         bool
final_notice_sent   bool (True after 6th pickup notification — convenience flag)
created_at          datetime
updated_at          datetime
```

### DiscPhoto
```
id              UUID PK
disc_id         FK → Disc
photo_path      str (Supabase Storage object path)
uploaded_at     datetime
sort_order      int
```

### PickupEvent
```
id                      UUID PK
scheduled_date          date
notes                   str (nullable)
notifications_sent_at   datetime (nullable — set when admin triggers notifications)
created_at              datetime
```

### DiscPickupNotification
```
id                  UUID PK
disc_id             FK → Disc
pickup_event_id     FK → PickupEvent
is_final_notice     bool
sent_at             datetime
```

### SMSJob (worker queue)
```
id              UUID PK
phone_number    str (E.164 — recipient)
message         str (full SMS body, composed by API at enqueue time)
status          enum: pending | processing | sent | failed
created_at      datetime
processed_at    datetime (nullable)
error           str (nullable — Twilio error message on failure)
```

---

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/google` | Redirect to Google OAuth |
| GET | `/auth/google/callback` | Exchange code, create/update User, return JWT |
| POST | `/auth/logout` | Clear session |

### Users (authenticated)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/users/me` | Current user profile + linked phones |
| POST | `/users/me/phones` | Initiate phone verification (sends Twilio code) |
| POST | `/users/me/phones/verify` | Confirm code, link phone to account |
| DELETE | `/users/me/phones/{number}` | Remove linked phone |

### Discs (admin: write; authenticated: read own)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/discs` | Paginated list (admin: all; user: matched by phone) |
| POST | `/discs` | Create disc (admin only) |
| PATCH | `/discs/{id}` | Update disc fields (admin only) |
| DELETE | `/discs/{id}` | Delete disc (admin only) |
| POST | `/discs/{id}/photos` | Upload photo (multipart, admin only) |
| DELETE | `/discs/{id}/photos/{photo_id}` | Delete photo (admin only) |

### Wishlist (authenticated)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/users/me/wishlist` | User's wishlist entries |
| POST | `/users/me/wishlist` | Add wishlist entry |
| DELETE | `/users/me/wishlist/{id}` | Remove wishlist entry |

### Admin
| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/users` | List all users |
| PATCH | `/admin/users/{id}` | Update user (e.g. promote to admin) |
| GET | `/admin/users/{user_id}/wishlist` | View user's wishlist |
| POST | `/admin/users/{user_id}/wishlist` | Add wishlist entry on behalf of user |
| DELETE | `/admin/users/{user_id}/wishlist/{id}` | Remove wishlist entry |
| GET | `/admin/pickup-events` | List pickup events |
| POST | `/admin/pickup-events` | Create pickup event |
| PATCH | `/admin/pickup-events/{id}` | Update pickup event |
| POST | `/admin/pickup-events/{id}/notify` | Send SMS to all users with unreturned discs |

### Webhooks
| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhooks/twilio` | Receive inbound Twilio SMS (validated by Twilio signature) |

---

## Auth & Security

- **Session:** JWT access token (1hr) issued at OAuth callback; refresh token in HttpOnly cookie
- **Admin access:** `is_admin=True` on User; first admin set manually in DB; subsequent admins promoted via `PATCH /admin/users/{id}`
- **Phone verification flow:**
  1. User POSTs phone number → 6-digit code generated, stored with 10-min TTL, sent via Twilio
  2. User POSTs code → verified, `PhoneNumber.verified=True` set
  3. All discs with matching `phone_number` are now visible to the user
- **Twilio webhook:** Validated using Twilio request signature header before processing

---

## SMS Notification Flow (Pickup Events)

When admin calls `POST /admin/pickup-events/{id}/notify`, the API returns immediately (202 Accepted) and the worker handles all Twilio sends:

**API (synchronous, fast):**
1. Query all discs: `is_found=True`, `is_returned=False`, not already in a `DiscPickupNotification` for this event
2. For each disc, count total prior `DiscPickupNotification` rows → if count == 5 (this is the 6th), mark as final notice
3. Write `DiscPickupNotification` records and set `Disc.final_notice_sent=True` for final notice discs
4. Group discs by `phone_number`, compose SMS message body for each group:
   - Standard: "Disc pickup scheduled for [date]. You have [N] disc(s): [list]. Reply STOP to opt out."
   - Final notice: "Final notice: your disc(s) will be added to the sale box if not picked up by [date]."
5. Insert one `SMSJob` row (status=`pending`) per phone number group
6. Set `PickupEvent.notifications_sent_at=now()`
7. Return 202 with count of SMS jobs enqueued

**Worker (polls `SMSJob` table every 10 seconds):**
1. SELECT jobs WHERE `status='pending'` FOR UPDATE SKIP LOCKED (prevents double-processing)
2. Set `status='processing'`
3. Send via Twilio; on success set `status='sent'`, `processed_at=now()`
4. On Twilio error set `status='failed'`, `error=<message>`

The same worker process also handles any future scheduled jobs (e.g. automated reminders) via APScheduler.

---

## Frontend Pages

| Route | Page | Access |
|-------|------|--------|
| `/` | Landing / Login (Google OAuth button) | Public |
| `/admin/discs` | Disc management table (CRUD, photo upload, filter/sort) | Admin only |
| `/admin/discs/new` | Add disc form | Admin only |
| `/admin/pickup-events` | Create/manage pickup events, trigger SMS | Admin only |
| `/admin/users` | User list, promote to admin | Admin only |
| `/my/discs` | My discs (read-only, matched by linked phones) | Authenticated |
| `/my/wishlist` | My wishlist (add/remove lost disc entries) | Authenticated |
| `/my/profile` | Profile, link/remove phone numbers | Authenticated |

**Frontend tech:**
- React + Vite
- React Router for client-side routing
- React Query for data fetching and cache management
- `orval` generates typed TypeScript API client from FastAPI `/openapi.json`
- Tailwind CSS for styling
- Drag-and-drop multi-photo upload on disc form

---

## Deployment & Infrastructure

### Fly.io (backend)
- `northlandingdiscreturn-api` — FastAPI app
- `northlandingdiscreturn-worker` — APScheduler worker (pickup notifications)
- Alembic migrations run as Fly release command before API starts

### GitHub Pages (frontend)
- Vite build deployed via `actions/deploy-pages`
- Default URL: `https://gtmanfred.github.io/northlandingdiscreturn`
- Custom domain configurable in repo settings

### Supabase
- Postgres database (connection via `DATABASE_URL`)
- Storage bucket for disc photos (accessed via `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`)
- Backend generates presigned URLs for photo access

### Environment Secrets
```
DATABASE_URL                  Supabase Postgres connection string
SUPABASE_URL                  Supabase project URL
SUPABASE_SERVICE_KEY          Supabase service role key (for storage)
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_FROM_NUMBER            E.164 format Twilio phone number
JWT_SECRET                    Random secret for JWT signing
```

### CI/CD (GitHub Actions)
- **`deploy-frontend.yml`:** On push to `main` → `npm run build` → deploy to GitHub Pages
- **`deploy-backend.yml`:** On push to `main` → build Docker images → `fly deploy` for API and worker

---

## Local Development

`docker-compose.yml` provides:
- `api` — FastAPI app with hot reload
- `worker` — Worker process
- `frontend` — Vite dev server (proxies `/api` to local FastAPI)
- External: Supabase cloud (or local Supabase CLI)

---

## Testing Strategy

- **Backend:** pytest + pytest-asyncio; repositories tested against a real Postgres test DB; services tested with repository mocks
- **Frontend:** Vitest for unit tests; API client generated and type-checked; React Testing Library for component tests
- **Integration:** Docker Compose used locally to verify end-to-end flows
