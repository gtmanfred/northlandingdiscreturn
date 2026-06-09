# Disc Lifecycle & SMS Flow

How discs move through the system, when return/pickup events get created, when text
messages get sent, and the exact templates for each message.

## Disc states

There is no status enum. State is two booleans on the `Disc` model
(`backend/app/models/disc.py`):

| `is_found` | `is_returned` | Meaning |
|------------|---------------|---------|
| `true`  | `false` | Active found disc, awaiting pickup |
| `true`  | `true`  | Returned / picked up by owner |
| `false` | `false` | Wishlist disc (owner wants it, not yet found) |

A disc can have `owner_id = NULL` (anonymous). Only discs with an owner are eligible
for SMS.

## SMS send points

There are exactly **three** places an SMS is enqueued:

1. **Welcome** — fired once per owner the first time their phone number is entered
   (any disc, found or wishlist). Explains the app + how to connect their number at
   discreturn.nl.
2. **Heads-up** — fired once per owner when a *found* disc with owner info is created;
   names the found disc.
3. **Pickup notification** — fired manually by an admin per pickup event; regular or
   final-notice variant.

Both write an `SMSJob` row. A background worker polls every 10s, claims pending jobs,
and sends via the **Surge** API (`backend/app/services/surge.py`). In test mode
(`SMS_TEST_MODE=true`) only numbers in `SMS_ALLOWLIST` are actually sent; others are
silently dropped.

## Flow diagram

```mermaid
flowchart TD
    %% ----- Disc creation -----
    A[Admin: POST /discs<br/>create disc] --> B{owner first+last<br/>+ phone given?}
    B -- yes --> C[resolve_or_create owner]
    B -- no --> D[disc has no owner]
    C --> E[DiscRepository.create]
    D --> E
    E --> WEL{maybe_enqueue_welcome<br/>owner.welcome_sent_at is NULL?}
    WEL -- yes --> WG[[SMSJob: Template 0<br/>WELCOME]]
    WG --> WH[stamp owner.welcome_sent_at]
    WH --> F
    WEL -- no --> F
    F{maybe_enqueue_heads_up<br/>is_found AND<br/>owner.heads_up_sent_at is NULL?}
    F -- yes --> G[[SMSJob: Template 1<br/>HEADS-UP + disc details]]
    G --> H[stamp owner.heads_up_sent_at]
    F -- no --> I[no heads-up]

    %% ----- Disc mutation -----
    M[Admin: PATCH /discs/id] --> N[DiscRepository.update]
    N --> O[is_returned=true is a<br/>manual toggle — NO SMS]

    %% ----- Pickup event + notify -----
    P[Admin: POST /admin/pickup-events<br/>create event] --> Q[PickupEvent row<br/>notifications_sent_at = NULL]
    Q --> R[Admin: POST .../id/notify]
    R --> S{notifications_sent_at<br/>is NULL?}
    S -- no --> T[reject — can only fire once]
    S -- yes --> U[enqueue_pickup_notifications]
    U --> V[list_unreturned_found:<br/>is_found AND NOT is_returned<br/>AND owner_id NOT NULL]
    V --> W{disc already notified<br/>for this event?}
    W -- yes --> X[skip disc]
    W -- no --> Y[record DiscPickupNotification]
    Y --> Z{prior notif count + 1<br/>&gt;= 6?}
    Z -- yes --> AA[mark is_final_notice<br/>set disc.final_notice_sent]
    Z -- no --> AB[regular notice]
    AA --> AC[group discs by owner]
    AB --> AC
    AC --> AD{owner has any<br/>final-notice disc?}
    AD -- yes --> AE[[SMSJob: Template 3<br/>FINAL NOTICE]]
    AD -- no --> AF[[SMSJob: Template 2<br/>REGULAR PICKUP]]
    AE --> AG[stamp event.notifications_sent_at]
    AF --> AG

    %% ----- Worker delivery -----
    subgraph WK[Worker — every 10s]
        WG -.enqueued.-> WJ[claim pending SMSJob<br/>FOR UPDATE SKIP LOCKED]
        G -.enqueued.-> WJ
        AE -.enqueued.-> WJ
        AF -.enqueued.-> WJ
        WJ --> WS{SMS_TEST_MODE<br/>AND not in allowlist?}
        WS -- yes --> WD[drop silently]
        WS -- no --> WP[POST Surge API] --> WM[mark job sent/failed]
    end
```

## Key rules

- **Welcome is once per owner, ever** — gated on `owner.welcome_sent_at`, independent of
  `is_found`. Enqueued before heads-up, so a new found-disc owner gets welcome first,
  then heads-up (two texts).
- **Heads-up is once per owner, ever** — gated on `owner.heads_up_sent_at`, not per
  disc. Adding a second disc for the same owner sends no new heads-up.
- **Returning a disc sends nothing** — `is_returned=true` via PATCH is a silent admin
  toggle.
- **Notify fires once per event** — guarded by `notifications_sent_at`.
- **One SMS per owner per notify**, not per disc. All of an owner's eligible discs are
  listed in a single message.
- **Final notice** triggers when an individual disc's total notification count reaches
  `FINAL_NOTICE_THRESHOLD = 6`. If any of an owner's discs hits final, the owner gets
  the FINAL NOTICE template.

## Message templates

Variables shown as `{placeholder}`.

### Template 0 — Welcome

Source: `backend/app/services/welcome.py`

> Hi {name}, this is North Landing Disc Return — we reunite lost discs with their
> owners. To see what discs have been found and get pickup updates, go to discreturn.nl,
> sign up, and connect this phone number to your profile. This number isn't monitored
> for replies. Reply STOP to opt out.

- `{name}` = owner full name, e.g. `Jane Smith`.
- Fires for **any** new owner, including wishlist (`is_found=false`) discs.

### Template 1 — Heads-up

Source: `backend/app/services/heads_up.py`

> Hi {name}, this is North Landing Disc Return. We found one of your discs: {disc_desc}.
> Questions or comments? Email nldiscman@gmail.com. Reply STOP to opt out.

- `{name}` = owner full name, e.g. `Jane Smith`.
- `{disc_desc}` = `Manufacturer Name (Color)`, e.g. `Innova Destroyer (red)`.

### Template 2 — Regular pickup notification

Source: `backend/app/services/notification.py`

> Disc pickup at North Landing {window_str}. You have disc(s): {disc_list}. Questions or
> comments? Email nldiscman@gmail.com. Reply STOP to opt out.

### Template 3 — Final notice pickup notification

Source: `backend/app/services/notification.py`

> FINAL NOTICE: Your disc(s) [{disc_list}] will be added to the sale box if not picked
> up at the {window_str} pickup. Questions or comments? Email nldiscman@gmail.com. Reply
> STOP to opt out.

### Shared placeholders for Templates 2 & 3

- `{window_str}` — pickup window in `America/New_York`, e.g.
  `Jun 8 from 10:00 AM to 12:00 PM ET`.
- `{disc_list}` — comma-separated `Manufacturer Name (Color)`, e.g.
  `Innova Destroyer (Red), Discraft Buzzz (Blue)`.

## Inbound SMS

`POST /webhooks/sms` (`backend/app/routers/webhooks.py`) validates the Surge HMAC
signature and handles `message.received`. The body (including `STOP`) is currently
parsed and logged but **not** acted upon — opt-out is not yet wired to suppress sends.
