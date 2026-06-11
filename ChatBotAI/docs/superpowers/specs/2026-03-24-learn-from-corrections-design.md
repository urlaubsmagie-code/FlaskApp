# Learn from Corrections — Design Spec

**Date:** 2026-03-24
**Feature:** #8 from AI Enhancement Plan
**Status:** Approved

## Overview

When a host edits an AI draft before sending, the system automatically captures both versions as a "correction". These corrections are loaded into the AI prompt for future responses, filtered by property and recency. Corrections are stored as `KnowledgeEntry` records (category `correction`) and managed in the existing Wissensdatenbank page under a dedicated "Korrekturen" tab.

## Key Decisions

- **Capture method:** Automatic on edit+send (no extra clicks)
- **Storage:** Reuse `KnowledgeEntry` table with `category='correction'`
- **Relevance filtering:** Property-based + recency (up to 7 same-property + 3 global, max 10)
- **Prompt format:** Dedicated `PAST CORRECTIONS:` section in system prompt
- **Management UI:** New "Korrekturen" tab in Wissensdatenbank (alongside Wissen and Eskalation tabs)

## Data Model

No new tables. Corrections use the existing `KnowledgeEntry` model:

| Field | Usage for corrections |
|-------|----------------------|
| `category` | `'correction'` |
| `label` | AI-extracted topic (e.g. "Parking", "Pool hours") |
| `value` | Formatted: `FALSCH: [original AI text]\nRICHTIG: [corrected host text]` |
| `property_id` | From the conversation's property (NULL = global) |
| `created_at` | When the correction was captured |

No migration needed — the existing `KnowledgeEntry` schema supports this directly.

## Capture Flow

### Frontend (conversation.js)

1. Host clicks "Edit" on a pending AI draft
2. Existing `editMessage()` function rejects the draft and puts text in textarea
3. **New:** Before rejecting, save the original AI text to a module-level variable: `pendingCorrectionOriginal = content`
4. Host modifies text and clicks Send
5. **New:** `sendMessage()` checks if `pendingCorrectionOriginal` is set
6. If set, include it in the POST body: `{ content: "...", original_ai_content: "..." }`
7. Clear `pendingCorrectionOriginal` after sending

### Backend (routes.py — send message endpoints)

When the send endpoint receives `original_ai_content`:

1. Compare `original_ai_content` with `content` using a simple similarity check
2. If texts differ meaningfully (not just whitespace/punctuation — use ratio < 0.90 via `difflib.SequenceMatcher`):
   - Look up the conversation's `property_id`
   - Create a `KnowledgeEntry` with `category='correction'`, `property_id`, and formatted value
   - Set `label` to `'(wird extrahiert...)'` as placeholder
   - Kick off topic extraction (see below)
3. If texts are too similar (ratio >= 0.90), skip — it was just a typo fix

### Topic Extraction

After storing the correction, extract a topic label via a lightweight AI call:

**Prompt:** "Given this original AI response and the host's corrected version, what is the topic of this correction in 1-3 words? Respond with ONLY the topic words, nothing else.\n\nOriginal: [original]\nCorrected: [corrected]"

- Runs synchronously after creating the KnowledgeEntry (updates the `label` field)
- If AI is unavailable or fails, keep `label` as the placeholder — correction still works via property/recency
- Uses low token limit (max_tokens=20) for fast response

## AI Prompt Integration

### Loading (message_router.py — `_generate_ai_response()`)

The existing code already loads `knowledge_entries` for the AI. Corrections are loaded alongside but kept separate:

1. Query `KnowledgeEntry` where `category='correction'` and (`property_id` matches conversation's property OR `property_id IS NULL`)
2. Filter `is_active=True` (if field exists, else just all)
3. Order by `created_at DESC`
4. Take up to 7 same-property + up to 3 global (NULL property_id), max 10 total
5. Pass as new parameter `corrections` to `generate_guest_response()`

### Prompt Format (ai_service.py — `_build_chat_messages()`)

Add a new section to the system prompt after knowledge entries:

```
PAST CORRECTIONS (you made these mistakes before — don't repeat them):
- "Parking": Don't say "free parking available" → Correct: "Street parking only, no dedicated spots"
- "Pool": Don't say "pool is heated" → Correct: "Pool is unheated, open May-September"
```

Parse the `value` field (split on `\nRICHTIG: `) to extract original and corrected parts for formatting.

If no corrections exist, omit this section entirely.

## Wissensdatenbank UI Changes

### Tab Layout

Replace the current flat list with three tabs at the top of the Knowledge Base page:

```
[Wissen]  [Eskalation]  [Korrekturen]
```

- **Wissen** — Shows entries with categories: general, checkin, nearby, rules, emergency, faq (existing behavior)
- **Eskalation** — Shows entries with category: escalation (existing, currently mixed in)
- **Korrekturen** — Shows entries with category: correction (new)

Active tab is highlighted. Tab state persists via URL parameter `?tab=knowledge|escalation|corrections` (default: knowledge).

### Tab Implementation

- Tabs are simple buttons that show/hide sections (no page reload)
- Each section has its own add button and entry list
- The existing property filter dropdown applies across all tabs
- The existing add/edit modal works for all tabs — when adding from Korrekturen tab, category is pre-set to `correction`

### Korrekturen Tab Content

Each correction entry shows:
- **Topic label** (from `label` field)
- **Property name** (or "Global" if no property)
- **Original vs Corrected preview** — parsed from `value` field, truncated to ~100 chars each
- **Date** (from `created_at`)
- **Edit and Delete buttons** (same as other knowledge entries)

Empty state: "Noch keine Korrekturen. Wenn Sie KI-Entwürfe bearbeiten, lernt die KI automatisch daraus."

### Corrections can also be added manually

The host can click "Add" in the Korrekturen tab and manually enter:
- Label (topic)
- Value (in the FALSCH:/RICHTIG: format, or freeform — AI will use it either way)
- Property scope

This lets hosts proactively teach the AI without waiting for a bad response.

## i18n Keys

### German (de)
```
'knowledge.tab.knowledge': 'Wissen'
'knowledge.tab.escalation': 'Eskalation'
'knowledge.tab.corrections': 'Korrekturen'
'knowledge.cat.correction': 'Korrektur'
'knowledge.corrections.empty': 'Noch keine Korrekturen'
'knowledge.corrections.empty.hint': 'Wenn Sie KI-Entwürfe bearbeiten, lernt die KI automatisch daraus.'
'knowledge.corrections.original': 'KI sagte'
'knowledge.corrections.corrected': 'Richtig ist'
'knowledge.corrections.autoSaved': 'KI-Korrektur gespeichert'
```

### English (en)
```
'knowledge.tab.knowledge': 'Knowledge'
'knowledge.tab.escalation': 'Escalation'
'knowledge.tab.corrections': 'Corrections'
'knowledge.cat.correction': 'Correction'
'knowledge.corrections.empty': 'No corrections yet'
'knowledge.corrections.empty.hint': 'When you edit AI drafts, the AI automatically learns from your changes.'
'knowledge.corrections.original': 'AI said'
'knowledge.corrections.corrected': 'Correct is'
'knowledge.corrections.autoSaved': 'AI correction saved'
```

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Host edits but sends identical text | No correction stored (similarity >= 0.90) |
| Host clicks Edit but doesn't send | `pendingCorrectionOriginal` cleared on next draft generation or page navigation |
| Conversation has no property | Correction stored with `property_id=NULL` (global) |
| Topic extraction fails | `label` stays as placeholder, correction still loaded by property/recency |
| Host deletes correction in Wissensdatenbank | Standard KnowledgeEntry delete — removed from future prompts |
| Too many corrections for one property | Limited to 7 per property + 3 global in prompt (oldest dropped) |

## Files Changed

- `static/js/conversation.js` — capture original text on edit, send with message
- `routes.py` — store correction on message send, topic extraction
- `services/ai_service.py` — add corrections section to system prompt
- `services/message_router.py` — load corrections for AI context
- `templates/chatbot/knowledge.html` — tab layout (Wissen/Eskalation/Korrekturen)
- `static/js/knowledge.js` — tab switching, correction entry rendering
- `static/css/style.css` — tab styles
- `static/js/i18n.js` — new translation keys
