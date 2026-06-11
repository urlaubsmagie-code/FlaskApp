# Chat Playtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Chat Playtest tab to the Debug dashboard where admins can simulate guest/host conversations through the real message pipeline without delivering messages to actual guests, with a live event log showing each pipeline step.

**Architecture:** New `playtest` platform type flows through the existing `MessageRouter` pipeline unchanged — platform delivery is naturally skipped because send code only fires for `smoobu`/`email`. A lightweight in-memory event buffer (`playtest_events.py`) captures pipeline steps, polled by the frontend. Five new API endpoints in `routes.py` drive the playtest. All UI lives in the existing `debug.html` as a 4th tab.

**Tech Stack:** Flask (Python), vanilla JS, existing SQLAlchemy models, existing MessageRouter

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `services/playtest_events.py` | **CREATE** | In-memory event buffer with `playtest_log()` and `get_events()` |
| `services/message_router.py` | MODIFY | Add ~10 `playtest_log()` calls gated on `platform == 'playtest'` |
| `routes.py` | MODIFY | Add 5 playtest API endpoints + filter playtest from inbox/unread queries |
| `templates/chatbot/debug.html` | MODIFY | Add Chat Playtest tab with split layout (chat + event log) |

---

### Task 1: Create the playtest event buffer

**Files:**
- Create: `services/playtest_events.py`

- [ ] **Step 1: Create `services/playtest_events.py`**

```python
"""
In-memory event buffer for Chat Playtest.
Captures pipeline events during playtest conversations for the live event log.
"""

import time
from collections import deque
from threading import Lock
from typing import Dict, List, Tuple, Any

# Per-conversation event buffers: { conversation_id: deque of events }
_buffers: Dict[int, deque] = {}
_lock = Lock()
_MAX_EVENTS = 200


def playtest_log(conversation_id: int, event_type: str, detail: str):
    """Append an event to the playtest buffer for a conversation."""
    event = {
        'index': 0,  # Set below under lock
        'timestamp': time.time(),
        'event_type': event_type,
        'detail': detail,
    }
    with _lock:
        if conversation_id not in _buffers:
            _buffers[conversation_id] = deque(maxlen=_MAX_EVENTS)
        buf = _buffers[conversation_id]
        event['index'] = len(buf)
        buf.append(event)


def get_events(conversation_id: int, since_index: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """Return events after since_index and the new cursor.

    Returns:
        (events_list, new_cursor) — pass new_cursor as since_index on next call.
    """
    with _lock:
        buf = _buffers.get(conversation_id)
        if not buf:
            return [], 0
        events = [e for e in buf if e['index'] >= since_index]
        new_cursor = buf[-1]['index'] + 1 if buf else 0
    return events, new_cursor


def clear_buffer(conversation_id: int):
    """Clear the event buffer for a conversation."""
    with _lock:
        _buffers.pop(conversation_id, None)
```

- [ ] **Step 2: Commit**

```bash
git add services/playtest_events.py
git commit -m "feat(playtest): add in-memory event buffer for chat playtest"
```

---

### Task 2: Instrument MessageRouter with playtest events

**Files:**
- Modify: `services/message_router.py`

The goal is to add `playtest_log()` calls at key pipeline points, each gated behind `if conversation.platform == 'playtest':` so there is zero overhead for real conversations.

- [ ] **Step 1: Add import at top of `message_router.py`**

After the existing imports (around line 20, after `logger = logging.getLogger(__name__)`), add:

```python
from .playtest_events import playtest_log
```

- [ ] **Step 2: Instrument `process_incoming_message()` — after message stored (line ~127)**

After `logger.info(f"Message stored: {message.id}")` (around line 127), add:

```python
            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'guest_message_stored',
                             f'Message #{message.id}: "{message_content[:80]}"')
```

- [ ] **Step 3: Instrument `process_incoming_message()` — duplicate detection (line ~122)**

After `logger.info(f"Duplicate message skipped: ...")` (around line 122), add:

```python
                if conversation.platform == 'playtest':
                    playtest_log(conversation.id, 'dedup_check',
                                 f'Duplicate skipped — existing message #{message.id} '
                                 f'(platform_message_id={platform_message_id})')
```

- [ ] **Step 4: Instrument `process_incoming_message()` — memory extraction (line ~169)**

