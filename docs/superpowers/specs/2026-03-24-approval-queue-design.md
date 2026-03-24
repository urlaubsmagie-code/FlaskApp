# Approval Queue Design

**Date:** 2026-03-24
**Status:** Approved
**Feature:** AI Enhancement Plan #1 — Approval Queue

## Overview

AI responses are saved as "pending" drafts instead of sending immediately. The host reviews each draft and approves, edits, or rejects it. Per-conversation "auto-approve" toggle allows trusted chats to bypass the queue.

## Data Model

### Message table — new columns

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `approval_status` | String(20), nullable | NULL | `NULL` = normal message (including pre-feature and auto-approved), `'pending'` = awaiting approval, `'approved'` = approved and sent, `'rejected'` = rejected by host |
| `approved_at` | DateTime, nullable | NULL | Timestamp when the draft was approved |
| `original_content` | Text, nullable | NULL | Original AI text if edited before approval (for future "Learn from Corrections" feature) |

`Message.to_dict()` must include all three new fields so the frontend can distinguish pending drafts.

Design note: `approval_status=NULL` is used for both pre-feature messages and auto-approved messages. This is intentional — no need to distinguish them for current functionality. If "Learn from Corrections" (#8) needs this distinction later, a migration can backfill.

### Conversation table — new column

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `auto_approve` | Boolean | False | When True, AI responses skip the queue and send immediately |

### AISettings — new keys

| Key | Default | Description |
|-----|---------|-------------|
| `approval_queue_enabled` | `true` | Master toggle for the approval queue |
| `auto_approve_new_conversations` | `false` | Whether new conversations get `auto_approve=True` automatically |

Both keys must be added to `_populate_default_settings()` in models.py.

New conversations: `_find_or_create_conversation()` in message_router.py sets `auto_approve` from `auto_approve_new_conversations` AISettings key, parallel to how `auto_respond` is already set.

### Migration

`p10_approval_queue` — adds columns to Message and Conversation tables.

### Query changes

Anywhere that displays or counts "sent" messages must filter out pending/rejected drafts:
- Inbox latest_message preview (`preload_last_messages()` — add filter to the max(Message.id) subquery)
- Conversation summary generation
- Message counts
- `process_incoming_message()` return dict: when `approval_status='pending'`, set `ai_response=None` in the return dict so callers (Smoobu webhook, Gmail sync) don't treat pending drafts as sent messages

Filter: `WHERE approval_status IS NULL OR approval_status = 'approved'`

Exception: `api_get_messages()` returns pending drafts (so the UI can render them with special styling) but filters out rejected messages.

### Inbox filter implementation

The "KI-Freigabe" inbox filter requires knowing which conversations have pending drafts. Implementation: query conversations that have at least one Message with `approval_status='pending'`. This is a JOIN-based filter in `api_get_conversations()`, same pattern as other filters. The `has_pending_approval` flag is included in the conversation JSON response so the frontend can show the badge without an extra query.

## API Endpoints

### New endpoints

| Method | URL | Body | Behavior |
|--------|-----|------|----------|
| POST | `/api/messages/<id>/approve` | — | Set `approval_status='approved'`, `approved_at=now()`, send via platform. Returns `{success, email_sent, smoobu_sent}` |
| POST | `/api/messages/<id>/reject` | — | Set `approval_status='rejected'`. Returns `{success}` |
| POST | `/api/conversations/<id>/toggle-auto-approve` | — | Toggle `auto_approve` boolean. Returns `{auto_approve}`. Follows pattern of `toggle-ai` and `toggle-auto-respond` |
| POST | `/api/settings/bulk-auto-approve` | `{enabled: bool}` | Set `auto_approve` on ALL active conversations (not closed). Returns `{updated_count}` |

The "Edit" action is frontend-only: JS moves the draft text to the textarea, calls `/api/messages/<id>/reject` to remove the draft, then the user sends via the normal owner message endpoint.

### Platform send on approve

The `/api/messages/<id>/approve` endpoint handles platform sending the same way `api_generate_ai_response()` currently does — attempts Smoobu/Gmail send, returns success flags. If platform send fails, the message is still marked as `approved` but the response includes `email_sent=false` / `smoobu_sent=false` with a warning, same as current behavior for failed sends.

### Modified endpoints

| Endpoint | Change |
|----------|--------|
| `/api/conversations/<id>/ai-response` | Now creates pending draft (`approval_status='pending'`) instead of sending. Renamed conceptually to "KI-Antwort erstellen" |
| `/api/conversations/<id>/messages` (GET) | Returns pending drafts, filters out rejected |
| `/api/conversations` (GET) | Includes `has_pending_approval` flag per conversation |

## Message Router Flow

### Auto-respond flow (guest message arrives)

1. Guest message arrives → `process_incoming_message()`
2. Check: `approval_queue_enabled` (master) AND `conversation.auto_respond` AND `conversation.ai_enabled`
3. If yes, generate AI response via `_generate_ai_response()`
4. Check `conversation.auto_approve`:
   - **True:** Save with `approval_status=NULL`, send via platform immediately (current behavior)
   - **False:** Save with `approval_status='pending'`, skip platform send
5. If another guest message arrives while a draft is pending → delete the old pending draft → generate a new one with full context
6. If AI is still generating when the next message arrives, the second generation overwrites whatever the first produces — no locking needed, last-write-wins

### Manual "KI-Antwort erstellen" button

- Always creates a pending draft (`approval_status='pending'`), regardless of auto_approve setting
- Auto_approve only applies to the auto-respond flow, not manual generation. Manual = you want to review.
- If a pending draft already exists in the conversation, replace it

### Approval actions

| Action | Button | Behavior |
|--------|--------|----------|
| Approve | "Absenden" (green) | POST `/api/messages/<id>/approve`. Set `approval_status='approved'`, `approved_at=now()`, send via platform (Smoobu/Gmail) |
| Edit | "Bearbeiten" (blue) | Frontend moves draft text to textarea. POST `/api/messages/<id>/reject` to remove draft. User edits and sends as owner message via normal send endpoint |
| Reject | "Ablehnen" (red outline) | POST `/api/messages/<id>/reject`. Set `approval_status='rejected'`. Message stays in DB but disappears from conversation view |

### "KI-Vorschlag" button

Unchanged — fills textarea without saving anything to the database.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Approval queue master toggle turned OFF while drafts are pending | Pending drafts remain as-is. Host can still approve/reject them. No auto-approve or auto-reject. |
| AI disabled (`ai_enabled=False`) on conversation with pending draft | Pending draft remains. Host can still approve/reject it. Disabling AI only prevents future generation. |
| Conversation closed with pending draft | Pending draft is auto-rejected (`approval_status='rejected'`). |
| Auto-approve toggled ON while a draft is pending | Existing pending draft stays pending. Auto-approve only affects future messages. |
| Platform send fails during approval | Message still marked `approved`. Warning shown to user (same as current failed-send behavior). |

## Conversation UI

### Pending draft bubble

- Rendered inline in the message flow (same position as a normal AI message)
- Styled with red/warning background color
- Label: "Wartet auf Freigabe"
- Three action buttons directly on the bubble:
  - "Absenden" (green) — approve and send
  - "Bearbeiten" (blue/secondary) — move to textarea
  - "Ablehnen" (red outline) — reject

### Button rename

- "KI-Antwort senden" → "KI-Antwort erstellen"
- Same icon (magic wand), now creates a pending draft instead of sending immediately

### Polling

Pending drafts created by auto-respond appear via existing polling mechanism, styled as pending.

## Inbox UI

### Conversation card badge

- Orange/yellow badge "KI-Freigabe" when conversation has a pending draft (`has_pending_approval=true`)
- Same pattern as escalation badge "Braucht Aufmerksamkeit"
- Disappears when draft is approved/rejected

### Filter

- New filter option "KI-Freigabe" in the status filter group (alongside active, pending_owner, closed, escalated)

### Latest message preview

- Pending drafts excluded — shows last "real" message (guest, owner, or approved AI)

## Settings UI

### Approval Queue section (in Settings page)

- Toggle: "KI-Freigabe aktivieren" — master enable/disable
- Toggle: "Automatisch für neue Chats aktivieren" — auto-enable for new conversations
- Bulk button: "Für alle Chats aktivieren" / "Für alle Chats deaktivieren"

### Per-conversation toggle

- "Auto-Freigabe" toggle in conversation header, next to AI and auto-respond toggles
- When ON: AI responses skip the queue, send immediately
- Only visible when approval queue is enabled globally

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| "KI-Antwort senden" button | Rename to "KI-Antwort erstellen", creates pending draft | Consistent flow — manual or auto, you always review first |
| Approve action | Two buttons: "Absenden" (send) and "Bearbeiten" (edit in textarea) | Fast approve for common case, easy edit when needed |
| Reject action | Delete from view, no auto-regenerate, no pause | Simple — host decides next step manually |
| Data model | `approval_status` column on Message | Clean separation from sender_type, keeps drafts in message flow, supports future "Learn from Corrections" |
| Multiple pending drafts | Replace old draft when guest sends follow-up | Old draft is outdated; regenerate with full context |
| Auto-approve | Bypasses queue entirely, sends immediately (auto-respond only) | Simple — trust means trust. Manual button always creates draft for review. |
| Settings pattern | Same as auto-respond: per-conversation + bulk + auto for new chats | Consistent UX, familiar pattern |
| Pending draft display | Inline message bubble with red styling, no banner | Simpler, draft stays in context next to guest message |
| NULL for auto-approved messages | Same as pre-feature messages | Intentional — no need to distinguish now, can backfill later if needed |
| Race condition (concurrent generation) | Last-write-wins, no locking | Simple, and the latest response is always the most relevant |
| Edge cases (toggle off, close, etc.) | Pending drafts remain or auto-reject on close | Minimal surprise — toggling settings doesn't silently send or delete drafts |
