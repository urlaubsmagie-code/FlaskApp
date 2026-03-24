# Escalation System + Inbox Status Indicators

**Date**: 2026-03-24
**Status**: Approved
**Features**: AI Enhancement Plan #4 (Escalation System) + #5 (Inbox Status Indicators)

## Goal

When the AI can't handle a guest's message (restricted topic, complaint, etc.), it should escalate: send a holding response, pause auto-respond, mark the conversation for host attention, and notify the host. The inbox should show at a glance which conversations are escalated and which have AI active.

## Design Decisions

- **Detection method**: Post-response phrase scanning. After the AI generates a response, check for the escalation phrase (e.g. "Kollegen", "colleague"). No second AI call needed.
- **Resolution**: Dedicated "Resolve" button, independent from AI toggle. Host can resolve escalation without re-enabling AI.
- **Push notification**: Separate escalation notification distinct from regular new-message notifications.
- **Inbox indicators**: Escalated state (orange + label) and AI auto-respond status (on/off badge) per conversation card.

## Implementation Approach

Layered: backend first (migration + detection + API), then frontend (inbox indicators + resolve button + filter).

---

## Layer 1: Backend

### 1.1 Database Migration

Add to `Conversation` model:
- `escalated` — Boolean, default `False`, indexed
- `escalated_at` — DateTime, nullable, set when escalated goes True, cleared on resolve (useful for future Statistics feature and urgency sorting)

Migration file: `p8_escalation_add_escalated_flag.py`

### 1.2 Escalation Detection (message_router.py)

In `_generate_ai_response()`, after the AI response is saved:

1. Scan response text (case-insensitive substring match) for escalation phrases. Use only high-specificity phrases tied to the AI's escalation prompt instruction:
   - German: "Kollegen" or "Kollegin" (the AI is instructed to say "I'll check with my colleague")
   - English: "colleague"
   - These are specific enough to avoid false positives — the AI won't mention "colleagues" in normal property/booking responses.
2. If match found:
   - Set `conversation.escalated = True`
   - Set `conversation.auto_respond = False`
   - Call `push_service.notify_escalation(conversation, guest)`
   - Log the escalation

Detection function: `_is_escalation_response(response_text)` — returns bool.

**Note on `/ai-suggest` endpoint**: Escalation detection does NOT run on manual AI suggestions (`/api/conversations/<id>/ai-suggest`), since those are previews that the host reviews before sending. The host can judge escalation-worthy content themselves.

### 1.3 Push Notification (push_service.py)

New method `notify_escalation(conversation, guest)`:
- Payload: title "Braucht Aufmerksamkeit", body "[Guest Name]", URL to conversation
- Targets assigned user, or all users if unassigned (same logic as `notify_new_guest_message`)
- Push notifications use German (the default UI language), consistent with existing push notifications. Push i18n is out of scope for this iteration.

### 1.4 API Changes (routes.py)

**Existing endpoints — extend response:**
- `GET /api/conversations` — include `escalated` and `escalated_at` fields in each conversation object. Add optional `?escalated=true` query parameter for server-side filtering (important since inbox is paginated at 20 and escalated conversations may be on later pages).
- `GET /api/conversations/<id>` — include `escalated` and `escalated_at` fields

**New endpoint:**
- `POST /api/conversations/<id>/resolve` — sets `escalated = False`, clears `escalated_at`, returns updated conversation. Does NOT touch `auto_respond`. Resolving a non-escalated conversation is a no-op (returns 200 with current state).

---

## Layer 2: Frontend

### 2.1 Inbox Card Indicators (inbox.html + inbox.js)

Each conversation card gains:
- **Escalated state**: Orange/red left border or background tint + label "Braucht Aufmerksamkeit" / "Needs Attention"
- **AI status badge**: Small indicator showing auto-respond ON (green dot/icon) or OFF (grey dot/icon)

### 2.2 Resolve Button (conversation.html + conversation.js)

- Appears in conversation header when `escalated = True`
- Styled as a distinct action button (e.g. orange, matching escalation color)
- On click: `POST /api/conversations/<id>/resolve` then updates UI
- Disappears once resolved

### 2.3 Inbox Filter (inbox.html + inbox.js + filter-state.js)

- Add "Escalated" / "Eskaliert" option to the status filter dropdown
- Conversation cards get a `data-escalated="true|false"` attribute
- In `applyFilters()`, when status filter is set to "escalated", check `card.dataset.escalated === 'true'` instead of `card.dataset.status`
- Server-side: use `?escalated=true` query param when this filter is active, to ensure escalated conversations beyond the current page are loaded

### 2.4 i18n (i18n.js)

New translation keys:
- `escalation_needs_attention`: "Braucht Aufmerksamkeit" / "Needs Attention"
- `escalation_resolve`: "Als gelöst markieren" / "Mark as Resolved"
- `ai_auto_respond_on`: "KI aktiv" / "AI Active"
- `ai_auto_respond_off`: "KI pausiert" / "AI Paused"
- `filter_escalated`: "Eskaliert" / "Escalated"
- `push_escalation_title`: "Braucht Aufmerksamkeit" / "Needs Attention"

---

## Data Flow

```
Guest sends message
  -> message_router.process_incoming_message()
    -> _generate_ai_response()
      -> ai_service.generate_guest_response()  (AI generates response)
      -> _is_escalation_response(response)      (scan for phrase)
      -> if escalation detected:
           conversation.escalated = True
           conversation.auto_respond = False
           push_service.notify_escalation()
      -> save AI message, send via platform

Host sees escalated conversation in inbox (orange + label)
  -> clicks into conversation
  -> handles guest issue manually
  -> clicks "Resolve" button
    -> POST /api/conversations/<id>/resolve
      -> conversation.escalated = False
      -> (auto_respond stays False — host controls separately)
```

## Files Modified

| File | Changes |
|------|---------|
| `models.py` | Add `escalated` column to Conversation |
| `migrations/versions/p8_escalation_...py` | New migration |
| `services/message_router.py` | Add `_is_escalation_response()`, wire into `_generate_ai_response()` |
| `services/push_service.py` | Add `notify_escalation()` |
| `routes.py` | Add `/resolve` endpoint, extend conversation API responses |
| `templates/chatbot/inbox.html` | Escalation styling, AI badge |
| `templates/chatbot/conversation.html` | Resolve button |
| `static/js/inbox.js` | Card rendering for escalation + AI status |
| `static/js/conversation.js` | Resolve button handler |
| `static/js/filter-state.js` | Escalated filter option |
| `static/js/i18n.js` | New translation keys |
| `static/css/style.css` | Escalation card styling, AI badge styling |
