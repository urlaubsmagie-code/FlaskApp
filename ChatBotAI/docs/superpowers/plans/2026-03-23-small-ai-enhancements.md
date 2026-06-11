# Small AI Enhancements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the AI pipeline with response quality guards, fix the latest message targeting issue, and add restricted topic support via KB escalation category.

**Architecture:** Three independent changes to `services/ai_service.py` (the core AI pipeline), with minor additions to `models.py` (category + default), `knowledge.js` / `knowledge.html` / `i18n.js` (UI for escalation category). No new DB migrations.

**Tech Stack:** Python/Flask, Ollama chat API, SQLAlchemy, Jinja2, vanilla JS

**Spec:** `docs/superpowers/specs/2026-03-23-small-ai-enhancements-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `services/ai_service.py` | Modify | All 3 features: cleaning methods, prompt restructuring, KB filtering |
| `models.py` | Modify | Add `escalation` category, lower default temperature |
| `static/js/knowledge.js` | Modify | Escalation category label, icon, order |
| `templates/chatbot/knowledge.html` | Modify | Escalation option in category dropdown |
| `static/js/i18n.js` | Modify | i18n keys for escalation category |

---

## Task 1: Response Quality Guards — `_strip_think_tags` and `_clean_ai_response`

**Files:**
- Modify: `services/ai_service.py:480-487` (generate_guest_response return block)
- Modify: `services/ai_service.py:374-382` (extract_guest_info JSON cleanup)

- [ ] **Step 1: Add `_strip_think_tags` static method**

Add after the existing `_strip_email_quotes` method (after line 784) in `AIService`:

```python
@staticmethod
def _strip_think_tags(text: str) -> str:
    """Strip <think>...</think> blocks from model output (qwen3 chain-of-thought)."""
    if not text or '<think>' not in text:
        return text
    # Strip closed think blocks
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Strip unclosed think tag (model stopped mid-thought)
    text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
    return text.strip()
```

- [ ] **Step 2: Add `_clean_ai_response` method**

Add right after `_strip_think_tags`:

```python
def _clean_ai_response(self, text: str) -> Optional[str]:
    """Clean AI response: strip artifacts, enforce length guards.

    Returns cleaned text, or None if response is broken/empty.
    """
    if not text:
        return None

    # Strip thinking blocks first (can be large)
    text = self._strip_think_tags(text)

    # Strip model artifacts
    artifact_patterns = [
        r'\[INST\]', r'\[/INST\]',
        r'<<SYS>>', r'<</SYS>>',
        r'<\|assistant\|>', r'<\|user\|>', r'<\|system\|>',
        r'<\|im_start\|>', r'<\|im_end\|>',
        r'<\|end\|>',
        r'<s>', r'</s>',
    ]
    for pattern in artifact_patterns:
        text = re.sub(pattern, '', text)

    # Clean up whitespace left by stripping
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    # Minimum length guard
    if len(text) < 10:
        logger.warning(f"[AI QUALITY] Response too short ({len(text)} chars), rejecting: '{text}'")
        return None

    # Maximum length guard — truncate at sentence boundary
    if len(text) > 2000:
        original_len = len(text)
        truncated = text[:2000]
        # Find last sentence boundary
        last_boundary = max(
            truncated.rfind('.'),
            truncated.rfind('!'),
            truncated.rfind('?')
        )
        if last_boundary > 100:  # Only use boundary if it leaves a reasonable response
            text = truncated[:last_boundary + 1]
        else:
            text = truncated
        logger.info(f"[AI QUALITY] Response truncated from {original_len} to {len(text)} chars")

    return text
```

- [ ] **Step 3: Wire `_clean_ai_response` into `generate_guest_response`**

Replace lines 480-487 in `generate_guest_response`:

```python
# OLD:
        response = self._call_chat_api(messages, timeout=self.timeout)

        if response:
            logger.info(f"[AI RESPONSE] guest='{guest_name}' | length={len(response)} chars | preview='{response[:80]}'")
            return response
        else:
            logger.warning(f"[AI FAILED] guest='{guest_name}' | No response from Ollama")
            return None
