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
5. If stale or missing: fetch messages to summarize, generate summary via Ollama, cache in DB
6. Inject cached summary into system prompt
7. Proceed with normal response generation (recent messages as chat turns)

### Summary Staleness

Track with `ai_summary_through_id` — the ID of the newest message included in the summary. The cutoff message is determined by querying the Nth-from-last message in the conversation:

```python
cutoff_msg = Message.query.filter_by(conversation_id=conv.id) \
    .order_by(Message.sent_at.desc()).offset(max_history).first()
```

If `cutoff_msg` exists and its ID > `ai_summary_through_id`, the summary is stale.

### Incremental Summarization (long conversations)

To avoid sending huge prompts for very long conversations, use an incremental approach:
- If no existing summary: fetch up to 50 oldest unsummarized messages, generate summary
- If existing summary exists: fetch the existing summary + new messages since `ai_summary_through_id` up to the cutoff, ask the AI to update the summary with the new information
- This keeps the summarization prompt bounded regardless of conversation length

## Schema Changes

Add two columns to `Conversation`:

```python
ai_summary = db.Column(db.Text, nullable=True)
ai_summary_through_id = db.Column(db.Integer, nullable=True)
```

- `ai_summary`: The cached summary text (bullet points)
- `ai_summary_through_id`: ID of the last message covered by the summary. No FK constraint (simple integer comparison is sufficient and avoids cascade complexity).

Migration: `p9_summary_add_conversation_summary_columns.py` (revision=`p9_summary`, down_revision=`p8_escalation`)

## AI Service Changes

### New method: `generate_conversation_summary()`

Located in `AIService`. Takes a list of message dicts and an optional existing summary string. Returns a compact summary string or None on failure.

**Parameters:**
- `messages`: List of message dicts to summarize
- `existing_summary`: Optional existing summary to update incrementally

**Prompt design (initial summary):**
- System: "You are a summarization assistant."
- User: Formatted messages with instruction to produce bullet-point summary

**Prompt design (incremental update):**
- System: "You are a summarization assistant."
- User: Existing summary + new messages, with instruction to update the summary

Uses `_call_chat_api()`. Since `_call_chat_api` reads `num_predict` from AISettings, the summary call uses the same token limit. This is acceptable — summaries are naturally short due to the prompt instruction.

### Modified: `_build_chat_messages()`

New optional parameter: `conversation_summary: Optional[str]`

When provided, inject into the system prompt after all context sections (guest profile, property, reservation, knowledge base, host instructions) and before the conversation history turns:

```
=== CONVERSATION SUMMARY (older messages not shown below) ===
{summary}
=== The recent messages below continue from this summary. ===
```

## Message Router Changes

### Modified: `_generate_ai_response()`

Before calling `_build_chat_messages()`:

1. Count total messages in conversation
2. If count > `max_history`:
   - Find the cutoff message: `Message.query.filter_by(conversation_id=...).order_by(Message.sent_at.desc()).offset(max_history).first()`
   - If `conversation.ai_summary_through_id` is None or < cutoff message ID: summary is stale
   - Fetch messages to summarize (between `ai_summary_through_id` and cutoff ID, or first 50 if no existing summary)
   - Call `ai_service.generate_conversation_summary(messages, existing_summary)`
   - If successful: store in `conversation.ai_summary` and `conversation.ai_summary_through_id`, commit
   - If failed: log warning, proceed with existing cached summary (or no summary)
3. Pass `conversation.ai_summary` to `_build_chat_messages()`

### Error Handling

Summary generation failure must never block response generation. If `generate_conversation_summary()` returns None:
- Log a warning
- Proceed with whatever cached summary exists (may be stale or None)
- The AI response is generated normally — just without the summary context
- DB commit failure is also caught and logged without blocking

### Performance Consideration

Summary generation goes through the GPU semaphore just like normal responses. When a summary needs updating, there will be two sequential AI calls (summary + response). Interleaving from other requests between the two calls is possible but acceptable — this only happens when:
- Conversation first exceeds the threshold, OR
- New messages have pushed the cutoff point past the cached summary

For most responses, the cached summary is reused with zero overhead.

## Summary Prompts

### Initial Summary

```
Summarize this conversation between a vacation rental host and a guest.
Write concise bullet points covering:
- Key decisions made
- Promises or commitments by either party
- Questions that were answered (and the answers)
- Pending or open items

Keep it under 300 words. Write in the same language as the conversation.
Do NOT include greetings, pleasantries, or filler.

Conversation:
{formatted_messages}
```

### Incremental Update

```
Here is an existing summary of an ongoing conversation between a vacation rental host and a guest:

{existing_summary}

New messages since the last summary:
{new_messages}

Update the summary to include the new information.
Keep the same bullet-point format. Keep it under 300 words.
Write in the same language as the conversation.
Remove items that are no longer pending. Add new decisions, promises, or open items.
```

Note: Summaries are written in the conversation's language (not forced to English) since the local model (qwen3:8b) produces better summaries in the source language.

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
