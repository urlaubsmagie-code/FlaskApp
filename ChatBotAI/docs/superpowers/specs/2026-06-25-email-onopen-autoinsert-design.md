# Email Candidate Promotion — On-Open Auto-Insert + Per-Chat Recover Button

**Date:** 2026-06-25
**Status:** Design approved, pending spec review
**Depends on:** Email Reconciliation Pass (`services/email_reconcile.py`, `EmailBackfillCandidate` model, `/chatbot/email-review` tray) and the DKIM/DMARC anti-spoof gate.

## Problem

The email reconciliation pass catches guest messages that Smoobu dropped (from Airbnb/Booking notification emails) and queues them as `EmailBackfillCandidate` rows, each matched to a best-guess conversation with a confidence score. Today the only way a candidate becomes a real message is:

1. The background daemon auto-inserts it **if** `confidence ≥ threshold (0.8)` **and** the platform autoinsert flag is on — currently OFF (shadow mode), so nothing flows, or
2. A human opens `/chatbot/email-review` and confirms each one.

The user wants candidates to reach the conversation more naturally — as they work through chats — without trusting a blanket background auto-insert, and with an explicit on-demand option per chat.

## Goals

- When the user opens a conversation, **silently** insert the near-certain (`≥ 0.95`) email candidates matched to it.
- Give every conversation a **manual button** to pull in that chat's already-detected candidates on demand (down to the standard `0.8` bar), usable whether or not the auto mode is enabled.
- Keep weak matches (`< 0.8`) in the review tray only.
- Make the auto behavior toggleable from Settings.

## Non-Goals

- No live Gmail re-scan per chat (operates only on already-queued candidates — fast, no external call, no Cloudflare 524 risk).
- No banner/undo UI — insertion is silent (explicit user choice).
- No change to the background daemon's behavior or the shadow-mode flags.
- No re-verification of DKIM/DMARC at promotion time (the queued candidates were already classified, matched, and — for future scans — passed the gate at capture).

## Design

### Shared helper

`promote_email_candidates(conversation_id, min_confidence) -> int` in `services/email_reconcile.py`:

1. Query `EmailBackfillCandidate` where `guessed_conversation_id == conversation_id`, `status == 'pending'`, `confidence >= min_confidence`, ordered by `parsed_timestamp` ascending (chronological insert).
2. For each candidate:
   - **Dedup guard:** skip (leave pending) if a guest message already exists within ±window of `parsed_timestamp`. `has_equivalent_message(conversation_id, notif, window_minutes)` only reads `notif.sent_at`, so pass a minimal shim — `types.SimpleNamespace(sent_at=cand.parsed_timestamp)` — rather than constructing a full `ParsedNotification`. This reuses the existing helper and prevents duplicating a message Smoobu later synced. The dedup window comes from `get_reconcile_config()['window_minutes']`.
   - Insert via the same path the confirm endpoint uses:
     `MessageRouter._store_message(conversation_id=…, sender_type='guest', content=cand.parsed_text, platform_message_id=f"email:{cand.gmail_message_id}", sent_at=cand.parsed_timestamp, sent_via_app=False)`.
     The `platform_message_id` uniqueness gives global idempotency on top of the dedup guard.
   - Set `cand.status = 'confirmed'`.
3. `db.session.commit()` once at the end. Return the count inserted.

Idempotent: confirmed rows are excluded by the `status == 'pending'` filter, so a second call (e.g. re-opening the chat) inserts nothing.

### Mode 1 — Auto-insert on chat open

In `routes.py::conversation_view` (before the message query):

```
if AISettings.get('email_autoinsert_on_open', 'true') != 'false':
    try:
        threshold = float(AISettings.get('email_onopen_threshold', '0.95'))
    except (TypeError, ValueError):
        threshold = 0.95
    promote_email_candidates(conversation_id, threshold)
```

Inserted messages are then picked up by the existing `base_filter` message query and render in-thread on the same page load. Wrapped in try/except so a promotion failure never blocks the conversation view.

### Mode 2 — Per-chat recover button

- **Endpoint:** `POST /api/conversation/<int:conversation_id>/recover-emails`, `@login_required`.
  - Reads the standard match threshold from `get_reconcile_config()['threshold']` (default 0.8).
  - Calls `promote_email_candidates(conversation_id, threshold)`.
  - Returns `{'success': True, 'inserted': N}`.
- **UI:** a button in `conversation.html` ("E-Mails für diesen Chat suchen") that POSTs to the endpoint, then on success reloads the thread (or appends and scrolls) and shows a brief "N Nachricht(en) eingefügt" toast. Always rendered, regardless of the toggle.
- i18n keys (`de`/`en`) for the button label and result toast; bump `conversation.js` + `i18n.js` cache versions.

### Settings

- New `AISettings` keys, both optional with defaults:
  - `email_autoinsert_on_open` — bool string, default `'true'`.
  - `email_onopen_threshold` — float string, default `'0.95'`.
- Toggle + threshold field added to the existing email-reconcile section of `settings.html`, with i18n strings.

## Data Flow

```
daemon scan ──> EmailBackfillCandidate (pending, scored, matched to conv)
                         │
        ┌────────────────┼─────────────────────────┐
        ▼                ▼                          ▼
 open chat (≥0.95)   recover button (≥0.8)     stays in tray (<0.8)
 auto, silent        manual, per-chat          manual confirm only
        │                │
        └──> promote_email_candidates(conv, bar)
                 dedup guard → _store_message → status='confirmed'
```

## Edge Cases

- **GET that writes:** `conversation_view` is a GET that now mutates on first open. Acceptable for this internal app; idempotent, and failures are swallowed so the page always renders.
- **Pre-gate candidates:** the ~100 currently queued predate the DKIM gate. They are trusted as already-matched; promotion does not re-verify authenticity (auth headers are not stored on the candidate row).
- **Dedup vs. Smoobu:** the ±window guard plus `email:<gmail-id>` uniqueness prevent a message appearing twice if Smoobu later syncs the same content.
- **Wrong-conversation match:** below-0.8 candidates are never promoted by either mode; they require explicit tray confirmation (which already supports a `conversation_id` override).
- **Concurrency:** two simultaneous opens of the same chat — the `status == 'pending'` filter + commit make a double-insert unlikely; `_store_message`'s `platform_message_id` uniqueness is the backstop.

## Testing (TDD)

Unit (`promote_email_candidates`):
- Inserts a `≥ min_confidence` candidate and marks it `confirmed`.
- Skips a candidate below `min_confidence` (stays `pending`).
- Skips (leaves pending) a candidate when an equivalent guest message already exists in-window.
- Inserts multiple in `parsed_timestamp` order.
- Idempotent: second call inserts 0.
- Returns the correct inserted count.

Route-level:
- `conversation_view` auto-inserts `≥0.95` when `email_autoinsert_on_open` is on; inserts nothing when off.
- `POST /api/conversation/<id>/recover-emails` inserts `≥0.8` candidates for that chat and returns the count; below-0.8 untouched.

## Open Questions

None — design approved 2026-06-25.
