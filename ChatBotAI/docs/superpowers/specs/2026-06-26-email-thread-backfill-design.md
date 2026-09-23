# Email-Thread Backfill — Design

**Date:** 2026-06-26
**Status:** Approved design, pending implementation plan
**Author:** brainstormed with user (urlaubsmagie)

## Problem

Smoobu does not reliably deliver all Booking.com chat messages into our inbox
(a Booking-side contact-configuration issue the user is separately fixing).
Meanwhile, the same guest conversations frequently exist **in full** in Gmail as
ordinary two-sided email threads — the guest's messages **and** our team's
replies (e.g. from `buchungsanfrage.urlaubsmagie@gmail.com`, signed "Elena").

We want to reconstruct those conversations in the app by copying the missing
messages from Gmail into the conversations we already have, so a chat is
complete without depending on Smoobu being 100%.

### Evidence (gathered 2026-06-26)

- Genuine Booking.com **notification** emails are effectively absent from the
  account (the only Booking-format email in 365 days was a phishing spoof).
  Booking never emails our own replies, and currently isn't reliably emailing
  guest chat messages either — consistent with the contact-config issue.
- Gmail **does** contain ~20+ real two-sided guest↔host email threads
  (payment, cancellation, invoice, arrival questions), with our replies in
  `SENT`. Example thread `19e0121a`: guest `dbrachholz@gmail.com` →
  `buchungsanfrage.urlaubsmagie@googlemail.com`, our reply from
  `buchungsanfrage.urlaubsmagie@gmail.com` → guest, signed "Elena".

These threads are the real, available source. They are NOT Booking's
notification relay format; they are direct email conversations.

## Goal & Scope

**Goal:** Backfill **existing** conversations with missing messages (both
directions) found in the guest's Gmail thread.

**In scope:**
- Match a Gmail thread to an existing Guest + Conversation.
- Insert missing `guest` and `owner` messages from the thread.
- Per-chat manual trigger (button) + an opt-in automatic background pass.

**Out of scope (YAGNI / deferred):**
- Creating **new** conversations for guests we don't already have (deferred
  Phase 2).
- Running memory/AI extraction on backfilled messages (insert as historical
  only for now).
- Channels other than Gmail (this is Gmail-thread backfill).

## Approach

**Extend the existing `services/email_reconcile.py` module** (Approach A) rather
than build a parallel system. Reuse its hardened pieces:
- DKIM/DMARC authenticity gate (`verify_sender_authenticity`),
- `GmailService._clean_email_body()` quoted-history/signature stripping,
- existing fuzzy dedup (normalized content + direction + time window),
- existing guest-matching helpers.

New, small additions: ingest **host/`SENT`** messages, and walk a **thread**
(not a single notification email).

## Matching (the careful part)

Anchor = the guest's **real email address**. Confidence tiers:

### Tier 1 — Strong (may auto-insert)
- Guest has a usable email on file: non-empty, and **not** a relay alias
  (`@guest.booking.com`, `@reply.airbnb.com`, etc.).
- Search Gmail: `from:<email> OR to:<email>` within the lookback window.
- A candidate thread qualifies **only if it involves both** the guest's address
  **and** one of our configured host addresses (proves guest↔us, not
  guest↔supplier).

### Tier 2 — Weak (confirmation-gated, button only)
- Guest has no usable email (common for Booking-relay guests).
- Fall back to a **name** search, but **never auto-insert**. Require:
  - a host address present in the thread, AND
  - date overlap between the email dates and the reservation
    (`check_in`..`check_out`) window.
- Surface candidate thread(s) to the user to confirm before any write.

### No match → skip
Clear "no reliable email thread found for this guest" result; nothing written.

### Disambiguation
- The per-chat button attaches found messages to **the conversation the user
  opened**. The Tier-1 host-address + date-overlap checks prevent stapling the
  wrong thread when a guest has multiple stays.
