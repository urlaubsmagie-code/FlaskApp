# Email Reconciliation Pass — Design Spec

**Date:** 2026-06-09
**Status:** Approved (design); pending implementation plan
**Component:** ChatBotAI — unified inbox / message sync

## Problem

Smoobu's API + webhooks are our source of truth for guest messages, but they
demonstrably drop messages (documented Booking.com ↔ Smoobu gaps; `modifiedAt`
not bumping for owner-typed messages; historical missing-conversation issues).
We want a **third, independent reconciliation source** that backfills the gaps
without replacing what already works.

Airbnb and Booking.com each send the host a **guest-message notification email**
that arrives in Gmail (`urlaubsmagie@gmail.com`), through a different pipeline
than the Smoobu messaging API. A message Smoobu never surfaces over its API can
still land as an email. We already operate a working `GmailService`, so the raw
pipe exists.

## Goal

Add a background pass that reads Airbnb/Booking guest-message notification
emails, matches each to an existing conversation, and inserts any **guest
message we don't already have** — in correct chronological order — so the
unified inbox is complete even when Smoobu drops something.

This is a **verification / backfill step**, not a new channel. Smoobu stays the
primary source.

## Key facts established during design

- **We do NOT store the channel confirmation number.** Our DB only holds
  Smoobu's internal `Conversation.smoobu_reservation_id`. The Booking.com number
  the guest sees (e.g. `5843975682`, embedded in the `@guest.booking.com` reply
  address) and the Airbnb thread token (`…@reply.airbnb.com`) are **not stored
  anywhere**, so we cannot join the email's reservation number to a conversation
  today. Matching must use the composite of fields that ARE in both places.
- **Guest email is not a join key.** Notifications come from the platform relay
  (`@guest.booking.com`, `@reply.airbnb.com`); the guest's real email is masked.
- **Email only carries guest→host messages.** We are never emailed our own
  replies, so this backfills **guest** messages only. Owner-side gaps are out of
  scope for this feature.
- **Translation breaks exact-text dedup.** Airbnb auto-translates (observed:
  German translation + original Spanish in the same email); Smoobu may hold a
  different version. Dedup must be fuzzy (conversation + time window +
  direction), never exact-text.
- **Email timestamps are approximate** (received time, not exact send time).
  Good enough for ordering; another reason dedup can't key on exact time.
- **Plumbing already exists:** `GmailService.get_recent_emails(query=...)`
  searches with arbitrary Gmail queries and fetches full headers + body, already
  stripping quoted replies/signatures. `MessageRouter._store_message()` is an
  idempotent insertion choke point accepting a custom `sent_at` and
  `platform_message_id`. The 10-min Smoobu daemon has an obvious hook point
  right after `_reconcile_read_states()`.

## Approach (chosen)

**Backfill-only reconciliation pass.** Read-only on Gmail (no sending). Inserts
into **existing** conversations only. Runs in the existing daemon. Chosen over
(2) a full email ingestion channel with conversation-creation + reply-by-email,
and (3) an on-demand-button-only design, because it precisely matches the
"third verification step" intent, is the smallest safe change, and reuses
existing infrastructure.

## Design

### 1. Where it runs

A new function `reconcile_from_email()` invoked in the existing Smoobu daemon
loop (`app.py`), immediately after `_reconcile_read_states()`. Background,
fire-and-forget — never on a request thread (Cloudflare kills >100s routes and
it would starve Waitress threads). Bounded to the same ~90-day window as the
reservation sync; incremental on subsequent runs.

### 2. Fetch + classify (the funnel)

Targeted Gmail queries via `GmailService`:

- **Booking:** `from:guest.booking.com`
- **Airbnb:** `from:airbnb.com`, then keep only messages whose reply address is
  `@reply.airbnb.com`.

Confirmations, payouts, reviews, and reminders never match the relay domains, so
they are excluded at the query level. A structural-marker check is the final
safety net:

- Booking body opens with `##- Bitte schreiben Sie Ihre Antwort oberhalb dieser Zeile -##`.
- Airbnb body has the message-bubble layout + "direkt auf diese E-Mail antworten".

> **Build-time check:** confirm which Airbnb header carries the
> `reply.airbnb.com` address (`Reply-To` vs `From`) from a real "Show original"
> export or a live Gmail API fetch, so the query is airtight.

