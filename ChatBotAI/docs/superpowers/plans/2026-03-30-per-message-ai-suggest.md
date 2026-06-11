# Per-Message AI Suggestion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightbulb icon to each guest message that generates an AI draft specifically for that message, using a slimmed-down prompt.

**Architecture:** New API endpoint receives a message ID, builds a lean prompt (history + profile + property + host instructions only), and returns a draft. Frontend adds a lightbulb button to every guest message (in template + 2 JS render paths). Draft appears in the textarea like existing KI-Vorschlag.

**Tech Stack:** Flask route, Jinja2 template, vanilla JS, CSS, Ollama via existing AIService

---

### Task 1: Backend — New API endpoint

**Files:**
- Modify: `routes.py` (insert after the existing `api_suggest_ai_response` function, ~line 1140)

- [ ] **Step 1: Add the new route**

Insert this route after the existing `api_suggest_ai_response` function (after ~line 1140):

```python
@chatbot_bp.route('/api/conversations/<int:conversation_id>/ai-suggest-for-message', methods=['POST'])
def api_suggest_for_message(conversation_id):
    """Generate an AI suggestion targeting a specific guest message"""
    conversation = Conversation.query.get_or_404(conversation_id)

    if not conversation.ai_enabled:
        return jsonify({'error': 'AI is disabled for this conversation'}), 400

    request_data = request.get_json(silent=True) or {}
    message_id = request_data.get('message_id')
    if not message_id:
        return jsonify({'error': 'message_id is required'}), 400

    # Validate message belongs to this conversation and is from a guest
    target_message = Message.query.filter_by(
        id=message_id,
        conversation_id=conversation_id,
        sender_type='guest'
    ).first()
    if not target_message:
        return jsonify({'error': 'Guest message not found in this conversation'}), 404

    ai_service = get_ai_service()
    memory_service = get_memory_service()

    if not ai_service:
        return jsonify({'error': 'AI service not initialized'}), 503

    if not ai_service.test_connection():
        return jsonify({'error': 'Cannot connect to Ollama. Is the server running?'}), 503

    try:
        tone = AISettings.get('ai_response_tone', 'friendly_professional')
        host_instructions = AISettings.get('host_instructions', '')
        max_history = int(AISettings.get('max_conversation_history', '10'))

        # Get conversation history for read-only context
        messages = conversation.messages.filter(
            db.or_(Message.approval_status.is_(None), Message.approval_status == 'approved')
        ).order_by(Message.sent_at.desc()).limit(max_history).all()
        messages.reverse()

        # Get guest profile and property info
        profile = memory_service.get_guest_profile(conversation.guest_id) if memory_service else {}
        property_info = conversation.property.to_dict() if conversation.property else None

        # Clean target message content
        target_content = target_message.content or ''

        # Generate with slimmed-down context: no KB, no reservation, no corrections,
        # no summary, no resolved topics — just history + profile + property + instructions
        ai_response = ai_service.generate_guest_response(
            guest_profile=profile,
            conversation_history=[m.to_dict() for m in messages],
            latest_message=target_content,
            property_info=property_info,
            tone=tone,
            host_instructions=host_instructions,
            conversation_subject=conversation.subject,
            max_history=max_history,
            reservation_info=None,
            knowledge_entries=None,
            conversation_summary=None,
            corrections=None,
            resolved_topics=None,
            is_closing=False,
            target_message_override=target_content,
        )

        if not ai_response:
            return jsonify({'error': 'AI response timed out. The model may be loading - try again.'}), 504

        return jsonify({
            'suggestion': ai_response,
            'target_message_id': message_id,
        })

    except MemoryError:
        logger.error("MemoryError during per-message AI suggestion")
        db.session.rollback()
        return jsonify({'error': 'Out of memory. Try a smaller model in Settings.'}), 503
    except Exception as e:
        logger.error(f"Error in per-message AI suggest: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500
```

- [ ] **Step 2: Verify the route file has no syntax errors**

Run: `python -c "import py_compile; py_compile.compile('routes.py', doraise=True)"`
Expected: No output (success)

- [ ] **Step 3: Commit**

```bash
git add routes.py
git commit -m "feat: add /ai-suggest-for-message API endpoint"
```

---

### Task 2: AI Service — Add target_message_override parameter

**Files:**
- Modify: `services/ai_service.py` — `generate_guest_response()` (~line 410) and `_build_chat_messages()` (~line 633)

- [ ] **Step 1: Add `target_message_override` parameter to `generate_guest_response()`**

In `services/ai_service.py`, find the `generate_guest_response` method signature (line ~410). Add the new parameter after `is_closing`:

