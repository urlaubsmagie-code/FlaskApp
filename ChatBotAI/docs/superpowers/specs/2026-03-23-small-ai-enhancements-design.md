# Small AI Enhancements Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Scope:** 3 small features to harden the AI pipeline before larger enhancements

---

## Feature 1: Response Quality Guards

### Goal
Strip model artifacts and reject broken responses before they reach guests.

### Implementation

**New method `_clean_ai_response(text)` in `AIService`**, called in `generate_guest_response` between the `_call_chat_api` call and the existing truthiness check. Replaces the current `if response:` / `return response` block — cleaning runs first, then the cleaned result is checked.

If the cleaned result is `None` (failed length guard) or empty, the method returns `None` — this propagates as a silent no-response (no AI message stored, no retry). This is intentional: a broken response is worse than no response.

**Artifact stripping** (regex removal):
- Instruction tags: `[INST]`, `[/INST]`, `<<SYS>>`, `<</SYS>>`
- Role markers: `<|assistant|>`, `<|user|>`, `<|im_start|>`, `<|im_end|>`, `<|end|>`
- Token markers: `<s>`, `</s>`
- Thinking blocks: `<think>...</think>` (qwen3 chain-of-thought — strip entire block including content; regex uses `re.DOTALL` for multi-line blocks)
- Final whitespace cleanup after stripping

**Think-tag stripping in `extract_guest_info`:** The `<think>` block also appears in JSON extraction responses and would break JSON parsing. Add a lightweight `_strip_think_tags(text)` static method and call it in `extract_guest_info` before JSON parsing (before the existing `clean_response` logic). This is separate from the full `_clean_ai_response` which includes length guards not appropriate for extraction.

**Length guards (guest responses only):**
- Minimum 10 characters: reject (return None), log warning
- Maximum 2000 characters: truncate at last sentence boundary (`.`, `!`, `?`) before the limit. If no sentence boundary found, hard truncate at 2000.

**Temperature default:**
- Change default from `0.5` to `0.3` in `_populate_default_settings()` in `models.py`
- Only affects fresh installs — existing DB values are preserved

### Files changed
- `services/ai_service.py`: Add `_clean_ai_response()`, `_strip_think_tags()`, call in `generate_guest_response` and `extract_guest_info`
- `models.py`: Update default temperature in `_populate_default_settings`

---

## Feature 2: Latest Message Fix

### Goal
Ensure the AI addresses all unanswered guest messages, not just one arbitrary part of a merged block.

### Problem
When a guest sends multiple consecutive messages (no host reply between them), they get merged into a single user turn. The AI may respond to the wrong one, or miss some entirely.

Example:
- Guest: "Hallo!"
- Guest: "Gibt es ein Restaurant in der Naehe?"
- Guest: "Ich warte auf eure Antwort!"

These merge into one user turn, and the AI might only respond to "Hallo!".

### Implementation

**In `_build_chat_messages`:**

**Step 1 — Pre-scan for consecutive trailing guest messages** (before building system prompt):
Scan the cleaned conversation history backwards from the end to count consecutive guest messages that have no host/AI reply between them. This count (`unanswered_count`) is available when constructing the system prompt.

**Step 2 — Dynamic system prompt:**
- `unanswered_count == 1`: Current instruction — "The guest's MOST RECENT message is: '...'. Write a reply ONLY for this latest message."
- `unanswered_count >= 2`: "The guest has sent N unanswered messages (numbered [1]-[N] in their turn below). Address ALL of them in a single reply."

Note: `clean_latest` (the trigger message parameter) contains only the single triggering message. When `unanswered_count >= 2`, the system prompt references the numbered block in the conversation turns rather than quoting `clean_latest` directly.

**Step 3 — Numbered merging of consecutive guest messages:**
When merging consecutive user-role messages, apply numbering with `[1]`, `[2]`, `[3]` prefixes instead of plain concatenation. Only when 2+ consecutive.

Single message (no change):
```
Gibt es ein Restaurant in der Naehe?
```

Multiple consecutive messages:
```
[1] Hallo!
[2] Gibt es ein Restaurant in der Naehe?
[3] Ich warte auf eure Antwort!
```

### Files changed
- `services/ai_service.py`: Pre-scan in `_build_chat_messages`, modify merge logic, update system prompt generation

---

## Feature 3: Restricted Topics via Knowledge Base

### Goal
Let hosts define topics the AI must never handle, using the existing Knowledge Base UI.

### Implementation

**New KB category `escalation`:**
- Added to `KnowledgeEntry.VALID_CATEGORIES` in `models.py`
- No DB migration needed — category is a string column

**AI prompt handling** — filtering in `_build_chat_messages` (not inside `_format_knowledge_entries`):
1. Before calling `_format_knowledge_entries`, split `knowledge_entries` list:
   - `regular_entries` = entries where `category != 'escalation'`
   - `escalation_entries` = entries where `category == 'escalation'`
2. Pass only `regular_entries` to `_format_knowledge_entries` (unchanged behavior)
3. Build a separate `=== RESTRICTED TOPICS ===` block from `escalation_entries`:
   ```
   === RESTRICTED TOPICS ===
   You MUST NOT answer questions about these topics yourself.
   Instead, reply with something like: "I'll check with my colleague and get back to you shortly."
   (Always in the guest's language.)

   - Refunds / Rueckerstattung
   - Cancellations / Stornierung
   ```
4. Append this block to the system prompt after the KB section

**`_format_knowledge_entries` stays unchanged** — it never sees escalation entries. No need to add `'escalation'` to its category iteration order.

**UI changes:**

`static/js/knowledge.js`:
- Add to `CATEGORY_LABELS`: `escalation: { de: 'Eskalation', en: 'Escalation' }`
- Add to `CATEGORY_ICONS`: `escalation: 'fa-exclamation-triangle'`
- Add `'escalation'` to `CATEGORY_ORDER` array

`templates/chatbot/knowledge.html`:
- Add `<option value="escalation" data-i18n="knowledge.cat.escalation">Eskalation</option>` to the category `<select>` in the add/edit modal

`static/js/i18n.js`:
- Add German key: `'knowledge.cat.escalation': 'Eskalation'`
- Add English key: `'knowledge.cat.escalation': 'Escalation'`

### Files changed
- `models.py`: Add `'escalation'` to `VALID_CATEGORIES`
- `services/ai_service.py`: Filter KB entries in `_build_chat_messages`, add restricted topics prompt section
- `static/js/knowledge.js`: Add escalation category label, icon, order
- `templates/chatbot/knowledge.html`: Add escalation option to category dropdown
- `static/js/i18n.js`: Add i18n keys for escalation category

---

## What is NOT in scope
- Escalation system (pausing auto-respond, push notification) — that's Feature #4 (medium)
- Inbox status indicators — Feature #5 (medium)
- Any new DB tables or migrations
- Settings UI changes (temperature is already configurable)