### 3. Parse

Per platform, extract from each email:

- The **newest** guest message text (GmailService strips quoted history).
- Guest **name** (Booking: full name; Airbnb: first name only).
- **Timestamp** from the email Date header.
- **Property name** (Booking: "Unterkunftsname"; Airbnb: subject line).
- **Dates** where present (Booking: exact check-in/check-out; Airbnb: subject
  date range).
- **Booking reference** where present (Booking only).
- The stable **Gmail message-id**, used for idempotency.

### 4. Match + confidence score

Each parsed email is scored 0–1 against candidate conversations:

- **Booking:** full name + exact check-in/check-out + property → near-unique →
  **high confidence**. If the build-time check finds Smoobu exposes the channel
  reference, we add an exact ref-join and these become **certain**.
- **Airbnb:** first name + property + date-range → **lower confidence**.

A configurable **threshold** decides auto-insert vs. queue (see §9).

### 5. Dedup (fuzzy, not exact)

A parsed message counts as "already have it" if the matched conversation has a
guest message within a small **time window**, in the **same direction**
(guest→host). Exact text comparison is NOT used (translation). Inserted email
messages carry `platform_message_id = "email:<gmail-id>"`, so
`_store_message()` blocks re-inserts on re-scan automatically.

### 6. Insert vs. review

- **Score ≥ threshold:** insert immediately via `_store_message()` with the
  synthetic id and parsed `sent_at`. Ordering by `sent_at` drops it into the
  thread chronologically with no special handling.
- **Score < threshold:** write an `EmailBackfillCandidate` row (status
  `pending`) instead of touching any thread. Rejected candidates are remembered
  (status `rejected`) so they do not re-queue on every scan.

### 7. Data model + migration (p18)

New model `EmailBackfillCandidate`:

| field | type | notes |
|---|---|---|
| `id` | int PK | |
| `gmail_message_id` | str, unique | idempotency / no re-queue |
| `platform` | str | "airbnb" \| "booking" |
| `parsed_name` | str | guest name from email |
| `parsed_text` | text | newest guest message |
| `parsed_timestamp` | datetime | from email Date header |
| `guessed_conversation_id` | int FK, nullable | best match, may be corrected on confirm |
| `confidence` | float | 0–1 |
| `status` | str | "pending" \| "confirmed" \| "rejected" |
| `created_at` | datetime | |

New `AISettings` keys:

- `email_reconcile_enabled` (default true)
- `email_confidence_threshold` (default e.g. 0.8)
- `email_autoinsert_booking` (default true)
- `email_autoinsert_airbnb` (default false) — **the toggle**: flip to true once
  Airbnb matching is trusted, which empties and retires the review tray.

### 8. UI — review tray

Its own page at `/chatbot/email-review` with a sidebar entry and a **count
badge** of pending candidates. Each row shows: parsed message text, parsed guest
name/timestamp, the guessed conversation (linked), and the confidence score.
Actions per row:

- **Confirm** → insert into the guessed conversation (with the option to correct
  the target conversation first), mark candidate `confirmed`.
- **Reject** → mark `rejected`, never re-queued.

Empty state (the end goal once Airbnb is trusted): "Nothing to review."

### 9. Configuration / extensibility

The trust behavior is driven entirely by the `AISettings` keys in §7, surfaced
in Settings. The intended evolution: as Airbnb matching becomes reliable, set
`email_autoinsert_airbnb = true` (and/or lower the threshold), at which point the
review tray naturally empties and becomes unnecessary — without a code change.

### 10. Observability

Each pass logs a one-line summary to the debug dashboard:
`scanned / matched / auto-inserted / queued / skipped-dupe / unmatched`.

## Out of scope (YAGNI for v1)

- Sending / reply-by-email-out.
- Creating brand-new conversations from an email (backfill into existing
  conversations only).
- Backfilling owner-side messages (email only carries guest→host).
- Storing/parsing for any platform other than Airbnb and Booking.com.

## Open build-time questions (resolve during implementation, not blocking design)

1. Does Smoobu's reservation payload expose the channel's external reference? If
   yes, persist it and add an exact Booking join.
2. Exact Airbnb header carrying `reply.airbnb.com` (`Reply-To` vs `From`).
3. Final default value for `email_confidence_threshold` after testing against
   real matches.
