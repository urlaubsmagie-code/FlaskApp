# Compact Prompt Mode — Design Spec

**Date**: 2026-03-30
**Status**: Approved
**Goal**: Make KI-Vorschlag and KI-Antwort produce accurate responses on qwen3:8b by drastically reducing prompt size.

## Problem

The current system prompt for autonomous AI modes (KI-Vorschlag, KI-Antwort) sends ~1,500-2,500 tokens of context. The qwen3:8b model drowns in this context and latches onto reservation data or old messages instead of answering the latest guest question. The per-message suggest (lightbulb) works well because it uses a slimmed prompt — this design applies that principle to all AI modes.

## Design: Two-Tier Prompt System

### Prompt Mode Selection

| AI Mode | Prompt Mode | Reason |
|---------|-------------|--------|
| KI-Antwort (auto-respond) | **Compact** | Must work on 8B, no human in the loop |
| KI-Vorschlag (textbar button) | **Compact** | AI picks which message to answer — needs focus |
| Lightbulb (per-message suggest) | **Current slim** | Already works — we tell it which message |

Selection is automatic based on whether `target_message_override` is set. No settings toggle needed.

### Compact Prompt Structure (~400-600 tokens)

```
1. Role + rules + tone (~100 tokens)
   Shortened to essentials: role, language rule, don't-invent rule, don't-reask rule.
   No 6-line rule list.

2. Guest name + language (~15 tokens)
   "Guest: Maria Schmidt (speaks German)"

3. Reservation one-liner (~30 tokens)
   "Reservation: Jun 5-8, 2 guests, Property: Beach House Mallorca"
   Single line compressed from current multi-line block.

4. Host instructions (~50-100 tokens, if set)
   Kept as-is. These are the host's custom rules — always respected.

5. KB entries (~0-150 tokens, top 3 only, when populated)
   Filtered by existing context_filter. Currently 0 entries — ready for future use.

6. Conversation log — last 4 messages (~150-250 tokens)
   Down from max 10. Each message capped at 150 chars.

7. YOUR TASK — at the end (~50 tokens)
   Latest message repeated. "Write a reply that answers THIS message."
```

### What's Excluded from Compact Mode

- Full guest profile (allergies, pets, family, preferences, interests)
- Property details (amenities, description)
- Conversation summary
- Resolved topics
- Corrections
- Escalation entries

These sections are built for the future and add bulk without helping the 8B model answer current questions. They remain available in the per-message suggest path and can be re-enabled in compact mode later.

## Implementation

### Files Changed

Only `services/ai_service.py`:

1. **New method: `_build_compact_prompt()`**
   - Builds the slim system prompt with sections 1-7 above
   - Returns system prompt string

2. **New helper: `_format_reservation_compact()`**
   - Compresses reservation info to a single line
   - Format: "Reservation: {check_in}-{check_out}, {guests} guests, Property: {name}"

3. **Modified: `_build_chat_messages()`**
   - At the top: if `target_message_override` is set, use current per-message suggest path (unchanged)
   - Otherwise: use `_build_compact_prompt()` for the system message

4. **Modified: `_format_conversation_log()`**
   - New parameter `max_messages` (default 10, compact passes 4)

### Files NOT Changed

- `message_router.py` — still passes all context; compact prompt ignores what it doesn't need
- `context_filter.py` — still filters KB the same way
- `routes.py` — API endpoints unchanged
- Frontend — no UI changes

### Design Principle

Callers keep sending all available context. The compact prompt selectively uses only what it needs. This means re-enabling sections later requires zero changes to callers.

## Constraints

- Must produce good results on qwen3:8b (production model)
- Should be even better on qwen3:14b (current testing model)
- Per-message suggest (lightbulb) behavior must not change
- No new dependencies or settings