```

```python
# NEW:
        response = self._call_chat_api(messages, timeout=self.timeout)

        if not response:
            logger.warning(f"[AI FAILED] guest='{guest_name}' | No response from Ollama")
            return None

        response = self._clean_ai_response(response)
        if not response:
            logger.warning(f"[AI FAILED] guest='{guest_name}' | Response rejected by quality guards")
            return None

        logger.info(f"[AI RESPONSE] guest='{guest_name}' | length={len(response)} chars | preview='{response[:80]}'")
        return response
```

- [ ] **Step 4: Wire `_strip_think_tags` into `extract_guest_info`**

In `extract_guest_info`, add think-tag stripping before the existing JSON cleanup (before line 375):

```python
# OLD (line 374-375):
                # Clean up response - sometimes AI adds markdown code blocks
                clean_response = response.strip()
```

```python
# NEW:
                # Strip think tags first (qwen3 chain-of-thought)
                clean_response = self._strip_think_tags(response)
                # Clean up response - sometimes AI adds markdown code blocks
                clean_response = clean_response.strip()
```

- [ ] **Step 5: Lower default temperature**

In `models.py` line 638, change:

```python
# OLD:
        ('ai_temperature', '0.5', 'AI response temperature (0.0 = deterministic, 1.0 = creative)'),
```

```python
# NEW:
        ('ai_temperature', '0.3', 'AI response temperature (0.0 = deterministic, 1.0 = creative)'),
```

- [ ] **Step 6: Commit**

```bash
git add services/ai_service.py models.py
git commit -m "feat(ai): add response quality guards

Strip model artifacts ([INST], <think>, role markers) and enforce
length guards (min 10, max 2000 chars with sentence-boundary truncation).
Lower default temperature from 0.5 to 0.3 for new installs."
```

---

## Task 2: Latest Message Fix — Pre-scan + Numbered Merging

**Files:**
- Modify: `services/ai_service.py:532-552` (system prompt construction)
- Modify: `services/ai_service.py:662-678` (merge logic)

- [ ] **Step 1: Add pre-scan helper method**

Add a new static method to `AIService` (after `_strip_email_quotes`):

```python
@staticmethod
def _count_trailing_guest_messages(clean_history: list) -> int:
    """Count consecutive guest messages at the end of the history (no host/AI reply between them)."""
    count = 0
    for msg in reversed(clean_history):
        if msg.get('sender_type') == 'guest':
            count += 1
        else:
            break
    return count
```

- [ ] **Step 2: Pre-scan in `_build_chat_messages`**

In `_build_chat_messages`, add the pre-scan **before the system prompt construction** (before line 532, right after `clean_latest` is computed around line 530). This must run early because `unanswered_count` is used in the system prompt. We scan the raw `conversation_history` parameter (already available) instead of `clean_history` (not yet built):

```python
        # Pre-scan: count consecutive trailing guest messages for dynamic system prompt
        # Uses raw conversation_history (available from method params) since clean_history isn't built yet
        unanswered_count = self._count_trailing_guest_messages(conversation_history)
```

Note: `_count_trailing_guest_messages` checks `msg.get('sender_type')` which works on both raw message dicts (from `Message.to_dict()`) and the cleaned history format.

- [ ] **Step 3: Update system prompt to be dynamic**

Replace the static conversation flow section (lines 546-552). The original `system_parts = [...]` list literal (starting at line 534) must be **closed with `]`** after `"Previous guest messages have ALREADY been answered by the host.",` — then the conditional logic uses `.extend()`:

```python
# OLD (lines 546-552, inside the system_parts = [...] list):
            "=== CONVERSATION FLOW ===",
            "The full conversation follows as user/assistant turns.",
            "Previous guest messages have ALREADY been answered by the host.",
            f'The guest\'s MOST RECENT message is: "{clean_latest[:300]}"',
            "Write a reply ONLY for this latest message above.",
            "Do NOT re-answer earlier questions that the host already addressed.",
            "===",
        ]
