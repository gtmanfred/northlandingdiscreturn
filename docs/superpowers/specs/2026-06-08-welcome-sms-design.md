# Welcome SMS + Heads-up Rework — Design

Date: 2026-06-08

## Goal

When a new owner's phone number is entered for the first time, send a one-time
**welcome** SMS explaining what the app is and how to connect their phone number to a
profile at discreturn.nl. Separately, rework the existing **heads-up** SMS so it carries
only "we found your disc" info (intro/cadence text moves to the welcome message) and now
includes the found disc's details.

## Background

Current SMS send points (`docs/disc-sms-flow.md`):
1. **Heads-up** — fired once per owner on first found disc with owner info. Gated on
   `owner.heads_up_sent_at is None` AND `is_found=True`.
2. **Pickup notifications** — admin-triggered per pickup event.

This change adds a third send point (welcome) and reworks heads-up copy.

## Behavior

### Welcome SMS (new)

- **Trigger:** `POST /discs` creates/resolves an owner with a phone number.
- **Condition:** `owner.welcome_sent_at is None`. Fires once per owner, ever.
  Independent of `is_found` — wishlist owners (`is_found=False`) get it too.
- **Ordering:** enqueued **before** heads-up in `create_disc`, so its `SMSJob` row is
  inserted first and the worker (FIFO claim) sends it first.
- **Dedup:** new nullable column `owners.welcome_sent_at`, stamped `now()` on send,
  mirroring `heads_up_sent_at`.

For a brand-new owner whose first disc is found, both welcome and heads-up fire — two
texts, welcome first. This is intended.

### Heads-up SMS (reworked)

- **Trigger / condition unchanged:** once per owner, `is_found=True`,
  `heads_up_sent_at is None`.
- **Copy change:** drop the app-intro and pickup-cadence sentences. Add the found
  disc's details.
- **Signature change:** `maybe_enqueue_heads_up` takes the `disc` object (for
  manufacturer/name/color and `is_found`) instead of a bare `is_found` bool.

## Templates

### Welcome (`app/services/welcome.py`)

```
Hi {name}, this is North Landing Disc Return — we reunite lost discs with their owners. To see what discs have been found and get pickup updates, go to discreturn.nl, sign up, and connect this phone number to your profile. Reply STOP to opt out.
```

- `{name}` = `owner.name`.

### Heads-up (`app/services/heads_up.py`, replaces current text)

```
Hi {name}, this is North Landing Disc Return. We found one of your discs: {disc_desc}. Reply STOP to opt out.
```

- `{name}` = `owner.name`.
- `{disc_desc}` = `f"{manufacturer} {name} ({color})"`, e.g. `Innova Destroyer (Red)` —
  same format as pickup-notification disc lists.

## Components

1. **Model** — `app/models/owner.py`: add
   `welcome_sent_at: Mapped[datetime | None]` (timezone-aware, nullable).
2. **Migration** — new Alembic revision adding `owners.welcome_sent_at`.
3. **Repository** — `OwnerRepository.mark_welcome_sent(owner)`, mirroring
   `mark_heads_up_sent`.
4. **Service (new)** — `app/services/welcome.py`:
   `WELCOME_TEMPLATE`, `async def maybe_enqueue_welcome(*, owner, db) -> bool`. Gate on
   `welcome_sent_at is None`; enqueue `SMSJob` via
   `PickupEventRepository(db).create_sms_job(...)`; call `mark_welcome_sent`.
5. **Service (rework)** — `app/services/heads_up.py`: change `HEADS_UP_TEMPLATE`; change
   `maybe_enqueue_heads_up` signature to `(*, owner, disc, db)`; build `disc_desc` and
   read `is_found` from `disc`.
6. **Router** — `app/routers/discs.py` `create_disc`: after disc create, when
   `owner_obj is not None`, call `maybe_enqueue_welcome(owner=owner_obj, db=db)` then
   `maybe_enqueue_heads_up(owner=owner_obj, disc=disc, db=db)`.
7. **Docs** — update `docs/disc-sms-flow.md`: add welcome to the flow diagram + a new
   template section; update heads-up template text.

## Testing (TDD)

- Welcome enqueued on first owner creation; `welcome_sent_at` stamped.
- Welcome NOT re-enqueued when `welcome_sent_at` already set.
- Welcome fires for wishlist owner (`is_found=False`).
- Welcome enqueued before heads-up (row order / sent order).
- Heads-up message contains the disc description.
- Heads-up still gated on `is_found` and `heads_up_sent_at`.

## Out of scope

- No change to pickup notifications, inbound STOP handling, or the worker.
- No retroactive welcome for existing owners (only fires on next owner-creation touch
  where `welcome_sent_at is None`; existing owners have it NULL, so a future disc add
  for them would trigger a welcome — acceptable).
