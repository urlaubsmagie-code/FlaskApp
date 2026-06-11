# Smoobu Webhook Integration — Implementation Log

Started: 2026-05-18
Goal: Replace 120s daemon sync with real-time Smoobu webhook delivery.

---

## Why

The 120s background sync daemon makes 200+ Smoobu API calls every cycle and can take 2+ minutes to complete. Webhooks let Smoobu push individual events to us within ~2 seconds — drastically less load on both sides, and near-instant new-message delivery.

Webhook discovery confirmed (2026-05-18) Smoobu sends:
- `newMessage` (action="newMessage") — new chat message; payload has `data.id` (message id), `data.sender` ("host" or "guest"), `data.booking.id` (reservation id).
- `onlineCheckInUpdate` — guest finished online check-in; payload has `data.bookingId`.

Headers carry: `Api-Key` (varies per request — likely the destination integration's key), `Cf-Connecting-Ip: 85.195.81.12` (Smoobu's outbound IP), `User-Agent: Symfony BrowserKit`.

## Non-goals (don't touch)

- The `SmoobuService.sync_messages()` daemon loop. It stays as a safety net.
- `MessageRouter._store_message()` and its dedup logic. Already battle-tested.
- The `sync_conversation_messages(reservation_id)` method already used by the per-conversation sync button. We'll *reuse* it from the webhook handler.
- Anything outside the webhook handler and (later) the daemon interval.

## Architecture

```
Smoobu  ── POST /chatbot/api/webhooks/smoobu ──►  Flask
                                                    │
                                                    ▼
                                          Verify Api-Key header
                                                    │
                                                    ▼
                                          Dispatch on action:
                                            newMessage → spawn thread →
                                              smoobu.sync_conversation_messages(booking_id)
                                            onlineCheckInUpdate → log only (for now)
                                            anything else → log to discovery file
                                                    │
                                                    ▼
                                            Always return 200 in <50ms
```

Reuses existing `sync_conversation_messages(reservation_id)` which already handles message fetch, dedup (via unique constraint p14 + IntegrityError guards), `last_message_at` bump, `is_read` reconciliation. No new business logic.

The fire-and-forget thread keeps Smoobu happy (no retries triggered by slow response).

## Steps

| # | Status   | Description                                                                            |
|---|----------|----------------------------------------------------------------------------------------|
| 0 | DONE     | Created discovery endpoint (`webhook_smoobu_discovery` in routes.py), logged 4 events. |
| 1 | DONE     | Confirmed payload format from log. `sync_conversation_messages` reused as-is.          |
| 2 | DONE     | Webhook handler now dispatches `newMessage` events to a background sync thread.        |
| 3 | PARTIAL  | One `newMessage` event verified end-to-end (Hunter Johnson, 12:12:51 UTC). 24h soak ongoing. |
| 4 | LATER    | Increase daemon `SYNC_INTERVAL` from 120s to 600s once webhooks proven over 24-48h.   |
| 5 | LATER    | (Optional) IP-whitelist Smoobu's 85.195.81.12 if their docs confirm it's stable.       |
| 6 | DONE     | Handle `newReservation` events — pre-enrich Guest before first message arrives.        |
| 7 | DONE     | Daemon coverage check — log [WEBHOOK_MISS] when daemon imports something new.          |
| 8a | DONE    | Handle `cancelReservation` + `updateReservation` events (data layer only).             |
| 8b | DONE    | UI: render "Storniert" label in inbox card + conversation header.                      |

Each step is independently revertible. Files touched per step are listed below as they happen.

## Step 2 — TODO

**Files to touch:**
- `ChatBotAI/routes.py` — extend `webhook_smoobu_discovery`. Keep logging for unknown events.

**No other files change.**

**Rollback if it breaks:**
- `git diff routes.py` to see the change.
- Revert: replace the new handler body with the prior pure-logging body. Server restart not needed for the route change to be re-deployed (Flask reloads on POST in dev, requires restart in production Waitress — same as any other route change).

**Failure modes to watch for:**
- IntegrityError on duplicate inserts — already handled by p14 unique index + existing rollback logic in `sync_conversation_messages`.
- Exception in worker thread — must not propagate to the route. We catch + log.
- Smoobu sends an unexpected payload shape — fall through to the existing log-only branch.

---

## Change log (appended as steps complete)

### 2026-05-18 — Step 2 implemented

**File changed**: `ChatBotAI/routes.py`
**Function changed**: `webhook_smoobu_discovery` (extended; discovery logging preserved verbatim).
**New function added**: `_run_webhook_message_sync(app, booking_id)` — module-level helper run in a daemon thread.

