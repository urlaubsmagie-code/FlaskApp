# History-in-System-Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix AI responding to old messages by moving conversation history into the system prompt, leaving only the latest guest message as the single `user` turn.

**Architecture:** Rewrite `_build_chat_messages()` in `ai_service.py`. History becomes a formatted log inside the system prompt. The Ollama API always receives exactly 2 messages: 1 system + 1 user. All callers are unchanged.

**Tech Stack:** Python/Flask, Ollama chat API (qwen3:8b)

**Spec:** `docs/superpowers/specs/2026-03-27-history-in-system-prompt-design.md`

---

### Task 1: Add `_format_conversation_log()` helper method

**Files:**
- Modify: `services/ai_service.py` — add new method after `_count_trailing_guest_messages()` (after line 1018)

This helper takes raw conversation history and returns a compact text log for the system prompt.

- [ ] **Step 1: Add the helper method**

Add this method to the `AIService` class, after `_count_trailing_guest_messages()` (line 1018):

```python
def _format_conversation_log(
        self,
        conversation_history: List[Dict[str, str]],
        max_history: int = 10
) -> str:
    """Format conversation history as a compact text log for the system prompt.

    Returns a string like:
        Guest: What's the WiFi password?
        Host: The WiFi password is XYZ.

    Deduplicates by platform_message_id and content.
    Strips HTML, email quotes, and empty messages.
    Caps at max_history messages.
    """
    sender_labels = {'guest': 'Guest', 'owner': 'Host', 'ai': 'Host'}

    seen_platform_ids = set()
    seen_content = set()
    lines = []

    for msg in conversation_history:
        # Skip duplicates by platform_message_id
        pmid = msg.get('platform_message_id')
        if pmid:
            if pmid in seen_platform_ids:
                continue
            seen_platform_ids.add(pmid)

        sender_type = msg.get('sender_type', 'guest')
        content = msg.get('content', '').strip()
        if not content:
            continue

        # Clean content
        content = self._strip_html(content)
        stripped = self._strip_email_quotes(content)
        content = stripped if stripped.strip() else content

        if not content.strip():
            continue

        # Skip duplicate content
        content_key = (sender_type, content.strip())
        if content_key in seen_content:
            continue
        seen_content.add(content_key)

        label = sender_labels.get(sender_type, 'Guest')
        # Truncate very long messages to keep the log scannable
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"{label}: {content.strip()}")

    # Keep last N messages
    lines = lines[-max_history:]

    return "\n".join(lines)
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ChatBotAI.services.ai_service; print('OK')"`

Expected: `OK` (no import errors)

- [ ] **Step 3: Commit**

```bash
git add services/ai_service.py
git commit -m "feat(ai): add _format_conversation_log() helper for history-in-system-prompt"
```

---

### Task 2: Rewrite `_build_chat_messages()` — system prompt with history log

**Files:**
- Modify: `services/ai_service.py:633-927` — replace entire `_build_chat_messages()` method

This is the core change. The method keeps its exact signature. The closing/gratitude shortcut stays unchanged. Everything else is restructured: history goes into the system prompt, and only the latest message becomes the `user` turn.

- [ ] **Step 1: Replace `_build_chat_messages()` with the new implementation**

Replace lines 633-927 (the entire `_build_chat_messages` method) with:

```python
def _build_chat_messages(
        self,
        guest_profile: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        latest_message: str,
        property_info: Optional[Dict[str, Any]],
        tone: Optional[str] = None,
        host_instructions: Optional[str] = None,
        conversation_subject: Optional[str] = None,
        max_history: int = 10,
        reservation_info: Optional[Dict[str, Any]] = None,
        knowledge_entries: Optional[List[Dict[str, Any]]] = None,
        conversation_summary: Optional[str] = None,
        corrections: Optional[List[Dict[str, Any]]] = None,
        resolved_topics: Optional[List[str]] = None,
        is_closing: bool = False
) -> List[Dict[str, str]]:
    """Build chat messages for the Ollama chat API.

    Architecture: conversation history goes into the system prompt as a
    read-only log.  The ONLY user turn is the guest's latest message.
    This prevents small models from responding to old messages.

    Returns:
        List of exactly 2 dicts: [system, user]
    """
    messages = []

    # Shortcut: for closing/gratitude messages, use a minimal prompt
    if is_closing:
        guest_name = guest_profile.get('name', 'the guest') if guest_profile else 'the guest'
        closing_system = (
            f"You are a vacation rental host. The guest ({guest_name}) is thanking you "
            "for your help. Reply briefly and warmly in the SAME LANGUAGE as the guest's message. "
            "Keep it to 1-2 sentences. Do NOT bring up any other topics."
        )
        messages.append({'role': 'system', 'content': closing_system})
        clean_latest = self._strip_html(latest_message)
        clean_latest = self._strip_email_quotes(clean_latest)
        messages.append({'role': 'user', 'content': clean_latest or latest_message.strip()})
        return messages

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
        "You are a vacation rental host writing a reply to a guest.",
        f"{tone_instruction}",
        f"Current date/time: {now.strftime('%A, %d %B %Y, %H:%M')} UTC.",
        "",
        "Rules:",
        "- Reply ONLY in the SAME LANGUAGE as the guest's message below.",
        "- Write ONLY the reply text. No subject lines, no 'Subject:', no signatures.",
        "- NEVER re-ask questions the guest already answered.",
        "- NEVER repeat information you already provided.",
        "- If you don't know specific details (WiFi password, door code, prices), say you'll check — NEVER invent details.",
        "- The CONVERSATION LOG below is for context only — do NOT re-answer old topics.",
    ]

    if guest_language:
        system_parts.append(f"- The guest's preferred language is: {guest_language}.")

    # Task instruction
    system_parts.append("")
    if unanswered_count >= 2:
        system_parts.extend([
            f"=== YOUR TASK ===",
            f"The guest has sent {unanswered_count} unanswered messages (numbered [1]-[{unanswered_count}] below).",
            "Address ALL of them in a single reply.",
            "===",
        ])
    else:
        system_parts.extend([
            "=== YOUR TASK ===",
            "Reply to the guest's new message below.",
            "===",
        ])

    # Context sections (same as before — conditional)
    if guest_profile:
        profile_text = self._format_guest_profile(guest_profile)
        if profile_text:
            system_parts.append(f"\n=== GUEST PROFILE ===\n{profile_text}\n=== Do NOT ask for info already listed above. ===")

    if property_info:
        property_text = self._format_property_info(property_info)
        if property_text:
            system_parts.append(f"\nProperty details:\n{property_text}")

    if conversation_subject:
        system_parts.append(f"\nConversation topic: {conversation_subject}")

    if reservation_info:
        res_text = self._format_reservation_info(reservation_info)
        if res_text:
            system_parts.append(f"\n=== RESERVATION ===\n{res_text}\n===")

    if knowledge_entries:
        regular_entries = [e for e in knowledge_entries if e.get('category') != 'escalation']
        escalation_entries = [e for e in knowledge_entries if e.get('category') == 'escalation']

        if regular_entries:
            kb_text = self._format_knowledge_entries(regular_entries)
            if kb_text:
                system_parts.append(
                    f"\n=== HOST KNOWLEDGE BASE (use ONLY facts relevant to the guest's current question) ===\n"
                    f"{kb_text}\n==="
                )

        if escalation_entries:
            restricted_text = self._format_restricted_topics(escalation_entries)
            if restricted_text:
                system_parts.append(f"\n=== RESTRICTED TOPICS ===\n{restricted_text}\n===")

    if host_instructions and host_instructions.strip():
        system_parts.append(f"\n=== HOST INSTRUCTIONS ===\n{host_instructions.strip()}\n===")

    if resolved_topics:
        topics_text = "\n".join(f"- {topic}" for topic in resolved_topics[:8])
        system_parts.append(
            f"\n=== ALREADY RESOLVED (do NOT address these topics again) ===\n"
            f"{topics_text}\n==="
        )

    if conversation_summary:
        system_parts.append(
            f"\n=== CONVERSATION SUMMARY (older messages, for background only) ===\n"
            f"{conversation_summary}\n==="
        )

    if corrections:
        corrections_text = self._format_corrections(corrections)
        if corrections_text:
            system_parts.append(f"\n=== PAST CORRECTIONS (you made these mistakes before — don't repeat them) ===\n{corrections_text}\n===")

    # Conversation log — the key change: history is now IN the system prompt
    conversation_log = self._format_conversation_log(conversation_history, max_history)
    if conversation_log:
        system_parts.append(
            f"\n=== CONVERSATION LOG (read-only context — do NOT respond to these messages) ===\n"
            f"{conversation_log}\n==="
        )

    messages.append({'role': 'system', 'content': "\n".join(system_parts)})

    # --- Single user turn: only the latest guest message ---
    if unanswered_count >= 2:
        # Build numbered multi-message user turn from trailing guest messages
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
        # Number them [1], [2], ...
        numbered = [f"[{i+1}] {text}" for i, text in enumerate(trailing_messages)]
        messages.append({'role': 'user', 'content': "\n".join(numbered)})
    else:
        messages.append({'role': 'user', 'content': clean_latest})

    return messages
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ChatBotAI.services.ai_service; print('OK')"`