After `logger.info(f"Memory extraction completed for message {message.id}")` (around line 169), add:

```python
                    if conversation.platform == 'playtest':
                        playtest_log(conversation.id, 'memory_extraction',
                                     f'Memory extraction completed for message #{message.id}')
```

- [ ] **Step 5: Instrument `process_incoming_message()` — memory extraction failed (line ~171)**

After `logger.warning(f"Memory extraction failed: {e}")` (around line 171), add:

```python
                    if conversation.platform == 'playtest':
                        playtest_log(conversation.id, 'memory_extraction',
                                     f'Memory extraction failed: {e}')
```

- [ ] **Step 6: Instrument `_generate_ai_response()` — start (line ~460)**

At the top of `_generate_ai_response()`, after the `is_acknowledgment` check block (after line 464), add:

```python
        if conversation.platform == 'playtest':
            playtest_log(conversation.id, 'ai_generation_start',
                         f'Generating AI response for: "{trigger_message.content[:80]}"')
```

But if acknowledgment IS detected, log that instead. Right after the `logger.info(f"[AI SKIP] Acknowledgment detected...")` line (around line 463), add:

```python
            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'acknowledgment_skipped',
                             f'Acknowledgment detected: "{trigger_message.content[:50]}" — skipping AI')
```

- [ ] **Step 7: Instrument `_generate_ai_response()` — context filter (line ~615)**

After `logger.debug(f"[CONTEXT FILTER] auto-respond: {filtered.filter_log}")` (around line 615), add:

```python
        if conversation.platform == 'playtest':
            playtest_log(conversation.id, 'context_filter',
                         f'Context filter: {filtered.filter_log}')
```

- [ ] **Step 8: Instrument `_generate_ai_response()` — after AI response generated (line ~636)**

After the `if not response_text: return None` check (around line 636), add:

```python
        if conversation.platform == 'playtest':
            playtest_log(conversation.id, 'ai_response_generated',
                         f'AI response generated ({len(response_text)} chars): '
                         f'"{response_text[:100]}"')
```

- [ ] **Step 9: Instrument `_generate_ai_response()` — approval status (line ~656)**

After `logger.info(f"AI response saved as pending draft ...")` (around line 658), add:

```python
            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'approval_status',
                             f'Saved as PENDING draft (message #{ai_message.id}) — approval queue active')
```

And in the else branch (auto-approve path), after `# Auto-approve path` comment (around line 664), add:

```python
            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'approval_status',
                             f'Auto-approved (message #{ai_message.id}) — '
                             f'platform delivery skipped (playtest mode)')
```

- [ ] **Step 10: Instrument `_generate_ai_response()` — escalation check (line ~708)**

After `logger.info(f"[ESCALATION] Conversation {conversation.id} escalated ...")` (around line 713), add:

```python
                if conversation.platform == 'playtest':
                    playtest_log(conversation.id, 'escalation_check',
                                 'Escalation TRIGGERED — auto-respond paused')
```

- [ ] **Step 11: Instrument `process_owner_message()` — after message stored (line ~242)**

After the `message, _ = self._store_message(...)` call and `result['message_id'] = message.id` (around line 243), add:

```python
            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'owner_message_stored',
                             f'Owner message #{message.id}: "{content[:80]}"')
```

- [ ] **Step 12: Commit**

```bash
git add services/message_router.py
git commit -m "feat(playtest): instrument MessageRouter with playtest event logging"
```

---

### Task 3: Add playtest API endpoints

**Files:**
- Modify: `routes.py`

All endpoints are admin-only, placed near the existing debug API routes.

- [ ] **Step 1: Add 5 playtest API endpoints after the existing debug endpoints (after line ~416)**

Find the `api_debug_status` function (around line 419). After that function ends (around line 454), insert the playtest endpoints. Add them before the `api_conversations_last_updated` route:

```python
# ============================================================================
# CHAT PLAYTEST API (Debug)
# ============================================================================

@chatbot_bp.route('/api/debug/playtest/start', methods=['POST'])
@admin_required
def api_playtest_start():
    """Create a new playtest conversation."""
    import uuid
    from .services.playtest_events import playtest_log

    data = request.get_json() or {}
    guest_name = data.get('guest_name', 'Playtest Guest')

    # Create a dedicated playtest guest
    guest = Guest(
        name=guest_name,
        email=f"playtest-{uuid.uuid4().hex[:8]}@test.local"
    )
    db.session.add(guest)
    db.session.flush()

    # Create playtest conversation — AI enabled, auto-respond OFF by default
    conversation = Conversation(
        guest_id=guest.id,
        platform='playtest',
        platform_id=f"playtest-{uuid.uuid4().hex[:8]}",
        subject=f"Playtest {datetime.utcnow().strftime('%H:%M')}",
        status='active',
        ai_enabled=True,
        auto_respond=False,
        is_read=True
    )
    db.session.add(conversation)
    db.session.commit()

    playtest_log(conversation.id, 'conversation_created',
                 f'Playtest conversation #{conversation.id} created (guest: {guest_name})')

    return jsonify({
        'conversation_id': conversation.id,
        'guest_id': guest.id,
        'guest_name': guest_name
    })


@chatbot_bp.route('/api/debug/playtest/<int:conversation_id>/message', methods=['POST'])
@admin_required
def api_playtest_message(conversation_id):
    """Send a message in a playtest conversation as guest or host."""
    from .services.message_router import get_message_router

    conversation = Conversation.query.get_or_404(conversation_id)
    if conversation.platform != 'playtest':
        return jsonify({'error': 'Not a playtest conversation'}), 400

    data = request.get_json()
    if not data or not data.get('content', '').strip():
        return jsonify({'error': 'Content is required'}), 400

    content = data['content'].strip()
    role = data.get('role', 'guest')
    router = get_message_router()

    if role == 'guest':
        result = router.process_incoming_message(
            platform='playtest',
            platform_conversation_id=conversation.platform_id,
            sender_email=conversation.guest.email,
            sender_name=conversation.guest.name,
            message_content=content,
            subject=conversation.subject,
            auto_respond=False,
            skip_push=True
        )
        return jsonify({
            'message_id': result.get('message_id'),
            'success': result.get('success', False)
        })
    elif role == 'host':
        result = router.process_owner_message(
            conversation_id=conversation_id,
            content=content,
            extract_memory=True,
            sent_via_app=True
        )
        return jsonify({
            'message_id': result.get('message_id'),
            'success': result.get('success', False)
        })
    else:
        return jsonify({'error': 'Invalid role — use "guest" or "host"'}), 400


@chatbot_bp.route('/api/debug/playtest/<int:conversation_id>/ai-response', methods=['POST'])
@admin_required
def api_playtest_ai_response(conversation_id):
    """Generate an AI response for a playtest conversation."""
    from .services.message_router import get_message_router
    from .services.playtest_events import playtest_log

    conversation = Conversation.query.get_or_404(conversation_id)
    if conversation.platform != 'playtest':
        return jsonify({'error': 'Not a playtest conversation'}), 400

    router = get_message_router()
    result = router.generate_ai_response_for_conversation(conversation_id)

    if result.get('success'):
        return jsonify({
            'message_id': result.get('message_id'),
            'content': result.get('response'),
            'success': True
        })
    else:
        return jsonify({'error': result.get('error', 'AI generation failed')}), 500


@chatbot_bp.route('/api/debug/playtest/<int:conversation_id>/events')
@admin_required
def api_playtest_events(conversation_id):
    """Poll for new playtest events."""
    from .services.playtest_events import get_events

    since = request.args.get('since', 0, type=int)
    events, cursor = get_events(conversation_id, since)
    return jsonify({'events': events, 'cursor': cursor})


@chatbot_bp.route('/api/debug/playtest/<int:conversation_id>/messages')
@admin_required
def api_playtest_messages(conversation_id):
    """Get all messages in a playtest conversation."""
    conversation = Conversation.query.get_or_404(conversation_id)
    if conversation.platform != 'playtest':
        return jsonify({'error': 'Not a playtest conversation'}), 400

    messages = Message.query.filter_by(
        conversation_id=conversation_id
    ).order_by(Message.sent_at.asc()).all()

    return jsonify({
        'messages': [m.to_dict() for m in messages]
    })
```

- [ ] **Step 2: Filter playtest conversations from the inbox page query**

In the `index()` function (around line 251), change:

```python
    conversations = Conversation.query.options(
        joinedload(Conversation.guest),
        joinedload(Conversation.property)
    ).order_by(Conversation.updated_at.desc()).limit(50).all()
```

to:

```python
    conversations = Conversation.query.options(
        joinedload(Conversation.guest),
        joinedload(Conversation.property)
    ).filter(Conversation.platform != 'playtest').order_by(Conversation.updated_at.desc()).limit(50).all()
```

- [ ] **Step 3: Filter playtest from the API conversations endpoint**

In `api_get_conversations()` (around line 476), after the line:

```python
    query = Conversation.query.options(joinedload(Conversation.guest), joinedload(Conversation.property))
```

Add:

```python
    query = query.filter(Conversation.platform != 'playtest')
```

- [ ] **Step 4: Filter playtest from the unread count in `api_conversations_last_updated()`**

In `api_conversations_last_updated()` (around line 461), change the `ts_result` query to exclude playtest:

```python
    ts_result = db.session.query(func.max(Conversation.updated_at)).filter(
        Conversation.platform != 'playtest'
    ).scalar()
    unread = db.session.query(func.count(Conversation.id)).filter(
        Conversation.is_read == False,
        Conversation.platform != 'playtest'
    ).scalar()
```

- [ ] **Step 5: Commit**

```bash
git add routes.py
git commit -m "feat(playtest): add playtest API endpoints and filter from inbox"
```

---

### Task 4: Build the Chat Playtest tab UI

**Files:**
- Modify: `templates/chatbot/debug.html`

This is the largest task — adds the 4th tab with the complete split-panel UI.

- [ ] **Step 1: Add playtest CSS styles**

In the `<style>` block in `debug.html`, before the closing `</style>` tag (around line 69), add:

```css
    /* Chat Playtest */
    .playtest-layout { display: flex; gap: 16px; height: calc(100vh - 200px); }
    .playtest-chat { flex: 6; display: flex; flex-direction: column; border: 1px solid var(--border-color, #ddd); border-radius: 8px; background: var(--card-bg, #fff); overflow: hidden; }
    .playtest-events { flex: 4; display: flex; flex-direction: column; border: 1px solid var(--border-color, #ddd); border-radius: 8px; background: var(--card-bg, #fff); overflow: hidden; }

    .playtest-toolbar { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-bottom: 1px solid var(--border-color, #ddd); flex-wrap: wrap; }
    .playtest-toolbar .btn { padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85em; font-weight: 600; }
    .playtest-toolbar .btn-start { background: #22c55e; color: #fff; }
    .playtest-toolbar .btn-start:hover { background: #16a34a; }
    .playtest-info { font-size: 0.8em; color: var(--text-secondary, #888); margin-left: auto; }

    .role-switcher { display: flex; border: 2px solid var(--border-color, #ddd); border-radius: 6px; overflow: hidden; }
    .role-btn { padding: 6px 14px; border: none; cursor: pointer; font-size: 0.85em; font-weight: 600; background: var(--card-bg, #fff); color: var(--text-color, #333); transition: all 0.15s; }
    .role-btn.active-guest { background: #3b82f6; color: #fff; }
    .role-btn.active-host { background: var(--primary-color, #7B2332); color: #fff; }

    .playtest-messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 8px; }
    .playtest-msg { max-width: 75%; padding: 10px 14px; border-radius: 12px; font-size: 0.9em; line-height: 1.4; word-break: break-word; }
    .playtest-msg.guest { align-self: flex-start; background: #f3f4f6; color: #1f2937; border-bottom-left-radius: 4px; }
    .playtest-msg.owner { align-self: flex-end; background: var(--primary-color, #7B2332); color: #fff; border-bottom-right-radius: 4px; }
    .playtest-msg.ai { align-self: flex-end; background: #4338ca; color: #fff; border-bottom-right-radius: 4px; }
    .playtest-msg .msg-meta { font-size: 0.75em; opacity: 0.7; margin-top: 4px; }
    .playtest-msg .msg-badge { font-size: 0.7em; font-weight: 700; opacity: 0.8; text-transform: uppercase; margin-bottom: 2px; }

    .playtest-input { display: flex; gap: 8px; padding: 10px 14px; border-top: 1px solid var(--border-color, #ddd); }
    .playtest-input input { flex: 1; padding: 8px 12px; border: 1px solid var(--border-color, #ddd); border-radius: 6px; font-size: 0.9em; background: var(--card-bg, #fff); color: var(--text-color, #333); }
    .playtest-input button { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85em; font-weight: 600; }
    .playtest-input .btn-send { background: #3b82f6; color: #fff; }
    .playtest-input .btn-send.host-mode { background: var(--primary-color, #7B2332); }
    .playtest-input .btn-ai { background: #4338ca; color: #fff; }
    .playtest-input .btn-ai:disabled { opacity: 0.5; cursor: not-allowed; }

    .playtest-events-header { padding: 10px 14px; border-bottom: 1px solid var(--border-color, #ddd); display: flex; align-items: center; justify-content: space-between; }
    .playtest-events-header h3 { margin: 0; font-size: 0.95em; }
    .playtest-event-list { flex: 1; overflow-y: auto; padding: 8px; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.8em; }
    .playtest-event { padding: 4px 8px; border-bottom: 1px solid var(--border-color, #eee); display: flex; gap: 8px; align-items: flex-start; }
    .playtest-event .ev-time { color: var(--text-secondary, #888); white-space: nowrap; min-width: 75px; }
    .playtest-event .ev-type { font-weight: 700; white-space: nowrap; min-width: 140px; }
    .playtest-event .ev-type.stored { color: #16a34a; }
    .playtest-event .ev-type.ai { color: #4338ca; }
    .playtest-event .ev-type.dedup { color: #d97706; }
    .playtest-event .ev-type.escalation { color: #dc2626; }
    .playtest-event .ev-type.filter { color: #0891b2; }
    .playtest-event .ev-type.approval { color: #7c3aed; }
    .playtest-event .ev-type.memory { color: #059669; }
    .playtest-event .ev-type.info { color: var(--text-secondary, #888); }
    .playtest-event .ev-detail { word-break: break-word; color: var(--text-color, #333); }

    .playtest-empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary, #888); font-size: 0.95em; }

    .auto-respond-toggle { display: flex; align-items: center; gap: 4px; font-size: 0.8em; }
    .auto-respond-toggle input { cursor: pointer; }
```