**What now happens on a webhook POST:**
1. Body and headers are written to `instance/smoobu_webhooks.log` exactly as before (discovery preserved).
2. If `parsed_json.action == 'newMessage'` and `data.booking.id` is present, a daemon thread runs `SmoobuService.sync_conversation_messages(str(booking_id))`. The route returns 200 in <50 ms.
3. All other action types (`onlineCheckInUpdate`, unknown) are logged only — no behavior change.
4. Any exception in dispatch is caught + logged; the 200 response is guaranteed.

**No other code touched**: `sync_conversation_messages`, `MessageRouter`, the daemon, and the polling stack are unchanged.

**To activate**: restart the Flask server (`taskkill /F /IM python.exe` then `start_server.bat`). No DB migration. No frontend cache bump.

**To roll back this step (if it breaks anything):**
1. In `routes.py`, restore `webhook_smoobu_discovery` to the discovery-only body — copy from the version below.
2. Delete the new `_run_webhook_message_sync` helper.
3. Restart the server.

### 2026-05-18 — Step 6 implemented (newReservation handler)

**Goal**: pre-enrich the Guest record the moment a new booking arrives at Smoobu, so when the guest sends their first message UMI already has rich context (party size, channel, language, booking note).

**Files changed**:
- `ChatBotAI/services/smoobu_service.py` — added new method `process_new_reservation(res_data) -> Optional[Guest]`. Does NOT modify any existing method. Reuses the existing `_enrich_guest_from_reservation` upsert and `MemoryService.find_or_create_guest`.
- `ChatBotAI/routes.py` — extended the `action` dispatcher in `webhook_smoobu_discovery` with an `elif action == 'newReservation'` branch that spawns a daemon thread. Added new helper `_run_webhook_reservation_enrich(app, res_data)`.

**Deliberate design choice — no Conversation pre-creation**: pre-creating an empty Conversation would clutter the inbox (which sorts by `last_message_at`, NULL would sort weirdly). Instead we only pre-create the Guest; when the first message arrives, `MessageRouter.find_or_create_guest` matches by phone/email and reuses the enriched record, so AI prompt for message #1 has full context. Conversation creation flow is unchanged.

**To activate**: restart the Flask server. No DB migration. No frontend cache bump.

**To roll back this step**:
1. In `routes.py`: delete the `elif action == 'newReservation':` block and the new `_run_webhook_reservation_enrich` function.
2. In `services/smoobu_service.py`: delete the `process_new_reservation` method (lines starting `def process_new_reservation`).
3. Restart the server.

Neither file's existing functions were modified, so a clean revert is just deleting the new additions.

**Failure modes already handled**:
- Payload missing `data.id` → logged warning, no thread spawned.
- Payload without phone/email/name → method returns None without creating an anonymous Guest.
- `MemoryService` not initialized → method returns None.
- Any exception in enrichment → rollback DB, log, swallow (route already returned 200).

### 2026-05-19 — Step 8a implemented (cancelReservation + updateReservation, data layer)

**Goal**: capture two new event types Smoobu was firing that we weren't handling.
- `cancelReservation` (~5/day in observation): mark linked Conversation with `cancelled_at` timestamp so UI can later show a "Storniert" label.
- `updateReservation`: silently refresh check_in/check_out + GuestDetail.

**Files changed**:
- `ChatBotAI/migrations/versions/p16_cancelled_at_add_column.py` — new file. Adds `Conversation.cancelled_at` DateTime nullable column. No backfill needed (NULL = not cancelled).
- `ChatBotAI/models.py` — added `cancelled_at = db.Column(db.DateTime, nullable=True)` to Conversation (next to existing `escalated_at`). Added `cancelled_at` to `to_dict()` output. No other model changes.
- `ChatBotAI/services/smoobu_service.py` — added two new methods: `mark_reservation_cancelled(reservation_id)` and `update_reservation_from_webhook(res_data)`. Both reuse existing `_enrich_guest_from_reservation` and `process_new_reservation`. No existing methods modified.
- `ChatBotAI/routes.py` — extended the action dispatcher with `cancelReservation` and `updateReservation` branches. Added two new worker helpers `_run_webhook_cancel_reservation` and `_run_webhook_update_reservation`. No existing handler logic touched.

**Deliberate scope limit**: data layer only. The `cancelled_at` value is stored but not yet shown to the team. Step 8b will add the visual label.

**Activation steps**:
1. Run migration: `flask db upgrade` (or trust the existing `_auto_upgrade_schema` to handle it on next boot).
2. Restart server: `taskkill /F /IM python.exe` then `start_server.bat`.
3. No frontend cache bump yet — UI changes are Step 8b.

**Verification**:
- Check `instance/smoobu_webhooks.log` for new `cancelReservation` entries.
- Query the DB: `SELECT id, platform_id, cancelled_at FROM conversation WHERE cancelled_at IS NOT NULL;` — should show recently-cancelled conversations.
- Server console should log `Smoobu cancelReservation webhook dispatched: res=...` on each event.