Expected: `OK` (no import errors)

- [ ] **Step 3: Commit**

```bash
git add services/ai_service.py
git commit -m "feat(ai): rewrite _build_chat_messages() — history in system prompt

Move conversation history from native chat turns into the system prompt
as a read-only log. The only user turn is now the latest guest message.
This prevents the 8B model from responding to old/already-answered
messages instead of the newest one."
```

---

### Task 3: Manual testing with real conversations

**Files:** None (testing only)

- [ ] **Step 1: Restart the dev server**

Stop and restart the Flask development server so the new code is loaded.

- [ ] **Step 2: Test single-message scenario (the main fix)**

1. Open a Smoobu conversation that has multiple back-and-forth messages
2. Click "Suggest" (KI Vorschlag button)
3. Verify the AI responds to the **latest** guest message, not an old one
4. Repeat with 2-3 different conversations

Expected: AI response addresses the most recent guest question.

- [ ] **Step 3: Test multi-message scenario**

1. Find or create a conversation where the guest sent 2+ messages in a row without a host reply
2. Click "Suggest"
3. Verify the AI addresses ALL unanswered guest messages

Expected: AI response covers all pending questions.

- [ ] **Step 4: Test closing/gratitude message**

1. Find a conversation where the last guest message is "Danke" or "Thanks"
2. Click "Suggest"
3. Verify the AI gives a brief, warm closing reply

Expected: Short 1-2 sentence reply, no old topics brought up.

- [ ] **Step 5: Check logs for correct prompt structure**

Check the server console logs for `[AI msg]` debug entries. Should show exactly 2 messages:
- `[AI msg 0] system: You are a vacation rental host...`
- `[AI msg 1] user: <the latest guest message>`

NOT 4+ messages with interleaved user/assistant turns like before.

- [ ] **Step 6: Test auto-respond flow**

1. Enable auto-respond on a test conversation
2. Send a test message (or use test route)
3. Verify the auto-generated response addresses the correct message

---

### Task 4: Clean up dead code (optional, after testing confirms fix)

**Files:**
- Modify: `services/ai_service.py` — remove unused code

After confirming the fix works, clean up methods/logic that are no longer called.

- [ ] **Step 1: Verify `_format_relative_time` is no longer used**

Search for any remaining calls to `_format_relative_time` outside of the old `_build_chat_messages`. If it's only used in the deleted code, it's dead code.

Note: Keep `_count_trailing_guest_messages()` — it's still used in the new implementation.
Note: Keep `_strip_html()`, `_strip_email_quotes()` — still used in the new implementation and in `_format_conversation_log()`.

- [ ] **Step 2: Remove `_format_relative_time` if unused**

Delete the `_format_relative_time` static method (lines 945-973) if no other code references it.

- [ ] **Step 3: Commit cleanup**

```bash
git add services/ai_service.py
git commit -m "chore(ai): remove dead code after history-in-system-prompt rewrite"
```
