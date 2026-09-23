# Email Auto-Insert Flush — Design

**Date:** 2026-07-01
**Branch:** feat/notion-knowledge-sync
**Goal:** Fill in missing Booking.com (and, on demand, Airbnb) guest messages by inserting the already-gathered E-Mail-Abgleich candidates into their matched chats automatically, using the match % — no manual per-candidate confirmation.

## Problem

Smoobu's API/webhooks drop some Booking.com guest messages. The E-Mail-Abgleich
(email reconciliation) feature already gathers those messages from Gmail relay
emails into the `EmailBackfillCandidate` table, each with a `confidence` score
and a `guessed_conversation_id`. Today they sit in `status='pending'` and require
manual Confirm/Reject in the review tray, or land only when a specific chat is
opened / its "recover emails" button is pressed. There is no way to flush the
whole backlog into chats at once, and the ongoing daemon path is dormant
(`email_reconcile_enabled='false'`).

## Decisions (locked)

- **Confidence floor: ≥ 0.8.** Same bar the existing per-chat recover button uses.
  Below 0.8, candidates stay in the review tray. Candidates with a null
  `guessed_conversation_id` are skipped (can't be filed).
- **Scope: one-time button flush now + ongoing Booking daemon.** Airbnb stays in
  the review tray (`email_autoinsert_airbnb='false'`).
- **Safety net: undo button + subtle in-chat marker.** Auto-inserted messages are
  already tagged (`platform_message_id = 'email:<gmail_id>'`), so they are
  identifiable and removable.

## Reuse (what already exists — do not rebuild)

- `EmailBackfillCandidate` model — `models.py:590–628`
- `promote_email_candidates(conversation_id, min_confidence)` —
  `services/email_reconcile.py:477–515`. Inserts pending candidates ≥ threshold
  for one conversation via `router._store_message()`, sets `status='confirmed'`,
  dedups via `has_equivalent_message()`, idempotent (excludes non-pending).
- Per-chat recover endpoint — `routes.py:4736–4745`
- Daemon auto-insert path (Path A) — `services/email_reconcile.py:641–663`,
  wired in `app.py:370–388`. Gated by `email_confidence_threshold` (0.8) and
  `email_autoinsert_booking`/`email_autoinsert_airbnb`.
- Review tray — `routes.py:399–424`, `templates/chatbot/email_review.html`

## Design

### 1. Batch flush — `promote_all_email_candidates(min_confidence=0.8)`

New function in `services/email_reconcile.py`.

- Select distinct `guessed_conversation_id` from `EmailBackfillCandidate` where
  `status='pending'` AND `confidence >= min_confidence` AND
  `guessed_conversation_id IS NOT NULL`.
- For each conversation id, call the existing
  `promote_email_candidates(conv_id, min_confidence)` and accumulate the inserted
  message IDs it produced.
- Persist the full inserted-ID list as JSON in
  `AISettings['email_last_flush_message_ids']` so undo is exact.
- Return `{inserted, conversations, skipped_no_conv}` where `skipped_no_conv` is
  the count of pending ≥ floor candidates that had no `guessed_conversation_id`.

`promote_email_candidates` must return the inserted message IDs (not just a
count) so the batch can record them. If it currently returns only a count, extend
it to return the IDs and adjust the two existing callers (on-open, recover button)
which can ignore the extra data.

### 2. Settings UI — two buttons

In `templates/chatbot/settings.html`, add an "E-Mail-Abgleich" action block:

- **"Gesammelte E-Mails einfügen (≥80%)"** button + a live pending-count
  (reuse `GET /api/email-review/pending-count` or a ≥0.8-filtered variant).
  → `POST /api/email-reconcile/flush-all` → calls `promote_all_email_candidates(0.8)`
  → toasts `"{inserted} Nachrichten in {conversations} Chats eingefügt"`
  (and notes skipped count if > 0).
- **"Letzten Abgleich rückgängig machen"** button
  → `POST /api/email-reconcile/undo-flush`.

Both routes admin-gated consistent with the rest of Settings.

### 3. Undo — `POST /api/email-reconcile/undo-flush`

- Read `AISettings['email_last_flush_message_ids']` (JSON list). If empty → no-op
  toast.
- Delete those `Message` rows. For any `EmailBackfillCandidate` whose
  `gmail_message_id` maps to a deleted message's `platform_message_id`
  (`email:<gmail_id>`), reset `status='pending'`.
- Clear `email_last_flush_message_ids`.
- Precise to the batch: even if the daemon inserted other `email:` messages in
  between, only the recorded IDs are touched.

### 4. Ongoing (Booking only)

Set once (via Settings save or a small toggle in the same block):
- `email_reconcile_enabled = 'true'`
- `email_autoinsert_booking = 'true'` (already default)
- `email_autoinsert_airbnb = 'false'` (already default)

Daemon then keeps filing new ≥0.8 Booking candidates; Airbnb continues to land in
the review tray.

### 5. Subtle in-chat marker

In the conversation render path (`templates/chatbot/conversation.html` and/or
`static/js/conversation.js`), messages whose `platform_message_id` starts with
`email:` get a small label, e.g. "via E-Mail-Abgleich". **Open item:** verify the
template/JS exposes `platform_message_id` to the message loop; if not, a small
template/serializer tweak is needed to surface it.

## Testing

One `test_*.py` (assert-based, no framework fixtures beyond existing test setup):

- Batch flush inserts only candidates ≥ 0.8; a 0.79 candidate is left pending.
- Dedup respected: a candidate whose message already exists is not double-inserted.
- `email_last_flush_message_ids` captures exactly the inserted IDs.
- Undo deletes exactly those messages and restores their candidates to `pending`;
  a second undo is a no-op.
- `skipped_no_conv` counts pending ≥ 0.8 candidates with null conversation.

## Out of scope

- Airbnb auto-insert (stays in tray).
- Changing the scoring algorithm or thresholds other than reusing 0.8.
- Retiring the review tray (it empties naturally for Booking; still used for
  Airbnb and < 0.8 candidates).
