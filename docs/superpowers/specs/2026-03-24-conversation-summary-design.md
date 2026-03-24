# Conversation Summary Design

**Date:** 2026-03-24
**Feature:** AI Enhancement Plan #6 — Conversation Summary
**Status:** Approved

## Goal

Give the AI context about older messages that fall outside the recent message window, preventing it from contradicting earlier promises or forgetting key decisions. Purely backend — no UI changes.

## How It Works

When a conversation grows beyond the `max_conversation_history` setting (default: 10 messages), older messages fall out of the AI's context window. Before generating a response, the system checks if a summary is needed and generates one covering everything the AI can no longer see.

### Flow

1. AI response requested for conversation
2. Count total messages in conversation
3. If total <= `max_conversation_history`: skip summarization, proceed normally
4. If total > threshold: check if summary is stale (new messages exist beyond `ai_summary_through_id`)
5. If stale or missing: fetch messages from ID 1 through (newest - max_history), generate summary via Ollama, cache in DB
6. Inject cached summary into system prompt
7. Proceed with normal response generation (recent messages as chat turns)

### Summary Staleness

Track with `ai_summary_through_id` — the ID of the newest message included in the summary. When the message that's about to fall out of the recent window has ID > `ai_summary_through_id`, the summary is stale and needs regeneration.

## Schema Changes

Add two columns to `Conversation`:

```python
ai_summary = db.Column(db.Text, nullable=True)
ai_summary_through_id = db.Column(db.Integer, nullable=True)
```

- `ai_summary`: The cached summary text (bullet points)
- `ai_summary_through_id`: ID of the last message covered by the summary. No FK constraint (simple integer comparison is sufficient and avoids cascade complexity).

Migration: `p9_summary_add_conversation_summary_columns.py`

## AI Service Changes

### New method: `generate_conversation_summary()`

Located in `AIService`. Takes a list of message dicts and returns a compact summary string.

Prompt design:
- System: "You are a summarization assistant. Summarize the following conversation between a vacation rental host and a guest."
- Instructions: "Output a concise bullet-point summary covering: key decisions made, promises or commitments, questions that were answered, any pending/open items. Keep it under 300 words. Write in English regardless of conversation language (internal use only)."
- User message: The formatted conversation messages to summarize

Uses the same `_call_chat_api()` method with a shorter `num_predict` (512 tokens) to keep it fast.

### Modified: `_build_chat_messages()`

New optional parameter: `conversation_summary: Optional[str]`

When provided, inject into the system prompt:

```
=== CONVERSATION SUMMARY (older messages) ===
{summary}
=== The recent messages below follow this summary. ===
```

Placed after the guest profile section, before the conversation history turns.

## Message Router Changes

### Modified: `_generate_ai_response()`

Before calling `_build_chat_messages()`:

1. Count total messages in conversation
2. If count > `max_history`:
   - Calculate the cutoff: the message ID at position `(total - max_history)`
   - If `conversation.ai_summary_through_id` is None or < cutoff ID: summary is stale
   - Fetch messages from start through cutoff ID
   - Call `ai_service.generate_conversation_summary(messages)`
   - Store result in `conversation.ai_summary` and `conversation.ai_summary_through_id`
   - Commit to DB
3. Pass `conversation.ai_summary` to `_build_chat_messages()`

### Performance Consideration

Summary generation goes through the GPU semaphore just like normal responses. When a summary needs updating, there will be two sequential AI calls (summary + response). This only happens when:
- Conversation first exceeds the threshold, OR
- New messages have pushed the cutoff point past the cached summary

For most responses, the cached summary is reused with zero overhead.

## Summary Prompt

```
Summarize this conversation between a vacation rental host and a guest.
Write concise bullet points covering:
- Key decisions made
- Promises or commitments by either party
- Questions that were answered (and the answers)
- Pending or open items

Keep it under 300 words. Write in English.
Do NOT include greetings, pleasantries, or filler.

Conversation:
{formatted_messages}
```

## Files Modified

- `models.py` — Add `ai_summary`, `ai_summary_through_id` to Conversation
- `migrations/versions/p9_summary_*.py` — New migration
- `services/ai_service.py` — Add `generate_conversation_summary()`, modify `_build_chat_messages()`
- `services/message_router.py` — Modify `_generate_ai_response()` to handle summary lifecycle

## Not In Scope

- UI display of summaries (explicitly excluded)
- Settings page toggle (always on when conversation is long enough)
- Separate model for summarization (uses same Ollama model)
- Summary history/versioning (only latest cached)