- [ ] **Step 2: Add the Playtest tab button**

In the `debug-tabs` div (around line 85-95), after the API Calls tab button, add:

```html
        <button class="debug-tab" onclick="switchTab('playtest')">
            <i class="fas fa-comments"></i> Chat Playtest
        </button>
```

- [ ] **Step 3: Add the Playtest tab HTML content**

After the `<!-- API CALLS TAB -->` closing `</div>` (around line 142), add:

```html
    <!-- CHAT PLAYTEST TAB -->
    <div id="tab-playtest" class="tab-content" style="display:none;">
        <div class="playtest-layout">
            <!-- Left: Chat Panel -->
            <div class="playtest-chat">
                <div class="playtest-toolbar">
                    <button class="btn btn-start" onclick="playtestStart()">
                        <i class="fas fa-plus"></i> New Playtest
                    </button>
                    <div class="role-switcher">
                        <button class="role-btn active-guest" id="roleGuest" onclick="playtestSetRole('guest')">Guest</button>
                        <button class="role-btn" id="roleHost" onclick="playtestSetRole('host')">Host</button>
                    </div>
                    <label class="auto-respond-toggle" title="Auto-generate AI response after each guest message">
                        <input type="checkbox" id="playtestAutoAI"> Auto AI
                    </label>
                    <span class="playtest-info" id="playtestInfo">No active playtest</span>
                </div>
                <div class="playtest-messages" id="playtestMessages">
                    <div class="playtest-empty">Click "New Playtest" to start</div>
                </div>
                <div class="playtest-input">
                    <input type="text" id="playtestInput" placeholder="Type a message..."
                           onkeydown="if(event.key==='Enter')playtestSend()" disabled>
                    <button class="btn-send btn" id="playtestSendBtn" onclick="playtestSend()" disabled>Send</button>
                    <button class="btn-ai btn" id="playtestAiBtn" onclick="playtestGenerateAI()" disabled title="Generate AI response">
                        <i class="fas fa-magic"></i> AI
                    </button>
                </div>
            </div>
            <!-- Right: Event Log -->
            <div class="playtest-events">
                <div class="playtest-events-header">
                    <h3><i class="fas fa-stream"></i> Pipeline Events</h3>
                    <button class="btn btn-secondary" onclick="playtestClearEvents()" style="padding:2px 10px;font-size:0.8em;">Clear</button>
                </div>
                <div class="playtest-event-list" id="playtestEventList">
                    <div class="playtest-empty">Events will appear here during playtest</div>
                </div>
            </div>
        </div>
    </div>
```

