# Per-Message AI Suggestion — Design Spec

**Date:** 2026-03-30
**Status:** Approved

## Problem

The AI (qwen3:8b) frequently responds to old/already-answered guest messages instead of the latest one. The model gets overwhelmed by the large system prompt context and fixates on the wrong message.

## Solution

Add a lightbulb icon to each guest message that lets the host explicitly select which message the AI should answer. This sidesteps the "which message?" problem entirely — the host tells the AI exactly what to respond to.

The existing KI-Vorschlag button in the text bar remains unchanged.

## Design Decisions

- **Lightbulb icon on every guest message** — matches the existing KI-Vorschlag icon (`fa-lightbulb`) for visual consistency
- **Draft appears in the textarea** — same flow as KI-Vorschlag, no new UI patterns
- **Slimmed-down prompt** — conversation history + guest profile + property info + host instructions only. No KB entries, reservation info, corrections, conversation summary, or resolved topics. This keeps the prompt small enough for the 8B model to focus.
- **Conversation history included as read-only context** — prevents the AI from repeating answers the host already gave
- **No approval queue** — KI-Vorschlag (both existing and per-message) puts the draft in the textarea for the host to review/edit/send manually. Approval queue only applies to KI-Antwort and KI-Automatisch (auto-sent messages).
- **New dedicated API endpoint** — clean separation from existing `ai-suggest`, no risk of breaking current behavior

## Frontend

### Lightbulb Icon on Guest Messages

- Each guest message bubble gets a small `fa-lightbulb` icon in the message header area, next to the timestamp
- Styled subtly (muted color), highlights on hover
- Only on guest messages — no icon on owner or AI messages
- On click: calls the new endpoint with the message ID
- While generating: icon pulses, textarea shows loading indicator (same pattern as existing KI-Vorschlag)
- Result lands in the textarea as an editable draft
- `pendingCorrectionOriginal` is cleared on click (same as existing suggest flow)

### Template Change (`conversation.html`)

Add the lightbulb icon inside the guest message block:

```html
{% if message.sender_type == 'guest' %}
<button class="btn-suggest-for-message"
    onclick="suggestForMessage({{ message.id }})"
    title="KI-Antwort für diese Nachricht"
    data-i18n-title="conversation.ai.suggestForMessage">
    <i class="fas fa-lightbulb"></i>
</button>
{% endif %}
```

### JavaScript (`conversation.js`)

New function `suggestForMessage(messageId)`:
- Clears `pendingCorrectionOriginal`
- Disables the per-message button (and existing suggest/generate buttons) during generation
- Calls `POST /chatbot/api/conversations/{id}/ai-suggest-for-message` with `{ "message_id": messageId }`
- On success: places suggestion text in the textarea, shows toast
- On error: shows error toast
- Re-enables buttons after completion
- Shares the `activeAiController` AbortController for cancellation

### CSS

```css
.btn-suggest-for-message {
    /* Small, subtle button in message header */
    /* Muted color by default, highlight on hover */
    /* Consistent with existing icon button styles */
}
```

## Backend

### New Route: `POST /api/conversations/<id>/ai-suggest-for-message`

**Request:** `{ "message_id": 123 }`

**Validation:**
- Conversation exists
- AI is enabled for this conversation
- Message exists and belongs to this conversation
- Message is from a guest (`sender_type == 'guest'`)

**Context gathered:**
- Conversation history (up to `max_history` messages)
- Guest profile (from memory service)
- Property info (from conversation)
- Host instructions (from AI settings)
- Tone (from AI settings)

**Context NOT included (to keep prompt slim):**
- Knowledge base entries
- Reservation info
- Corrections
- Conversation summary
- Resolved topics

**Response:** `{ "suggestion": "draft text...", "target_message_id": 123 }`

### AI Service

Reuse existing `generate_guest_response()` method. The method already accepts all context params as optional — we pass `None` for KB, reservation, corrections, summary, resolved topics.

The key change: the `latest_message` parameter receives the selected message's text (not the most recent guest message), and the task instruction in the system prompt is modified to say:

> "The guest sent the following message. Write a reply specifically to THIS message: [selected message text]"

This requires making the task instruction customizable — add an optional `target_message_override` parameter to `generate_guest_response()` (or to `_build_chat_messages()`). When provided, the YOUR TASK section uses the override text instead of the generic "respond to the latest message."

## i18n

New translation key:
- `conversation.ai.suggestForMessage` — DE: "KI-Antwort für diese Nachricht" / EN: "AI suggestion for this message"

## Scope

### In scope
- Lightbulb icon on all guest messages (template + CSS)
- `suggestForMessage()` JS function
- New backend route `/ai-suggest-for-message`
- Task instruction override in AI service
- i18n key
- Cache version bump for conversation.js

### Out of scope
- Changes to existing KI-Vorschlag behavior
- Changes to approval queue logic
- Changes to KI-Antwort or auto-respond
- AI model changes or prompt improvements for the regular flow
