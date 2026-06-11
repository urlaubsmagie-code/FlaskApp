# Compact Prompt Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the autonomous AI prompt from ~1,500-2,500 tokens to ~400-600 tokens so qwen3:8b can focus on the latest guest message.

**Architecture:** Add a compact prompt path in `_build_chat_messages()` that is used for KI-Vorschlag and KI-Antwort (when `target_message_override` is NOT set). The per-message suggest (lightbulb) path remains unchanged. A new `_build_compact_prompt()` method constructs the slim system prompt, and a new `_format_reservation_compact()` helper compresses reservation info to one line.

**Tech Stack:** Python, Flask, Ollama API (no new dependencies)

---

### Task 1: Add `_format_reservation_compact()` helper

**Files:**
- Modify: `services/ai_service.py` (add method after `_format_reservation_info` at line ~1171)

- [ ] **Step 1: Add the compact reservation formatter**

Add this method to the `AIService` class, right after `_format_reservation_info()` (after line 1171):

```python
def _format_reservation_compact(self, reservation_info: Dict[str, Any]) -> str:
    """Format reservation as a single compact line for the slim prompt."""
    parts = []
    arrival = reservation_info.get('arrival') or reservation_info.get('check_in')
    departure = reservation_info.get('departure') or reservation_info.get('check_out')
    if arrival and departure:
        parts.append(f"{arrival} to {departure}")
    elif arrival:
        parts.append(f"Check-in: {arrival}")

    adults = reservation_info.get('adults')
    children = reservation_info.get('children')
    if adults and children:
        parts.append(f"{adults} adults + {children} children")
    elif adults:
        parts.append(f"{adults} guests")

    apt = reservation_info.get('apartment', {})
    if apt and apt.get('name'):
        parts.append(f"Property: {apt['name']}")

    return "Reservation: " + ", ".join(parts) if parts else ""
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "from ChatBotAI.app import create_app; print('OK')"` from the FlaskApp directory.
Expected: `OK` (no import errors)

- [ ] **Step 3: Commit**

```bash
git add services/ai_service.py
git commit -m "feat(ai): add compact reservation formatter for slim prompt"
```

---

### Task 2: Add `_build_compact_prompt()` method

**Files:**
- Modify: `services/ai_service.py` (add method before `_build_chat_messages` at line ~635)

- [ ] **Step 1: Add the compact prompt builder**

Add this method to the `AIService` class, right before `_build_chat_messages()` (before line 635):

