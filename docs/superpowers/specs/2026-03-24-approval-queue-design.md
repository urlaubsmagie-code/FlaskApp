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
| `approval_status` | String(20), nullable | NULL | `NULL` = normal message, `'pending'` = awaiting approval, `'approved'` = approved and sent, `'rejected'` = rejected by host |
| `approved_at` | DateTime, nullable | NULL | Timestamp when the draft was approved |
| `original_content` | Text, nullable | NULL | Original AI text if edited before approval (for future "Learn from Corrections" feature) |

### Conversation table — new column

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `auto_approve` | Boolean | False | When True, AI responses skip the queue and send immediately |

### AISettings — new keys

| Key | Default | Description |
|-----|---------|-------------|
| `approval_queue_enabled` | `true` | Master toggle for the approval queue |
| `auto_approve_new_conversations` | `false` | Whether new conversations get `auto_approve=True` automatically |

### Migration

`p10_approval_queue` — adds columns to Message and Conversation tables.

### Query changes

Anywhere that displays or counts "sent" messages must filter out pending/rejected drafts:
- Inbox latest_message preview
- Conversation summary generation
- Message counts

Filter: `WHERE approval_status IS NULL OR approval_status = 'approved'`

## Message Router Flow

### Auto-respond flow (guest message arrives)

1. Guest message arrives → `process_incoming_message()`
2. Check: `approval_queue_enabled` (master) AND `conversation.auto_respond` AND `conversation.ai_enabled`
3. If yes, generate AI response via `_generate_ai_response()`
4. Check `conversation.auto_approve`:
   - **True:** Save with `approval_status=NULL`, send via platform immediately (current behavior)
   - **False:** Save with `approval_status='pending'`, skip platform send
5. If another guest message arrives while a draft is pending → delete the old pending draft → generate a new one with full context

### Manual "KI-Antwort erstellen" button

- Always creates a pending draft (`approval_status='pending'`), regardless of auto_approve
- If a pending draft already exists in the conversation, replace it

### Approval actions

| Action | Button | Behavior |
|--------|--------|----------|
| Approve | "Absenden" (green) | Set `approval_status='approved'`, `approved_at=now()`, send via platform (Smoobu/Gmail) |
| Edit | "Bearbeiten" (blue) | Move draft text to textarea, delete the pending message. User edits and sends as owner message |
| Reject | "Ablehnen" (red outline) | Set `approval_status='rejected'`. Message stays in DB but disappears from conversation view |

### "KI-Vorschlag" button

Unchanged — fills textarea without saving anything to the database.

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

- Orange/yellow badge "KI-Freigabe" when conversation has a pending draft
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
| Auto-approve | Bypasses queue entirely, sends immediately | Simple — trust means trust, no delays |
| Settings pattern | Same as auto-respond: per-conversation + bulk + auto for new chats | Consistent UX, familiar pattern |
| Pending draft display | Inline message bubble with red styling, no banner | Simpler, draft stays in context next to guest message |