```

```python
# NEW (close the list, then extend conditionally):
            "=== CONVERSATION FLOW ===",
            "The full conversation follows as user/assistant turns.",
            "Previous guest messages have ALREADY been answered by the host.",
        ]

        if unanswered_count >= 2:
            system_parts.extend([
                f"The guest has sent {unanswered_count} unanswered messages (numbered [1]-[{unanswered_count}] in their turn below).",
                "Address ALL of them in a single reply.",
            ])
        else:
            system_parts.extend([
                f'The guest\'s MOST RECENT message is: "{clean_latest[:300]}"',
                "Write a reply ONLY for this latest message above.",
            ])

        system_parts.extend([
            "Do NOT re-answer earlier questions that the host already addressed.",
            "===",
        ])
```

The remaining code after line 553 (the `if guest_language:` check, etc.) stays unchanged — it already uses `system_parts.append()` which works with the closed list.

- [ ] **Step 4: Modify merge logic for numbered consecutive guest messages**

Replace the user-message merge logic (lines 662-678). Note: lines 662-665 are comments before `merged = []` at line 666 — include all of them:

```python
# OLD (lines 662-678):
        # Merge remaining consecutive same-role messages (Ollama requires alternating roles)
        # For consecutive user messages: CONCATENATE all of them (preserves full context)
        # For consecutive assistant messages: merge them together
        # Add short relative timestamps as prefixes for temporal awareness
        merged = []
        for msg in collapsed:
            time_prefix = f"[{msg['time_label']}] " if msg.get('time_label') else ""
            content_with_time = f"{time_prefix}{msg['content']}"

            if merged and merged[-1]['role'] == msg['role']:
                if msg['role'] == 'user':
                    # Concatenate guest messages so no context is lost
                    merged[-1]['content'] += "\n" + content_with_time
                else:
                    merged[-1]['content'] += "\n\n" + content_with_time
            else:
                merged.append({'role': msg['role'], 'content': content_with_time})
```

```python
# NEW (replaces lines 662-678):
        # Merge remaining consecutive same-role messages (Ollama requires alternating roles)
        # For consecutive user messages: NUMBER them [1], [2], [3] when 2+ consecutive
        # For consecutive assistant messages: merge them together
        # Add short relative timestamps as prefixes for temporal awareness
        merged = []
        # Track consecutive user messages for numbering
        _consecutive_user_count = 0

        for msg in collapsed:
            time_prefix = f"[{msg['time_label']}] " if msg.get('time_label') else ""
            content_with_time = f"{time_prefix}{msg['content']}"

            if merged and merged[-1]['role'] == msg['role']:
                if msg['role'] == 'user':
                    _consecutive_user_count += 1
                    if _consecutive_user_count == 2:
                        # Retroactively number the first message
                        merged[-1]['content'] = f"[1] {merged[-1]['content']}"
                    # Number this message
                    numbered = f"[{_consecutive_user_count}] {content_with_time}"
                    merged[-1]['content'] += "\n" + numbered
                else:
                    merged[-1]['content'] += "\n\n" + content_with_time
            else:
                if msg['role'] == 'user':
                    _consecutive_user_count = 1
                else:
                    _consecutive_user_count = 0
                merged.append({'role': msg['role'], 'content': content_with_time})
```

- [ ] **Step 5: Commit**

```bash
git add services/ai_service.py
git commit -m "feat(ai): fix latest message targeting with numbered merging

When guest sends multiple consecutive messages, number them [1], [2], [3]
and instruct the AI to address all unanswered messages in a single reply.
Pre-scans history to dynamically adjust system prompt."
```

---

## Task 3: Restricted Topics via KB Escalation Category

**Files:**
- Modify: `models.py:511-514` (VALID_CATEGORIES)
- Modify: `services/ai_service.py:576-579` (_build_chat_messages KB handling)
- Modify: `static/js/knowledge.js:6-24` (category constants)
- Modify: `templates/chatbot/knowledge.html:76-83` (category dropdown)
- Modify: `static/js/i18n.js:354-359,718-723` (i18n keys)

- [ ] **Step 1: Add `escalation` to `VALID_CATEGORIES`**

In `models.py` line 511-514:

```python
# OLD:
    VALID_CATEGORIES = [
        'general', 'checkin_checkout', 'nearby',
        'house_rules', 'emergency', 'faq'
    ]
```

```python
# NEW:
    VALID_CATEGORIES = [
        'general', 'checkin_checkout', 'nearby',
        'house_rules', 'emergency', 'faq', 'escalation'
    ]
