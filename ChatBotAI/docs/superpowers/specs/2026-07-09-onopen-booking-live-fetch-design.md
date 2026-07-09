# On-open live Booking email fetch — Design

**Date:** 2026-07-09
**Status:** Approved (pending spec review)
**Area:** ChatBotAI email reconciliation (`email_reconcile.py`, `routes.py`, `conversation.js`)

## Problem

Smoobu's Booking.com connectivity link lacks the messaging scope (confirmed with
Smoobu support — the Booking.com extranet "Was darf Smoobu verwalten?" list has no
Messages entry). So Booking guest messages never arrive through the Smoobu API.
Booking.com does email a notification (`@guest.booking.com`) for every guest
message, and `email_reconcile.py` already scrapes those into conversations via a
periodic background scan over *all* recent Booking + Airbnb emails.

We want the reconciliation to (1) target Booking only, and (2) additionally fetch
live, per-conversation, the moment a chat is opened — "open the chat → call the
Google API → pull that chat's Booking emails in."

## Key constraint (established during design)

There is **no stored Booking.com reservation number** to search by. The
conversation stores `smoobu_reservation_id` (Smoobu's internal id) and
`guest.booking_id` is also just the Smoobu id — neither equals the "Buchungsnummer"
in the `@guest.booking.com` emails. Therefore the per-chat Gmail search is anchored
on **guest name**, and matches are scored on **name + stay dates + apartment code**
— exactly the signals `score_conversation_match` already uses today.

## Decisions

- **Augment, not replace.** Keep the background scan but make it Booking-only; add
  the live on-open fetch on top.
- **Auto, throttled, async.** The live fetch fires automatically on chat open,
  skips if the same chat was live-fetched within the last N minutes (default 15),
  and runs async so it never blocks the thread from rendering.
- **Always auto-insert positive matches.** The live path inserts every match
  directly into the chat — no review tray. "Match" = `score_conversation_match > 0`.
  Anti-spoof (DKIM/DMARC via `verify_sender_authenticity`) and dedup
  (`has_equivalent_message` + global `email:{gmail_id}` guard) remain mandatory.

## Design

### 1. Background scan → Booking-only

In `reconcile_from_email`, restrict the platform loop to Booking:

```python
_PLATFORM_SENDER = {'booking': 'from:guest.booking.com'}
```

Airbnb parsing/scoring functions stay in the module (still unit-tested, harmless)
but nothing calls them from the scan. Net effect: the periodic scan only ever
queues/inserts Booking messages.

### 2. New: `fetch_booking_for_conversation(gmail, conversation_id) -> dict`

`reconcile_from_email` scoped to one chat:

1. Load conversation + guest. Return `{'inserted': 0, 'reason': 'not_booking'}` if
   `resolve_channel(conv) != 'booking'` or the guest has no name — no Gmail call
   wasted on Airbnb/Smoobu chats.
2. Build a single-conversation view (same dict shape `_candidate_views` produces).
3. Query Gmail:
   `from:guest.booking.com "<safe guest name>" newer_than:{days}d`
   (reuse `_safe_query_term`; `days` from `get_reconcile_config()`).
4. For each email, run the shared per-email handler (below) with
   `auto_insert_all=True`.

Returns `{'inserted': N, 'scanned': M, 'skipped_dupe': K, 'rejected_unauthenticated': R}`.

### 3. Shared per-email handler (refactor to avoid duplication)

Extract the current per-email body of `reconcile_from_email` into:

```python
def _handle_booking_email(email, views, cfg, router, stats, auto_insert_all):
    ...
```

Both the scan and the live fetch call it. Pipeline is unchanged:
`parse_booking_notification` → skip if no text/date → `verify_sender_authenticity`
(drop if not authentic) → skip if already an `EmailBackfillCandidate` or already
inserted (`email:{gmail_id}`) → `pick_best_match`/`score_conversation_match` →
`has_equivalent_message` dedup.

Insert-vs-queue branch:
- **Scan path** (`auto_insert_all=False`): unchanged — auto-insert if
  `score >= threshold and autoinsert_booking`, else queue candidate.
- **Live path** (`auto_insert_all=True`): auto-insert if `score > 0`, never queue.

### 4. Throttle + trigger

- **Throttle:** module-level `_last_live_fetch: dict[int, datetime]`. Skip the
  fetch if the conversation was fetched within `email_onopen_live_throttle_minutes`
  (default 15). In-memory is adequate for a throttle — a server restart at worst
  permits one extra fetch. `# ponytail: in-memory throttle; move to a Conversation
  column only if multi-worker fetches become a quota problem`.
- **Endpoint:** `POST /api/conversation/<id>/fetch-booking-live` (mirrors the
  existing `recover-emails` route). Gated on `email_onopen_live_enabled` (default
  `'true'`) + Gmail connected. Applies the throttle, calls
  `fetch_booking_for_conversation`, returns `{'success': True, 'inserted': N}`.
  Never raises to the client (matches the existing on-open promote's
  failure-is-silent contract).
- **Client:** `conversation.js` fires this endpoint once on page load, async, after
  the thread renders. If `inserted > 0`, reload/append the thread so the new
  Booking messages appear a moment later.

### 5. Settings (AISettings keys)

| Key | Default | Purpose |
|-----|---------|---------|
| `email_onopen_live_enabled` | `'true'` | Master toggle for the live on-open fetch |
| `email_onopen_live_throttle_minutes` | `'15'` | Per-chat throttle window |

Reuses existing `email_reconcile_days` (search window) and the existing scorer /
threshold config. The existing DB-only on-open promotion
(`email_autoinsert_on_open` / `promote_email_candidates`) is left in place.

## Out of scope

- No Booking.com reservation-number storage or ref-based matching (no such id is
  stored; name+dates+apartment is the anchor). A future step if name collisions
  prove to be a problem.
- No change to the Airbnb parsing code itself (only its removal from the scan loop).
- No change to the review-tray UI or the background daemon scheduling.

## Verification

One `test_onopen_booking_live.py`:
- Scan emits only the Booking query, no Airbnb query (`platform_queries` /
  `_PLATFORM_SENDER` is Booking-only).
- `fetch_booking_for_conversation` inserts a matching authenticated Booking email
  into the chat.
- No-op on a non-Booking conversation.
- No-op when called again within the throttle window.
- A same-name / different-apartment email (score 0.0) is **not** inserted.
