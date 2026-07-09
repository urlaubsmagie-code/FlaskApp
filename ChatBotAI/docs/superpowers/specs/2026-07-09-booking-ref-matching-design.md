# Reservation-number matching for the on-open Booking fetch — Design

**Date:** 2026-07-09
**Status:** Approved (pending spec review)
**Area:** ChatBotAI email reconciliation — live per-chat Booking fetch
**Builds on:** `2026-07-09-onopen-booking-live-fetch-design.md` (the on-open live fetch this refines)

## Problem

The on-open live Booking fetch inserts a guest's `@guest.booking.com` messages when
you open their chat. It works mechanically, but in practice it doesn't deliver
messages in two situations:

1. **Already mis-filed.** The background scan may have already parsed the email and
   queued it as a low-confidence `EmailBackfillCandidate` against the *wrong*
   conversation. The live path then finds the email but **skips it** (its
   "already a candidate → skip" guard), so it never reaches the correct chat.
2. **Apartment-veto false negatives.** The live path inserts on `score > 0`, and
   `score_conversation_match` applies a −0.5 soft-veto when the email's apartment
   (Booking's marketing/concept name) doesn't map to the conversation's code. The
   Booking concept-name mapping is incomplete, so legitimate matches get vetoed to
   `0.0` and are not inserted.

**Concrete case:** Michael Werner, conv 2520 (apartment B5, stay 10.–12.07). His
Booking message ("Ich möchte einen Check-in um 16:00–17:00 Uhr…") was parsed by the
scan and queued as a **pending** candidate against conv 2057 (a different guest) at
confidence 0.15, because B5's concept name didn't map. Opening 2520 logged
`scanned: 1, auto_inserted: 0` — the email was found but skipped as an existing
candidate.

## Key insight

Every Booking reservation has a **Buchungsnummer** (Booking's confirmation number)
that is an **exact, shared key** across all systems:

- **The email:** `parse_booking_notification` already extracts it as `booking_ref`
  (from the `<ref>-…@guest.booking.com` sender and the "Buchungsnummer" body field).
- **Smoobu:** the reservation object exposes it as the structured field
  `reference-id`. Verified: reservation 146578501 → `reference-id = '5110199521'` =
  the email's `booking_ref`.
- **Our DB:** already stored for **~92% of Booking chats** inside the guest note
  (`GuestDetail` `guest_note`), verbatim as `Buchungsnummer: 5110199521\n…`. It is
  written during Smoobu enrichment — the same sync that creates the chat — so **new
  reservations get it automatically**, not just historical ones.

Matching on this number is **exact** (not fuzzy), so it needs no apartment mapping,
no date guessing, and no same-name disambiguation — and a wrong/stale number simply
fails to match and falls through, so it can never cause a wrong-chat insert.

## Design

When the on-open live fetch runs for a conversation, for each `@guest.booking.com`
email the name-scoped Gmail search returns, decide "does this email belong to this
chat?" with a **three-tier match**, fast → authoritative → fuzzy:

### Tier 1 — Buchungsnummer from the stored note (free, no API)
Read the conversation guest's `guest_note` detail; extract the number with
`re.search(r'Buchungsnummer:\s*(\d+)', note)`. If it equals the email's `booking_ref`
→ **match**. Covers ~92% incl. all newly-synced reservations.

### Tier 2 — Smoobu `reference-id` (authoritative, one API call)
Only if Tier 1 produced no number: fetch `get_reservation(conv.smoobu_reservation_id)`
and read `reference-id`. If it equals the email's `booking_ref` → **match**. Present
for every Booking reservation, so this closes the ~8% note gap and any repeat-guest
note staleness. The call is made at most once per chat-open (the fetch is already
throttled to 15 min); a Smoobu failure is non-fatal and drops to Tier 3.

### Tier 3 — name + exact dates (fuzzy safety net)
If neither side yields a Buchungsnummer: the guest name already matches (the Gmail
search is name-scoped), so require the email's `check_in` **and** `check_out` to
equal the conversation's `check_in`/`check_out` exactly. Both must match (check-in
alone is what mis-filed Michael to a 6-night stay).

An email that matches on **any** tier is inserted into the open conversation.

### Rescue mis-filed candidates
The live path stops unconditionally skipping already-queued emails. Instead: if a
matched email is currently an `EmailBackfillCandidate` (any `guessed_conversation_id`),
insert it into **this** conversation and set that candidate's `status='confirmed'`,
so it leaves the review tray and cannot be promoted into the wrong chat later. This
is the change that delivers Michael's message.

### Guards kept (non-negotiable)
- **Anti-spoof:** `verify_sender_authenticity` (DKIM/DMARC) still runs first; spoofed
  mail is dropped before any matching.
- **No true duplicates:** the global `Message.platform_message_id == "email:{id}"`
  guard still skips an email already inserted anywhere, and `has_equivalent_message`
  still guards the ±window against a Smoobu-origin copy.

### Scope
Applies to the **whole live path** (`auto_insert_all=True`) — the tiered match
replaces the `score > 0` rule for every email the search returns, fresh or mis-filed.
The **background scan is unchanged** (still threshold + review-tray).

## Components

- `email_reconcile.py`
  - `booking_ref_from_note(guest_id) -> str | None` — Tier 1 extractor.
  - `conversation_booking_ref(conv, smoobu_service=None) -> str | None` — Tier 1,
    then Tier 2 (lazy Smoobu call) if needed.
  - `email_matches_conversation(notif, conv, conv_ref) -> bool` — the tier decision
    (ref exact-match, else name+exact-dates).
  - Rework the `auto_insert_all` branch of `_handle_notification_email` (or a
    dedicated live handler): drop the skip-if-candidate guard, apply
    `email_matches_conversation`, and mark any existing candidate `confirmed` on
    insert.
  - `fetch_booking_for_conversation` resolves `conv_ref` once (Tier 1/2) and passes
    it into the per-email handling; obtains a Smoobu service lazily via
    `get_smoobu_service()` only when Tier 1 is empty.

## Data flow

```
open chat → fetch_booking_for_conversation(conv)
  conv_ref = conversation_booking_ref(conv)      # note → (smoobu reference-id)
  emails = gmail.search(from:guest.booking.com "<name>" newer_than:30d)
  for email:
    notif = parse_booking_notification(email)    # has booking_ref, dates
    verify_sender_authenticity(...)              # drop spoof
    if Message email:{id} exists: skip
    if email_matches_conversation(notif, conv, conv_ref):
        insert message (email:{id})
        mark EmailBackfillCandidate(gmail_id) confirmed, if any
```

## Edge cases

- Email `booking_ref` unparsable → Tiers 1–2 can't match on number → Tier 3.
- Conversation has no `smoobu_reservation_id` → Tier 2 unavailable → Tier 3.
- Smoobu API error/timeout → log, skip Tier 2 → Tier 3.
- Repeat guest whose note holds a *newer* reservation's number → Tier 1 mismatch →
  Tier 2 authoritative (or Tier 3). Never a wrong insert (exact match).
- Guest has several unread Booking messages → each email evaluated independently;
  all matching ones inserted.
- Conversation lacks stay dates → Tier 3 cannot confirm → email not inserted (safe;
  Tiers 1–2 still can).

## Out of scope

- Fixing the Booking concept-name → apartment-code mapping (separate task; this
  design sidesteps it entirely by matching on the reservation number).
- Backfilling a dedicated `booking_ref` column / migration — not needed; the note is
  already stored and Smoobu is authoritative on demand.
- Changing the background scan or the review-tray UI.

## Verification

- Unit: `email_matches_conversation` — ref exact-match true; ref mismatch + dates
  match true; ref mismatch + dates mismatch false; no-ref + name+exact-dates true;
  no-ref + check-in-only-match false. `booking_ref_from_note` extracts `5110199521`
  from a real note string and returns None on absent/garbled notes.
- Integration (the Michael case): a pending candidate for the email exists against
  the *wrong* conversation; `fetch_booking_for_conversation` on the *right*
  conversation (whose note carries the matching Buchungsnummer) inserts the message
  and flips the candidate to `confirmed`.
- Tier 2: Smoobu service mocked to return `reference-id`; inserted when the note is
  absent but `reference-id` matches.
- Regression: the existing on-open live-fetch tests and the background-scan tests
  still pass unchanged.