```

- [ ] **Step 2: Add `_format_restricted_topics` method**

Add a new static method to `AIService` (after `_format_knowledge_entries`):

```python
@staticmethod
def _format_restricted_topics(escalation_entries: List[Dict[str, Any]]) -> str:
    """Format escalation KB entries as restricted topics for the AI prompt."""
    if not escalation_entries:
        return ""

    lines = [
        "You MUST NOT answer questions about these topics yourself.",
        'Instead, reply with something like: "I\'ll check with my colleague and get back to you shortly."',
        "(Always in the guest's language.)",
        "",
    ]
    for entry in escalation_entries:
        lines.append(f"- {entry['label']}")

    return "\n".join(lines)
```

- [ ] **Step 3: Filter KB entries in `_build_chat_messages`**

Replace lines 576-579 in `_build_chat_messages`:

```python
# OLD:
        if knowledge_entries:
            kb_text = self._format_knowledge_entries(knowledge_entries)
            if kb_text:
                system_parts.append(f"\n=== HOST KNOWLEDGE BASE ===\n{kb_text}\n===")
```

```python
# NEW:
        if knowledge_entries:
            regular_entries = [e for e in knowledge_entries if e.get('category') != 'escalation']
            escalation_entries = [e for e in knowledge_entries if e.get('category') == 'escalation']

            if regular_entries:
                kb_text = self._format_knowledge_entries(regular_entries)
                if kb_text:
                    system_parts.append(f"\n=== HOST KNOWLEDGE BASE ===\n{kb_text}\n===")

            if escalation_entries:
                restricted_text = self._format_restricted_topics(escalation_entries)
                if restricted_text:
                    system_parts.append(f"\n=== RESTRICTED TOPICS ===\n{restricted_text}\n===")
```

- [ ] **Step 4: Add escalation to knowledge.js**

In `static/js/knowledge.js`, update the three constants:

```javascript
// CATEGORY_LABELS (line 6-13) — add after faq:
    escalation: { de: 'Eskalation', en: 'Escalation' },
```

```javascript
// CATEGORY_ICONS (line 15-22) — add after faq:
    escalation: 'fa-exclamation-triangle',
```

```javascript
// CATEGORY_ORDER (line 24) — add 'escalation' at end:
const CATEGORY_ORDER = ['general', 'checkin_checkout', 'nearby', 'house_rules', 'emergency', 'faq', 'escalation'];
```

- [ ] **Step 5: Add escalation option to knowledge.html dropdown**

In `templates/chatbot/knowledge.html`, after line 82 (the faq option):

```html
                    <option value="escalation" data-i18n="knowledge.cat.escalation">Eskalation</option>
```

- [ ] **Step 6: Add i18n keys**

In `static/js/i18n.js`, add after the German `knowledge.cat.faq` key (line 359):

```javascript
        'knowledge.cat.escalation': 'Eskalation',
```

Add after the English `knowledge.cat.faq` key (line 723):

```javascript
        'knowledge.cat.escalation': 'Escalation',
```

- [ ] **Step 7: Commit**

```bash
git add models.py services/ai_service.py static/js/knowledge.js templates/chatbot/knowledge.html static/js/i18n.js
git commit -m "feat(ai): add restricted topics via KB escalation category

New 'escalation' category in Knowledge Base. Entries in this category
are formatted as restricted topics in the AI prompt — the AI will
deflect these questions to the host instead of answering."
```

---

## Task 4: Manual Verification

- [ ] **Step 1: Start the dev server**

```bash
python -m ChatBotAI.run
```

- [ ] **Step 2: Test Quality Guards**

Open a test conversation, send a message, verify the AI response has no `<think>` tags or model artifacts. Check server logs for `[AI QUALITY]` or `[AI RESPONSE]` entries.

- [ ] **Step 3: Test Consecutive Messages**

Create a test conversation with 3 consecutive guest messages. Verify the AI addresses all of them. Check logs to confirm `[1]`, `[2]`, `[3]` numbering in the prompt.

- [ ] **Step 4: Test Escalation Category**

Go to Knowledge Base, create a new entry with category "Eskalation". Verify it renders with the warning icon. Send a guest message about that topic and verify the AI deflects instead of answering.