- The **background pass uses Tier 1 only**, and additionally requires the email
  dates to fall near the conversation's reservation window. Tier 2 never runs
  automatically.

## Reading the thread

### Direction classification
For each message: sender address ∈ **host set** → `owner`; otherwise → `guest`.
Verified against real data (guest address inbound, our address on `SENT`).

Host set is a configurable `AISettings` list, seeded from real data:
- `buchungsanfrage.urlaubsmagie@gmail.com`
- `buchungsanfrage.urlaubsmagie@googlemail.com`
- `urlaubsmagie@gmail.com`
- `urlaubsmagie@host.smoobu.com`

(Editable; add any `info@`/team addresses the user identifies.)

### Content extraction
- Run each message through `_clean_email_body()` to strip quoted history and
  signatures, leaving only new text.
- Skip junk: bounce notices ("Message not delivered", `mailer-daemon`), empty
  bodies, pure-signature messages.

### Anti-spoof
- `guest`-direction messages must pass `verify_sender_authenticity`
  (DKIM/DMARC), preventing injection of a spoofed guest message.
- `owner`-direction messages originate from our own authenticated account →
  inherently trusted.

### Dedup (two layers)
1. **Idempotency:** each inserted message gets
   `platform_message_id = "gmail-<gmailMessageId>"`. Re-runs never duplicate.
2. **Cross-source:** reuse existing fuzzy dedup (normalized content + same
   direction + time window) so a message Smoobu already has isn't re-inserted
   from email.

## Insertion / data model

New `Message` rows on the matched conversation:
- `sender_type`: `owner` or `guest` (from direction classification).
- `content`: cleaned body.
- `platform_message_id`: `gmail-<gmailMessageId>`.
- `sent_at`: the email's `Date`.
- `sent_via_app = False` (synced, not app-sent — keeps statistics correct).
- `is_processed = True` (no AI/memory pass in this phase).

Conversation timestamps:
- `last_message_at = max(existing, newest inserted email date)` — backfilling
  **old** history must NOT bounce an old chat to the top of the inbox.
- `updated_at` bumped so polling clients refresh.
- Read state: backfilled history does not mark a settled chat unread.

## Triggers

### Per-chat button (ship first)
- `POST /chatbot/api/conversation/<id>/import-email-thread`.
- Runs the matcher for that conversation's guest; returns
  `{inserted, skipped_dupes, candidates_needing_confirm[]}` + short preview.
- UI: button beside the existing "find emails" recover button. Tier-2
  candidates render as a confirm list before writing.
- Bounded and returns quickly (Gmail calls slow → respect Cloudflare 100s rule;
  fire-and-forget if needed).

### Background pass (opt-in)
- Extend the existing reconciliation pass: for each existing conversation with a
  **Tier-1** match, backfill silently.
- Gated by new setting `email_thread_backfill_auto` (**default off**). Enabled
  after the button is trusted.

## Settings (`AISettings`)
- Host-address list (seeded above; editable).
- `email_thread_backfill_auto` (default `false`).
- Lookback window in days (default `180`) to bound Gmail scans.

## Error handling
- Gmail unavailable / rate-limited → friendly error; **no partial writes**
  (commit per thread, rollback on failure).
- No match → clear message.
- Every insert idempotent → retries always safe.

## Testing (TDD; reuse `tests/test_email_reconcile.py` patterns)
Fixture Gmail threads covering:
- two-sided guest+host thread → both directions inserted with correct
  `sender_type`;
- quoted-history stripping (no duplicated quoted text);
- bounce / `mailer-daemon` skipped;
- cross-source dedup (message already present from Smoobu → not re-inserted);
- idempotency (run twice → identical result);
- matching precision: email-mismatch → **nothing inserted**; name-only →
  **never auto-inserts** (Tier 2 returns candidates, writes nothing).

## Open items for implementation planning
- Confirm the final host-address list with the user (any `info@`/team aliases).
- Exact Gmail query construction and pagination bounds for a single thread.
- UI placement/labels for the confirm list (Tier 2).
