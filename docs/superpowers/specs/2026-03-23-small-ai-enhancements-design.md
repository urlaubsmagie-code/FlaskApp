# Small AI Enhancements Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Scope:** 3 small features to harden the AI pipeline before larger enhancements

---

## Feature 1: Response Quality Guards

### Goal
Strip model artifacts and reject broken responses before they reach guests.

### Implementation

**New method `_clean_ai_response(text)` in `AIService`**, called in `generate_guest_response` after getting the raw response from `_call_chat_api`.

**Artifact stripping** (regex removal):
- Instruction tags: `[INST]`, `[/INST]`, `<<SYS>>`, `<</SYS>>`
- Role markers: `<|assistant|>`, `<|user|>`, `<|im_start|>`, `<|im_end|>`, `<|end|>`
- Token markers: `<s>`, `</s>`
- Thinking blocks: `<think>...</think>` (qwen3 chain-of-thought — strip entire block including content)
- Final whitespace cleanup after stripping

**Length guards:**
- Minimum 10 characters: reject (return None), log warning
- Maximum 2000 characters: truncate at last sentence boundary (`.`, `!`, `?`) before the limit. If no sentence boundary found, hard truncate at 2000.

**Temperature default:**
- Change default from `0.5` to `0.3` in `_populate_default_settings()` in `models.py`
- Only affects fresh installs — existing DB values are preserved

### Files changed
- `services/ai_service.py`: Add `_clean_ai_response()`, call it in `generate_guest_response`
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

1. **Numbering consecutive guest messages**: When merging consecutive user-role messages, number them with `[1]`, `[2]`, `[3]` prefixes instead of plain concatenation. Only applied when there are 2+ consecutive guest messages.

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

2. **Dynamic system prompt**: Track whether the final user turn has multiple unanswered messages.
   - 1 message: Current instruction — "The guest's MOST RECENT message is: '...'. Write a reply ONLY for this latest message."
   - 2+ messages: "The guest has sent N unanswered messages (numbered [1]-[N] in the final message). Address ALL of them in a single reply."

### Files changed
- `services/ai_service.py`: Modify merge logic in `_build_chat_messages`, update system prompt generation

---

## Feature 3: Restricted Topics via Knowledge Base

### Goal
Let hosts define topics the AI must never handle, using the existing Knowledge Base UI.

### Implementation

**New KB category `escalation`:**
- Added to `KnowledgeEntry.VALID_CATEGORIES` in `models.py`
- No DB migration needed — category is a string column

**AI prompt handling** in `_build_chat_messages`:
- Split `knowledge_entries` into regular entries and escalation entries
- Regular entries: formatted as today under `=== HOST KNOWLEDGE BASE ===`
- Escalation entries: separate prompt section:
  ```
  === RESTRICTED TOPICS ===
  You MUST NOT answer questions about these topics yourself.
  Instead, reply with something like: "I'll check with my colleague and get back to you shortly."
  (Always in the guest's language.)

  - Refunds / Rueckerstattung
  - Cancellations / Stornierung
  ```

**UI changes in `knowledge.js`:**
- Add to `CATEGORY_LABELS`: `escalation: { de: 'Eskalation', en: 'Escalation' }`
- Add to `CATEGORY_ICONS`: `escalation: 'fa-exclamation-triangle'`
- Add to `CATEGORY_ORDER` array

**Backend in `_format_knowledge_entries`:**
- Add `'escalation'` to the category iteration order
- Escalation entries are excluded from the regular KB formatting (handled separately)

### Files changed
- `models.py`: Add `'escalation'` to `VALID_CATEGORIES`
- `services/ai_service.py`: Split KB entries, add restricted topics section to prompt, update `_format_knowledge_entries` to skip escalation entries
- `static/js/knowledge.js`: Add escalation category label, icon, order

---

## What is NOT in scope
- Escalation system (pausing auto-respond, push notification) — that's Feature #4 (medium)
- Inbox status indicators — Feature #5 (medium)
- Any new DB tables or migrations
- Settings UI changes (temperature is already configurable)