- [ ] **Step 4: Add the Playtest JavaScript**

At the bottom of the `<script>` block, before the closing `</script>` tag (before the final `refreshAll();` call around line 561), add:

```javascript
// ============================================================================
// CHAT PLAYTEST
// ============================================================================

let playtestConvId = null;
let playtestRole = 'guest';
let playtestEventCursor = 0;
let playtestEventPoller = null;

function playtestSetRole(role) {
    playtestRole = role;
    const guestBtn = document.getElementById('roleGuest');
    const hostBtn = document.getElementById('roleHost');
    const sendBtn = document.getElementById('playtestSendBtn');
    const input = document.getElementById('playtestInput');

    guestBtn.className = role === 'guest' ? 'role-btn active-guest' : 'role-btn';
    hostBtn.className = role === 'host' ? 'role-btn active-host' : 'role-btn';
    sendBtn.className = role === 'host' ? 'btn-send btn host-mode' : 'btn-send btn';
    input.placeholder = role === 'guest' ? 'Type as guest...' : 'Type as host...';
}

function playtestStart() {
    const name = 'Playtest Guest';
    fetch('/chatbot/api/debug/playtest/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guest_name: name })
    })
    .then(r => r.json())
    .then(data => {
        playtestConvId = data.conversation_id;
        playtestEventCursor = 0;
        document.getElementById('playtestMessages').innerHTML = '';
        document.getElementById('playtestEventList').innerHTML = '';
        document.getElementById('playtestInfo').textContent =
            `Conversation #${data.conversation_id} | Guest: ${data.guest_name}`;
        document.getElementById('playtestInput').disabled = false;
        document.getElementById('playtestSendBtn').disabled = false;
        document.getElementById('playtestAiBtn').disabled = false;

        // Start event polling
        if (playtestEventPoller) clearInterval(playtestEventPoller);
        playtestEventPoller = setInterval(playtestPollEvents, 1000);
    })
    .catch(err => console.error('Playtest start error:', err));
}