**Rollback (data + code, leaves data column in DB)**:
1. In `routes.py`: delete the two new `elif` branches (`cancelReservation`, `updateReservation`) and the two new worker functions.
2. In `services/smoobu_service.py`: delete `mark_reservation_cancelled` and `update_reservation_from_webhook` methods.
3. (Optional, only if you also want to drop the column) `flask db downgrade p15_last_message_at` will run p16's `downgrade()` and remove the column.
4. In `models.py`: only revert the column + to_dict additions if you ran the downgrade.

Migration p16 is independently revertible — its `downgrade()` removes the column cleanly.

### 2026-05-19 — Step 8b implemented (Storniert label UI)

**Goal**: show a "Storniert" badge on cancelled-reservation conversations in both inbox card and conversation header, so the team can decide whether to keep chatting. No behaviour change.

**Files changed**:
- `templates/chatbot/inbox.html` — added one `{% if conv.cancelled_at %}` block inside `.conversation-meta`, just before `.status-badge`.
- `static/js/inbox.js` — added `cancellationLabel` variable in `createConversationCard()` and inserted it into the rendered HTML; added symmetric add/remove logic in `updateConversationCard()` so the badge appears in live polling updates when the cancelReservation webhook fires while the inbox is already open.
- `templates/chatbot/conversation.html` — added one `{% if conversation.cancelled_at %}` block inside `.guest-info`, after the stay-dates span.
- `static/css/style.css` — new `.cancellation-badge` rule (muted gray + amber text, smaller than `.escalation-badge` because cancellations are informational, not urgent). Dark-mode variant included.
- `static/js/i18n.js` — added `inbox.badge.cancelled` strings: German "Storniert" / English "Cancelled".
- `templates/chatbot/base.html` — bumped style.css to v50 and i18n.js to v25.
- `templates/chatbot/inbox.html` — bumped inbox.js to v29.
- (MEMORY.md cache-versions line updated.)

**Activation**:
1. Hard-reload the inbox (Ctrl+Shift+R) — no server restart needed for these static-file + template changes (templates are re-read per request).
2. Existing cancelled conversations from Step 8a will immediately show the badge.

**Rollback**:
1. Revert the additions in each of the 6 files (each is a small, contiguous addition — search for `cancelled_at` / `cancellation-badge` / `inbox.badge.cancelled` to find them).
2. Optionally roll back cache-version bumps (but leaving them higher than before is harmless).

### 2026-05-19 — Step 7 implemented (daemon coverage check)

**Goal**: gather evidence about webhook reliability so we can safely relax the daemon's 120s interval (Step 4) later.

**File changed**: `ChatBotAI/app.py` — single block inside `_run_one_sync`. The existing `if imported > 0: logger.info(...)` branch was upgraded:
- `logger.info` → `logger.warning` with a `[WEBHOOK_MISS]` tag
- Added `print(...)` so the line shows in the console regardless of logging-handler configuration
- `logger.debug` branch unchanged in semantics but message updated for clarity ("webhooks healthy")

**No new functions. No new files. No behavior change.** The daemon still runs every 120s and still imports anything it finds — we're just making "it found something" visible and tagged.

**How to read the data**:
- After ~24h of normal traffic, count `[WEBHOOK_MISS]` lines in the Flask Server console.
- 0 → webhooks are perfect. Move to Step 4 (relax daemon interval).
- 1–3 → very rare misses. Investigate manually then proceed with Step 4 with a safety margin (e.g., 5 min instead of 10 min).
- Many → don't relax the daemon; webhooks aren't trustworthy alone.

**Activation**: restart server (`taskkill /F /IM python.exe` then `start_server.bat`). No DB migration, no frontend changes.

**Rollback**: revert the one block in `app.py` back to the previous `logger.info` + `logger.debug` pair. Trivial.

---

Original discovery-only body (for rollback reference):

```python
@chatbot_bp.route('/api/webhooks/smoobu', methods=['POST', 'GET'])
def webhook_smoobu_discovery():
    import json
    import os
    from datetime import datetime
    from flask import request, current_app

    try:
        raw_body = request.get_data(as_text=True)
    except Exception:
        raw_body = '<unreadable>'

    try:
        parsed_json = request.get_json(silent=True)
    except Exception:
        parsed_json = None

    entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'method': request.method,
        'remote_addr': request.remote_addr,
        'path': request.path,
        'query_string': request.query_string.decode('utf-8', errors='replace'),
        'headers': {k: v for k, v in request.headers.items()},
        'raw_body': raw_body,
        'parsed_json': parsed_json,
    }

    log_dir = os.path.join(current_app.instance_path, '')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'smoobu_webhooks.log')
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')
    except Exception:
        current_app.logger.exception('Failed to write Smoobu webhook log entry')

    return jsonify({'success': True, 'received': True}), 200
```