```python
def _build_compact_prompt(
        self,
        guest_profile: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        clean_latest: str,
        unanswered_count: int,
        tone: Optional[str] = None,
        host_instructions: Optional[str] = None,
        reservation_info: Optional[Dict[str, Any]] = None,
        knowledge_entries: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build a compact system prompt (~400-600 tokens) for KI-Vorschlag / KI-Antwort.

    Keeps only what the 8B model needs to answer the latest guest message:
    role, rules, guest name, reservation one-liner, host instructions,
    top KB entries, short conversation log, and the task instruction.

    Excludes: full guest profile, property details, conversation summary,
    resolved topics, corrections, escalation entries.
    """
    now = datetime.utcnow()
    tone_instruction = self.TONE_INSTRUCTIONS.get(tone, self.TONE_INSTRUCTIONS['friendly_professional'])

    # 1. Role + rules + tone (compact)
    parts = [
        "You are a vacation rental host replying to a guest.",
        tone_instruction,
        f"Date: {now.strftime('%d %b %Y')}.",
        "Rules: Reply in the guest's language. Never invent details — say you'll check. Don't re-ask answered questions.",
    ]

    # 2. Guest name + language
    guest_name = guest_profile.get('name', 'the guest') if guest_profile else 'the guest'
    guest_language = guest_profile.get('language') if guest_profile else None
    if guest_language:
        parts.append(f"Guest: {guest_name} (speaks {guest_language})")
    else:
        parts.append(f"Guest: {guest_name}")

    # 3. Reservation one-liner
    if reservation_info:
        res_compact = self._format_reservation_compact(reservation_info)
        if res_compact:
            parts.append(res_compact)

    # 4. Host instructions
    if host_instructions and host_instructions.strip():
        parts.append(f"Host instructions: {host_instructions.strip()}")

    # 5. KB entries (top 3 only, no escalation)
    if knowledge_entries:
        regular = [e for e in knowledge_entries if e.get('category') != 'escalation'][:3]
        if regular:
            kb_lines = []
            for e in regular:
                label = e.get('label', '')
                value = e.get('value', '')
                kb_lines.append(f"- {label}: {value[:80]}")
            parts.append("Info:\n" + "\n".join(kb_lines))

    # 6. Conversation log (last 4 messages)
    conversation_log = self._format_conversation_log(conversation_history, max_history=4)
    if conversation_log:
        parts.append(f"Recent messages:\n{conversation_log}")

    # 7. YOUR TASK (at the end for model attention)
    parts.append("")
    if unanswered_count >= 2:
        parts.append(
            f"TASK: The guest sent {unanswered_count} unanswered messages. "
            "Address ALL of them in one reply."
        )
    else:
        parts.append(
            f'TASK: The guest\'s new message is: "{clean_latest[:300]}"\n'
            "Reply to THIS message only."
        )

    return "\n".join(parts)
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "from ChatBotAI.app import create_app; print('OK')"` from the FlaskApp directory.
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add services/ai_service.py
git commit -m "feat(ai): add compact prompt builder for autonomous AI modes"
```

---

### Task 3: Wire compact prompt into `_build_chat_messages()`

**Files:**
- Modify: `services/ai_service.py:635-842` (`_build_chat_messages` method)

- [ ] **Step 1: Add compact prompt path after the closing shortcut**

In `_build_chat_messages()`, replace the current code block from the `# Get guest's preferred language` comment (line 678) through the system prompt assembly (line 809) with a branching structure. The full replacement:

Find this block (lines 678-809):
```python
        # Get guest's preferred language if stored
        guest_language = guest_profile.get('language', None) if guest_profile else None

        # Resolve tone instruction
        tone_instruction = self.TONE_INSTRUCTIONS.get(tone, self.TONE_INSTRUCTIONS['friendly_professional'])

        # Clean latest message
        clean_latest = self._strip_html(latest_message)
        clean_latest = self._strip_email_quotes(clean_latest)
        if not clean_latest.strip():
            clean_latest = latest_message.strip()

        # Count consecutive trailing guest messages for multi-message handling
        unanswered_count = min(
            self._count_trailing_guest_messages(conversation_history),
            max_history
        )

        # --- Build system prompt ---
        now = datetime.utcnow()
        system_parts = [
```

Replace with:
```python
        # Clean latest message
        clean_latest = self._strip_html(latest_message)
        clean_latest = self._strip_email_quotes(clean_latest)
        if not clean_latest.strip():
            clean_latest = latest_message.strip()

        # Count consecutive trailing guest messages for multi-message handling
        unanswered_count = min(
            self._count_trailing_guest_messages(conversation_history),
            max_history
        )

        # --- Prompt mode selection ---
        # Per-message suggest (lightbulb): uses the full prompt with target_message_override
        # KI-Vorschlag / KI-Antwort: uses the compact prompt for 8B model focus
        if not target_message_override:
            system_content = self._build_compact_prompt(
                guest_profile=guest_profile,
                conversation_history=conversation_history,
                clean_latest=clean_latest,
                unanswered_count=unanswered_count,
                tone=tone,
                host_instructions=host_instructions,
                reservation_info=reservation_info,
                knowledge_entries=knowledge_entries,
            )
            messages.append({'role': 'system', 'content': system_content})

            # User turn: latest guest message(s)
            if unanswered_count >= 2:
                trailing_messages = []
                for msg in reversed(conversation_history):
                    if msg.get('sender_type') == 'guest':
                        content = self._strip_html(msg.get('content', ''))
                        content = self._strip_email_quotes(content)
                        if content.strip():
                            trailing_messages.append(content.strip())
                    else:
                        break
                trailing_messages.reverse()

                if len(trailing_messages) >= 2:
                    numbered = [f"[{i+1}] {text}" for i, text in enumerate(trailing_messages)]
                    messages.append({'role': 'user', 'content': "\n".join(numbered)})
                else:
                    messages.append({'role': 'user', 'content': trailing_messages[0] if trailing_messages else clean_latest})
            else:
                messages.append({'role': 'user', 'content': clean_latest})

            return messages

        # --- Per-message suggest: full prompt path (unchanged) ---
        # Get guest's preferred language if stored
        guest_language = guest_profile.get('language', None) if guest_profile else None

        # Resolve tone instruction
        tone_instruction = self.TONE_INSTRUCTIONS.get(tone, self.TONE_INSTRUCTIONS['friendly_professional'])

        # --- Build system prompt ---
        now = datetime.utcnow()
        system_parts = [
```