function playtestSend() {
    const input = document.getElementById('playtestInput');
    const content = input.value.trim();
    if (!content || !playtestConvId) return;

    // Show message immediately in UI
    playtestAddMessage(content, playtestRole);
    input.value = '';

    fetch(`/chatbot/api/debug/playtest/${playtestConvId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: content, role: playtestRole })
    })
    .then(r => r.json())
    .then(data => {
        if (!data.success) {
            playtestAddEvent('error', `Send failed: ${data.error || 'unknown'}`);
        }
        // If guest message + auto-AI enabled, trigger AI
        if (playtestRole === 'guest' && document.getElementById('playtestAutoAI').checked) {
            setTimeout(() => playtestGenerateAI(), 300);
        }
    })
    .catch(err => {
        playtestAddEvent('error', `Network error: ${err.message}`);
    });
}

function playtestGenerateAI() {
    if (!playtestConvId) return;
    const aiBtn = document.getElementById('playtestAiBtn');
    aiBtn.disabled = true;
    aiBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> AI';

    fetch(`/chatbot/api/debug/playtest/${playtestConvId}/ai-response`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(r => r.json())
    .then(data => {
        if (data.success && data.content) {
            playtestAddMessage(data.content, 'ai');
        } else {
            playtestAddEvent('error', `AI failed: ${data.error || 'unknown'}`);
        }
    })
    .catch(err => {
        playtestAddEvent('error', `AI error: ${err.message}`);
    })
    .finally(() => {
        aiBtn.disabled = false;
        aiBtn.innerHTML = '<i class="fas fa-magic"></i> AI';
    });
}

function playtestAddMessage(content, senderType) {
    const container = document.getElementById('playtestMessages');
    // Remove empty state
    const empty = container.querySelector('.playtest-empty');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.className = `playtest-msg ${senderType}`;

    const badgeText = senderType === 'guest' ? 'Guest' : senderType === 'ai' ? 'UMI' : 'Host';
    const time = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    div.innerHTML = `<div class="msg-badge">${badgeText}</div>` +
        escapeHtml(content) +
        `<div class="msg-meta">${time}</div>`;

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function playtestPollEvents() {
    if (!playtestConvId) return;

    fetch(`/chatbot/api/debug/playtest/${playtestConvId}/events?since=${playtestEventCursor}`)
    .then(r => r.json())
    .then(data => {
        if (data.events && data.events.length > 0) {
            data.events.forEach(ev => playtestAddEvent(ev.event_type, ev.detail, ev.timestamp));
            playtestEventCursor = data.cursor;
        }
    })
    .catch(() => {}); // Silently ignore polling errors
}

function playtestAddEvent(eventType, detail, timestamp) {
    const container = document.getElementById('playtestEventList');
    const empty = container.querySelector('.playtest-empty');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.className = 'playtest-event';

    // Format timestamp
    let timeStr;
    if (timestamp) {
        const d = new Date(timestamp * 1000);
        timeStr = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 1 });
    } else {
        timeStr = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    // Color-code event types
    let typeClass = 'info';
    if (eventType.includes('stored') || eventType === 'conversation_created') typeClass = 'stored';
    else if (eventType.includes('ai') || eventType === 'acknowledgment_skipped') typeClass = 'ai';
    else if (eventType.includes('dedup')) typeClass = 'dedup';
    else if (eventType.includes('escalation')) typeClass = 'escalation';
    else if (eventType.includes('filter') || eventType === 'context_filter') typeClass = 'filter';
    else if (eventType.includes('approval')) typeClass = 'approval';
    else if (eventType.includes('memory')) typeClass = 'memory';

    div.innerHTML =
        `<span class="ev-time">${timeStr}</span>` +
        `<span class="ev-type ${typeClass}">${eventType}</span>` +
        `<span class="ev-detail">${escapeHtml(detail)}</span>`;

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function playtestClearEvents() {
    document.getElementById('playtestEventList').innerHTML =
        '<div class="playtest-empty">Events will appear here during playtest</div>';
}
```

- [ ] **Step 5: Update the `switchTab` function to handle event polling**

In the existing `switchTab` function (around line 151), add cleanup when leaving the playtest tab. Replace the function:

```javascript
function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
    document.getElementById('tab-' + tab).style.display = '';
    document.querySelectorAll('.debug-tab').forEach(el => el.classList.remove('active'));
    event.currentTarget.classList.add('active');
    refreshAll();
}
```

with:

```javascript
function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
    document.getElementById('tab-' + tab).style.display = '';
    document.querySelectorAll('.debug-tab').forEach(el => el.classList.remove('active'));
    event.currentTarget.classList.add('active');
    if (tab !== 'playtest') {
        refreshAll();
    }
}
```

- [ ] **Step 6: Commit**

```bash
git add templates/chatbot/debug.html
git commit -m "feat(playtest): add Chat Playtest tab to debug dashboard"
```

---

### Task 5: Manual integration test

No automated tests for this feature — it's a debug/admin tool with UI. Verify manually.

- [ ] **Step 1: Start the dev server**

```bash
python -m ChatBotAI.run
```

- [ ] **Step 2: Test the playtest flow**

1. Navigate to `/chatbot/debug`
2. Click the "Chat Playtest" tab
3. Click "New Playtest" — verify conversation info appears and event log shows `conversation_created`
4. With "Guest" role selected, type a message and send — verify message appears left-aligned, events show `guest_message_stored` and `memory_extraction`
5. Switch to "Host" role, type a message and send — verify message appears right-aligned, events show `owner_message_stored`
6. Click "AI" button — verify typing indicator appears, AI response shows up as purple bubble, events show `ai_generation_start`, `context_filter`, `ai_response_generated`, and `approval_status`
7. Check "Auto AI" checkbox, switch to Guest, send a message — verify AI auto-generates a response after the guest message
8. Check the main inbox (`/chatbot/`) — verify playtest conversations do NOT appear
9. Send the same guest message twice rapidly — check event log for dedup behavior

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(playtest): address integration test findings"
```
