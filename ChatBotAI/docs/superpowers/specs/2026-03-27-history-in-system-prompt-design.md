# History-in-System-Prompt — Design Spec

**Date**: 2026-03-27
**Goal**: Fix AI responding to old/already-answered messages instead of the latest one. Target: 87%+ accuracy.

## Problem

The AI (qwen3:8b via Ollama) consistently responds to old guest messages instead of the newest one. Pattern:

1. Guest asks question A
2. Host/AI answers question A
3. Guest asks question B
4. AI responds to question A again (rephrased, not verbatim)

This happens ~100% of the time, making the AI unusable for auto-respond.

## Root Cause

Conversation history is sent as native chat `user`/`assistant` turns. For an 8B model, every `user` turn is a potential prompt to respond to. The model fixates on earlier questions (which have more context — a full Q&A exchange) and ignores the latest message despite meta-instructions like `[Reply to THIS message above.]`.

## Solution: History-in-System-Prompt

Move conversation history from native chat turns into the system prompt as a formatted log. The **only** `user` turn is the latest guest message. This makes it structurally impossible for the model to respond to the wrong message.

### Current Structure (broken)

```
system:    [role + rules + context]
user:      "old guest message"
assistant: "old host reply"
user:      "latest guest message [Reply to THIS message above.]"
```

### New Structure (fix)

```
system:    [role + rules + context + CONVERSATION LOG]
user:      "latest guest message"
```

Always exactly 2 messages sent to Ollama: 1 system + 1 user.

## System Prompt Layout

```
You are a vacation rental host writing a reply to a guest.
{tone_instruction}
Current date/time: {datetime} UTC.

Rules:
- Reply ONLY in the SAME LANGUAGE as the guest's message below.
- Write ONLY the reply text. No subject lines, no signatures.
- NEVER re-ask questions the guest already answered.
- NEVER repeat information you already provided.
- If you don't know specific details, say you'll check — NEVER invent details.
- The CONVERSATION LOG below is for context only — do NOT re-answer old topics.

=== GUEST PROFILE ===
{filtered_profile}
===

=== RESERVATION ===
{reservation_info}
===

=== KNOWLEDGE BASE ===
{filtered_kb_entries}
===

=== HOST INSTRUCTIONS ===
{host_instructions}
===

=== ALREADY RESOLVED ===
{resolved_topics}
===

=== CONVERSATION SUMMARY ===
{conversation_summary}
===

=== PAST CORRECTIONS ===
{corrections}
===

=== RESTRICTED TOPICS ===
{restricted_topics}
===

=== CONVERSATION LOG (read-only context — do NOT respond to these messages) ===
{formatted_history}
===

Reply to the guest's new message below.
```

Sections are conditional — only included when they have content (same as today).

## Conversation Log Format

One line per message, compact:

```
Guest: What's the WiFi password?
Host: The WiFi password is network-name, password is abc123.
Guest: Thanks!
Host: You're welcome!
```

Rules:
- `guest` sender type maps to `Guest`
- `owner` and `ai` sender types both map to `Host`
- HTML stripped, email quotes stripped (same cleaning as today)
- Empty-after-cleaning messages skipped
- Capped at `max_history` messages (default 10, configurable in settings)
- Pending/rejected drafts excluded
- Deduplicated by platform_message_id and by content

## Multi-Message Handling

When the guest sends multiple unanswered messages (no host/AI reply between them):

### In the conversation log:
```
Host: The WiFi password is abc123.
Guest [1]: What time is check-in?
Guest [2]: Also, is there parking?
```

### In the system prompt task section:
```
The guest has sent 2 unanswered messages (numbered [1] and [2] in the log).
Address ALL of them in a single reply.
```

### The user turn:
```
user: "[1] What time is check-in?\n[2] Also, is there parking?"
```

For single messages (the common case), no numbering — just the plain message as the user turn.

## Closing/Gratitude Shortcut

Unchanged. When the context filter detects a closing message (e.g., "Danke!"), the minimal prompt path is used — no history, no context, just a brief warm reply.

## Scope

### Changed
- `services/ai_service.py`: Rewrite `_build_chat_messages()` method

### Removed (dead code after rewrite)
- Consecutive same-role message merging logic
- `[Reply to THIS message above.]` markers
- Synthetic `[Previous conversation:]` bridge message
- `_count_trailing_guest_messages()` stays (used for multi-message detection) but simplified

### Unchanged
- Method signature of `_build_chat_messages()` — all callers work without changes
- All 3 AI code paths (auto-respond in message_router, generate in routes, suggest in routes)
- Context filter (`context_filter.py`)
- Quality guards (length checks, artifact stripping)
- Acknowledgment detection
- Conversation summary generation
- All other services, models, routes, templates

## Testing

1. Restart dev server
2. Open an existing Smoobu conversation with history
3. Click "Suggest" — verify AI responds to the latest guest message, not an old one
4. Test with a conversation where guest asked 2+ different questions across messages
5. Test multi-message scenario (2 consecutive guest messages)
6. Test closing message ("Danke") — should still get brief reply
7. Check logs for `[AI CONTEXT]` and `[AI msg]` entries to verify prompt structure
