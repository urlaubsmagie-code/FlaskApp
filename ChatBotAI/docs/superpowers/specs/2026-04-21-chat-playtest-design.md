# Chat Playtest — Design Spec

**Date:** 2026-04-21
**Location:** Debug page, new "Chat Playtest" tab

## Goal

A sandbox chat environment in the Debug dashboard where the admin can simulate guest/host conversations through the real message pipeline without sending anything to actual guests. Includes a live event log showing each pipeline step as it happens.

## Core Mechanism

- Test conversations use `platform='playtest'` — a virtual platform type
- All messages flow through the real `MessageRouter` pipeline: `process_incoming_message()`, `process_owner_message()`, `_generate_ai_response()`
- Platform delivery is naturally skipped because the existing send code gates on `conversation.platform == 'smoobu'` or `== 'email'` — `'playtest'` matches neither
- Memory extraction, dedup, approval queue, escalation detection all run for real
- AI generation calls real Ollama (local, no cost)

## Event Log

### In-memory event buffer

A capped list (~200 entries) keyed by conversation_id, stored in a module-level dict. Events auto-expire when the buffer is full (oldest dropped).

```python
# services/playtest_events.py
_buffers: Dict[int, List[dict]] = {}

def playtest_log(conversation_id: int, event_type: str, detail: str):
    """Append an event to the playtest buffer for a conversation."""

def get_events(conversation_id: int, since_index: int = 0) -> Tuple[List[dict], int]:
    """Return events after since_index, plus the new cursor."""
```

### Event types emitted

| Event | Where | Detail |
|-------|-------|--------|
| `conversation_created` | playtest start endpoint | conversation id, guest name |
| `guest_message_stored` | `process_incoming_message` step 3 | message id, content preview |
| `owner_message_stored` | `process_owner_message` | message id, content preview |
| `dedup_check` | `_store_message` | result: `new` or `duplicate (existing_id=X)` |
| `memory_extraction` | `process_incoming_message` step 6 | extracted items count or "none" |
| `ai_generation_start` | `_generate_ai_response` top | trigger message preview |
| `ai_response_generated` | `_generate_ai_response` after Ollama | message id, content preview, duration_ms |
| `acknowledgment_skipped` | `_generate_ai_response` | detected ack content |
| `approval_status` | `_generate_ai_response` approval check | `pending` or `auto_approved` |
| `escalation_check` | `_generate_ai_response` escalation check | `triggered` or `not_triggered` |
| `context_filter` | `_generate_ai_response` after filter | filter_log summary |

### Instrumentation

~8-10 `playtest_log()` calls added to `MessageRouter` methods, each gated behind:
```python
if conversation.platform == 'playtest':
    playtest_log(conversation.id, 'event_type', 'detail')
```

Zero overhead for non-playtest conversations.

## API Endpoints

All admin-only, under the existing debug route prefix.

### `POST /api/debug/playtest/start`

Creates a new playtest conversation.

- Request body: `{ "guest_name": "Test Guest" }` (optional)
- Creates Guest with `name=guest_name, email="playtest-{uuid}@test.local"`
- Creates Conversation with `platform='playtest'`, `ai_enabled=True`, `auto_respond=False`
- Returns: `{ "conversation_id": 123, "guest_id": 456 }`

### `POST /api/debug/playtest/<id>/message`

Sends a message in the playtest conversation.

- Request body: `{ "content": "Hello!", "role": "guest" | "host" }`
- If `role=guest`: calls `router.process_incoming_message()` with `platform='playtest'`, `auto_respond=False`
- If `role=host`: calls `router.process_owner_message()`
- Returns: `{ "message_id": 789, "content": "..." }`

### `POST /api/debug/playtest/<id>/ai-response`

Generates an AI response for the playtest conversation.

- Calls `router.generate_ai_response_for_conversation()` (or the route-level logic from `api_generate_ai_response`)
- Full pipeline: context filter, knowledge base, corrections, conversation summary
- Returns: `{ "message_id": 101, "content": "...", "approval_status": "pending" | null }`

### `GET /api/debug/playtest/<id>/events?since=0`

Polls for new events.

- Returns: `{ "events": [...], "cursor": 15 }`
- Frontend stores cursor, passes as `since` on next poll

### `GET /api/debug/playtest/<id>/messages`

Returns all messages in the playtest conversation (for initial load / refresh).

- Returns: `{ "messages": [...] }`

## Frontend — Debug Tab

### Layout

New 4th tab in debug.html: **"Chat Playtest"** with flask icon.

Split layout (flexbox):
- **Left panel (60%)**: Chat area
- **Right panel (40%)**: Event log

### Left Panel — Chat

- **Top bar**: "New Playtest" button, conversation info (id, guest name)
- **Role switcher**: Two toggle buttons `[Guest]` `[Host]` — visually indicates active role. Guest = blue-ish, Host = wine/primary color
- **Messages area**: Scrollable div, messages styled similarly to the real conversation page but simplified. Guest messages left-aligned, host/AI messages right-aligned. AI messages have a small UMI badge.
- **Input area**: Text input + Send button. When in Host mode, an additional "AI Generate" button appears next to Send.
- **Auto-respond toggle**: Checkbox "Auto AI Response" — when on, after sending a guest message, automatically triggers AI generation

### Right Panel — Event Log

- **Header**: "Pipeline Events" with a clear button
- **Scrollable list**: Each event is a row with:
  - Timestamp (HH:MM:SS.ms)
  - Event type badge (color-coded: green=stored, blue=AI, yellow=dedup, red=escalation)
  - Detail text
- Auto-scrolls to bottom on new events
- Polls every 1 second

### Interactions

1. Click "New Playtest" → POST /start → clears chat and log, stores conversation_id
2. Toggle role to Guest, type message, Send → POST /message with role=guest → message appears in chat, events appear in log
3. Toggle role to Host, type message, Send → POST /message with role=host → message appears in chat
4. Click "AI Generate" → POST /ai-response → typing indicator → AI message appears, events show full pipeline
5. With "Auto AI Response" on: send as guest → guest message stored → AI automatically generates response

## Inbox Filtering

Playtest conversations should not clutter the real inbox. Add a filter in the inbox query:

```python
# In the inbox route query
conversations = conversations.filter(Conversation.platform != 'playtest')
```

This is a single-line addition to the inbox query in routes.py.

## Files Modified

| File | Change |
|------|--------|
| `services/playtest_events.py` | **NEW** — Event buffer (~40 lines) |
| `services/message_router.py` | Add ~10 `playtest_log()` calls, gated on platform check |
| `routes.py` | Add 5 playtest API endpoints + filter inbox query |
| `templates/chatbot/debug.html` | Add Chat Playtest tab (HTML + CSS + JS) |

## What Does NOT Change

- `conversation.js`, `inbox.js`, `app.js` — no production frontend changes
- No new database models or migrations
- No changes to Smoobu/Gmail service code
- No changes to the AI service