This inserts the compact prompt path as an early return. If `target_message_override` is NOT set, the compact prompt is used and the method returns. If it IS set (lightbulb), execution falls through to the existing full prompt code.

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "from ChatBotAI.app import create_app; print('OK')"` from the FlaskApp directory.
Expected: `OK`

- [ ] **Step 3: Verify the per-message suggest path is unchanged**

Run a quick sanity check that `target_message_override` still reaches the full prompt:

```python
python -c "
from ChatBotAI.app import create_app
app = create_app()
with app.app_context():
    from ChatBotAI.services.ai_service import get_ai_service
    ai = get_ai_service()
    msgs = ai._build_chat_messages(
        guest_profile={'name': 'Test Guest'},
        conversation_history=[],
        latest_message='Hello',
        property_info=None,
        target_message_override='Where is the parking?'
    )
    system = msgs[0]['content']
    assert 'YOUR TASK' in system, 'Full prompt should have YOUR TASK section'
    assert 'parking' in system.lower(), 'Full prompt should contain the target message'
    print('Per-message suggest path: OK')

    msgs2 = ai._build_chat_messages(
        guest_profile={'name': 'Test Guest'},
        conversation_history=[],
        latest_message='What time is check-in?',
        property_info=None,
    )
    system2 = msgs2[0]['content']
    assert 'TASK:' in system2, 'Compact prompt should have TASK: section'
    assert 'GUEST PROFILE' not in system2, 'Compact prompt should NOT have full guest profile'
    print('Compact prompt path: OK')
    print()
    print('--- Compact prompt preview ---')
    print(system2)
"
```

Expected: Both checks pass, compact prompt is visibly shorter.

- [ ] **Step 4: Commit**

```bash
git add services/ai_service.py
git commit -m "feat(ai): use compact prompt for KI-Vorschlag and KI-Antwort

Autonomous AI modes now use a ~400-600 token prompt instead of
~1,500-2,500 tokens. Per-message suggest (lightbulb) is unchanged."
```

---

### Task 4: Manual testing with real conversation

**Files:** None (testing only)

- [ ] **Step 1: Test KI-Vorschlag with a real conversation**

Open the app, go to a conversation with recent guest messages. Click the KI-Vorschlag button in the textbar. Verify:
- The AI responds to the LATEST guest message (not an old one)
- The response is in the correct language
- The response doesn't invent details

- [ ] **Step 2: Test per-message suggest (lightbulb) still works**

Click a lightbulb button on a specific guest message. Verify:
- The AI responds specifically to THAT message
- Behavior is unchanged from before

- [ ] **Step 3: Compare prompt sizes**

Add a temporary log line to verify token reduction. In `_build_chat_messages()`, after each `messages.append({'role': 'system', ...})` line, add:
```python
import logging
logging.getLogger(__name__).info(f"[PROMPT SIZE] system prompt: {len(system_content)} chars")
```

Check the logs for both compact and full prompt to confirm the reduction.

- [ ] **Step 4: Remove temporary logging and commit**

```bash
git add services/ai_service.py
git commit -m "test: verify compact prompt produces correct AI responses"
```