```python
    def generate_guest_response(
            self,
            guest_profile: Dict[str, Any],
            conversation_history: List[Dict[str, str]],
            latest_message: str,
            property_info: Optional[Dict[str, Any]] = None,
            tone: Optional[str] = None,
            host_instructions: Optional[str] = None,
            conversation_subject: Optional[str] = None,
            max_history: int = 10,
            reservation_info: Optional[Dict[str, Any]] = None,
            knowledge_entries: Optional[List[Dict[str, Any]]] = None,
            conversation_summary: Optional[str] = None,
            corrections: Optional[List[Dict[str, Any]]] = None,
            resolved_topics: Optional[List[str]] = None,
            is_closing: bool = False,
            target_message_override: Optional[str] = None
    ) -> Optional[str]:
```

Then find where this method calls `self._build_chat_messages(...)` and pass through the new parameter. Add `target_message_override=target_message_override` to that call.

- [ ] **Step 2: Add `target_message_override` parameter to `_build_chat_messages()`**

In `_build_chat_messages` signature (line ~633), add the new parameter after `is_closing`:

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
            is_closing: bool = False,
            target_message_override: Optional[str] = None
    ) -> List[Dict[str, str]]:
```

- [ ] **Step 3: Modify the YOUR TASK section to use the override**

In `_build_chat_messages`, find the YOUR TASK section (line ~777). Replace the task instruction block:

```python
        # Task instruction at the END — models pay most attention to beginning + end
        system_parts.append("")
        if target_message_override:
            clean_target = self._strip_html(target_message_override)
            clean_target = self._strip_email_quotes(clean_target)
            if not clean_target.strip():
                clean_target = target_message_override.strip()
            system_parts.extend([
                "=== YOUR TASK ===",
                "The guest sent the following message. Write a reply specifically to THIS message:",
                f'"{clean_target[:300]}"',
                "Focus ONLY on answering this message. Ignore everything else in the conversation.",
                "===",
            ])
        elif unanswered_count >= 2:
            system_parts.extend([
                "=== YOUR TASK ===",
                f"The guest has sent {unanswered_count} unanswered messages below.",
                "Address ALL of them in a single reply.",
                "===",
            ])
        else:
            system_parts.extend([
                "=== YOUR TASK ===",
                f'The guest\'s NEW message is: "{clean_latest[:300]}"',
                "Write a reply that answers THIS message. Ignore everything else.",
                "===",
            ])
```

- [ ] **Step 4: Verify no syntax errors**

Run: `python -c "import py_compile; py_compile.compile('services/ai_service.py', doraise=True)"`
Expected: No output (success)

- [ ] **Step 5: Commit**

```bash
git add services/ai_service.py
git commit -m "feat: add target_message_override to AI prompt builder"
```

---

### Task 3: Frontend — Template lightbulb icon

**Files:**
- Modify: `templates/chatbot/conversation.html` (~line 134, inside the message header)

- [ ] **Step 1: Add lightbulb button to guest messages in the Jinja2 template**

In `templates/chatbot/conversation.html`, find the message header block (line ~134). Replace the existing `<div class="message-header">` block:

Old (lines 134-141):
```html
                <div class="message-header">
                    <span class="sender-name">
                        {% if message.sender_type == 'guest' %}{{ guest.name or 'Gast' }}
                        {% elif message.sender_type == 'owner' %}{{ message.sender_user.display_name if message.sender_user else 'Team' }}
                        {% else %}<span data-i18n="conversation.ai">KI-Assistent</span>{% endif %}
                    </span>
                    <span class="message-time">{{ message.sent_at.strftime('%d.%m.%Y %H:%M') if message.sent_at else '' }}</span>
                </div>
```

New:
```html
                <div class="message-header">
                    <span class="sender-name">
                        {% if message.sender_type == 'guest' %}{{ guest.name or 'Gast' }}
                        {% elif message.sender_type == 'owner' %}{{ message.sender_user.display_name if message.sender_user else 'Team' }}
                        {% else %}<span data-i18n="conversation.ai">KI-Assistent</span>{% endif %}
                    </span>
                    <span class="message-header-right">
                        {% if message.sender_type == 'guest' %}
                        <button class="btn-suggest-for-message" onclick="suggestForMessage({{ message.id }})"
                            data-i18n-title="conversation.ai.suggestForMessage"
                            title="KI-Antwort für diese Nachricht"
                            {% if not conversation.ai_enabled %}disabled{% endif %}>
                            <i class="fas fa-lightbulb"></i>
                        </button>
                        {% endif %}
                        <span class="message-time">{{ message.sent_at.strftime('%d.%m.%Y %H:%M') if message.sent_at else '' }}</span>
                    </span>
                </div>
```

- [ ] **Step 2: Commit**

```bash
git add templates/chatbot/conversation.html
git commit -m "feat: add per-message AI suggest lightbulb to guest messages"
```

---

### Task 4: Frontend — JavaScript `suggestForMessage()` function

**Files:**
- Modify: `static/js/conversation.js` (insert new function after `suggestAIResponse`, ~line 605)

- [ ] **Step 1: Add the `suggestForMessage` function**

Insert after the `suggestAIResponse` function (after line ~605):

```javascript
function suggestForMessage(messageId) {
    pendingCorrectionOriginal = null;
    const input = document.getElementById('messageInput');
    const suggestBtn = document.getElementById('suggestAiBtn');
    const generateBtn = document.getElementById('generateAiBtn');

    // Find and animate the clicked lightbulb button
    const msgDiv = document.querySelector(`.message[data-message-id="${messageId}"]`);
    const perMsgBtn = msgDiv ? msgDiv.querySelector('.btn-suggest-for-message') : null;

    // Disable all AI buttons during generation
    suggestBtn.disabled = true;
    generateBtn.disabled = true;
    if (perMsgBtn) {
        perMsgBtn.disabled = true;
        perMsgBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }

    if (activeAiController) activeAiController.abort();
    activeAiController = new AbortController();
    const signal = activeAiController.signal;

    fetch(`/chatbot/api/conversations/${conversationId}/ai-suggest-for-message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: messageId }),
        signal: signal
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showAiError(data.error);
        } else {
            input.value = data.suggestion;
            localStorage.setItem(draftKey, data.suggestion);
            input.focus();
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 200) + 'px';
            // Scroll to the input area so the host sees the draft
            input.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    })
    .catch(err => {
        if (err.name === 'AbortError') return;
        console.error('Failed to generate per-message AI suggestion:', err);
        showAiError(i18n.t('conversation.ai.error') || 'AI not reachable. Is Ollama running?');
    })
    .finally(() => {
        activeAiController = null;
        suggestBtn.disabled = !aiEnabled;
        generateBtn.disabled = !aiEnabled;
        if (perMsgBtn) {
            perMsgBtn.disabled = !aiEnabled;
            perMsgBtn.innerHTML = '<i class="fas fa-lightbulb"></i>';
        }
    });
}
```

- [ ] **Step 2: Add the lightbulb to the "load older messages" render path**

In the `loadOlderMessages` function (~line 99), find the `msgDiv.innerHTML` template (line ~116). Replace:

```javascript
                msgDiv.innerHTML = `
                    <div class="message-avatar"><i class="fas ${icon}"></i></div>
                    <div class="message-content">
                        <div class="message-header">
                            <span class="sender-name">${name}</span>
                            <span class="message-time">${time}</span>
                        </div>
                        <div class="message-text">${escapeHtml(msg.content || '')}</div>
                    </div>
                `;
```

With:

```javascript
                const suggestBtn = msg.sender_type === 'guest'
                    ? `<button class="btn-suggest-for-message" onclick="suggestForMessage(${msg.id})"
                        data-i18n-title="conversation.ai.suggestForMessage"
                        title="${i18n.t('conversation.ai.suggestForMessage')}"
                        ${!aiEnabled ? 'disabled' : ''}>
                        <i class="fas fa-lightbulb"></i>
                       </button>`
                    : '';
                msgDiv.innerHTML = `
                    <div class="message-avatar"><i class="fas ${icon}"></i></div>
                    <div class="message-content">
                        <div class="message-header">
                            <span class="sender-name">${name}</span>
                            <span class="message-header-right">
                                ${suggestBtn}
                                <span class="message-time">${time}</span>
                            </span>
                        </div>
                        <div class="message-text">${escapeHtml(msg.content || '')}</div>
                    </div>
                `;
```

- [ ] **Step 3: Add the lightbulb to the `addMessageToUI` render path**

In the `addMessageToUI` function (~line 797), find the `messageDiv.innerHTML` template (line ~822). Replace:

```javascript
    messageDiv.innerHTML = `
        <div class="message-avatar"><i class="fas ${icon}"></i></div>
        <div class="message-content">
            <div class="message-header">
                <span class="sender-name">${name}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-text">${escapeHtml(message.content || '')}</div>
        </div>
    `;
```

With:

```javascript
    const perMsgSuggestBtn = actualSenderType === 'guest' && message.id
        ? `<button class="btn-suggest-for-message" onclick="suggestForMessage(${message.id})"
            data-i18n-title="conversation.ai.suggestForMessage"
            title="${i18n.t('conversation.ai.suggestForMessage')}"
            ${!aiEnabled ? 'disabled' : ''}>
            <i class="fas fa-lightbulb"></i>
           </button>`
        : '';
    messageDiv.innerHTML = `
        <div class="message-avatar"><i class="fas ${icon}"></i></div>
        <div class="message-content">
            <div class="message-header">
                <span class="sender-name">${name}</span>
                <span class="message-header-right">
                    ${perMsgSuggestBtn}
                    <span class="message-time">${time}</span>
                </span>
            </div>
            <div class="message-text">${escapeHtml(message.content || '')}</div>
        </div>
    `;
```

- [ ] **Step 4: Commit**

```bash
git add static/js/conversation.js
git commit -m "feat: add suggestForMessage() and lightbulb in all JS render paths"
```

---

### Task 5: CSS — Style the lightbulb button

**Files:**
- Modify: `static/css/style.css` (insert after the `.message-time` styles, ~line 1075)

- [ ] **Step 1: Add styles for the lightbulb button and header-right wrapper**

Insert after the `.message.owner .message-time, .message.ai .message-time` block (~line 1075):

```css
.message-header-right {
    display: flex;
    align-items: center;
    gap: 6px;
}

.btn-suggest-for-message {
    background: none;
    border: none;
    color: var(--text-light);
    cursor: pointer;
    padding: 2px 4px;
    font-size: 0.75rem;
    border-radius: 4px;
    opacity: 0.4;
    transition: opacity 0.2s, color 0.2s;
}

.btn-suggest-for-message:hover {
    opacity: 1;
    color: var(--warning-color, #f59e0b);
}

.btn-suggest-for-message:disabled {
    cursor: not-allowed;
    opacity: 0.2;
}

.btn-suggest-for-message .fa-spinner {
    opacity: 1;
    color: var(--warning-color, #f59e0b);
}
```

- [ ] **Step 2: Add mobile styles**

Find the mobile breakpoint section for `.message-time` (~line 2118). After that block, add:

```css
    .btn-suggest-for-message {
        font-size: 0.85rem;
        padding: 4px 6px;
        opacity: 0.6;
    }
```

This makes the button slightly larger and more visible on mobile (no hover state on touch devices).

- [ ] **Step 3: Bump CSS cache version**

In `templates/chatbot/base.html`, find the stylesheet link for `style.css` and bump the version number from v16 to v17.

- [ ] **Step 4: Commit**

```bash
git add static/css/style.css templates/chatbot/base.html
git commit -m "feat: style per-message AI suggest lightbulb button"
```

---

### Task 6: i18n — Add translation key

**Files:**
- Modify: `static/js/i18n.js`

- [ ] **Step 1: Add the German translation**

In `static/js/i18n.js`, find the German `conversation.ai.suggest` key (~line 50). Add after it:

```javascript
        'conversation.ai.suggestForMessage': 'KI-Antwort für diese Nachricht',
```

- [ ] **Step 2: Add the English translation**

Find the English `conversation.ai.suggest` key (~line 463). Add after it:

```javascript
        'conversation.ai.suggestForMessage': 'AI suggestion for this message',
```

- [ ] **Step 3: Bump i18n cache version**

In `templates/chatbot/base.html`, find the script tag for `i18n.js` and bump the version number from v16 to v17.

- [ ] **Step 4: Bump conversation.js cache version**

In `templates/chatbot/conversation.html`, find the script tag for `conversation.js` and bump the version from v13 to v14.

- [ ] **Step 5: Commit**

```bash
git add static/js/i18n.js templates/chatbot/base.html templates/chatbot/conversation.html
git commit -m "feat: add i18n keys and bump cache versions for per-message suggest"
```

---

### Task 7: Manual testing

- [ ] **Step 1: Start the dev server**

Run: `python -m ChatBotAI.run`

- [ ] **Step 2: Open a conversation with guest messages**

Navigate to `/chatbot/` and open any conversation that has guest messages.

- [ ] **Step 3: Verify lightbulb icons appear on all guest messages**

Each guest message should have a small lightbulb icon in the header, next to the timestamp. Owner and AI messages should NOT have the icon.

- [ ] **Step 4: Click a lightbulb icon and verify the draft appears**

Click the lightbulb on any guest message. The button should show a spinner, then the AI draft should appear in the textarea at the bottom. The draft should be relevant to the specific message clicked.

- [ ] **Step 5: Verify the existing KI-Vorschlag button still works**

Click the KI-Vorschlag button in the text bar. It should work exactly as before.

- [ ] **Step 6: Verify disabled state when AI is off**

Toggle AI off. All lightbulb icons should become disabled (grayed out, not clickable). Toggle AI back on — they should re-enable.

- [ ] **Step 7: Test on mobile viewport**

Resize browser to mobile width (~375px). Verify lightbulb icons are visible and tappable.
