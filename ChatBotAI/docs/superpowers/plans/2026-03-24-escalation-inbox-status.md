# Escalation System + Inbox Status Indicators — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the AI detects it can't handle a guest message (restricted topic), automatically escalate — pause auto-respond, flag the conversation, and notify the host. Show escalation state and AI status in the inbox.

**Architecture:** Post-response phrase detection in message_router triggers escalation. New `escalated` + `escalated_at` columns on Conversation. New `/resolve` API endpoint. Inbox cards gain escalation styling and AI auto-respond badge. Filter-state extended with `data-escalated` attribute.

**Tech Stack:** Flask, SQLAlchemy, Alembic (batch mode for SQLite), vanilla JS, CSS variables

**Spec:** `docs/superpowers/specs/2026-03-24-escalation-inbox-status-design.md`

---

### Task 1: Database Migration — Add escalated columns

**Files:**
- Modify: `models.py:187-232` (Conversation class)
- Create: `migrations/versions/p8_escalation_add_escalated_flag.py`

- [ ] **Step 1: Add columns to Conversation model**

In `models.py`, add after line 218 (`last_synced_message_at`):

```python
# Escalation tracking
escalated = db.Column(db.Boolean, default=False, server_default='0', nullable=False, index=True)
escalated_at = db.Column(db.DateTime, nullable=True)
```

- [ ] **Step 2: Add fields to `to_dict()`**

In `models.py` Conversation.to_dict(), add after `'user_id'` line (257):

```python
'escalated': self.escalated,
'escalated_at': self.escalated_at.isoformat() if self.escalated_at else None,
```

- [ ] **Step 3: Create migration file**

Create `migrations/versions/p8_escalation_add_escalated_flag.py`:

```python
"""Add escalated flag and timestamp to conversation

Revision ID: p8_escalation
Revises: p7_readcursor
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'p8_escalation'
down_revision = 'p7_readcursor'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('escalated', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('escalated_at', sa.DateTime(), nullable=True))
        batch_op.create_index(op.f('ix_conversation_escalated'), ['escalated'])


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_conversation_escalated'))
        batch_op.drop_column('escalated_at')
        batch_op.drop_column('escalated')
```

- [ ] **Step 4: Run migration**

```bash
cd /c/Users/admin/Documents/FlaskApp && python -m ChatBotAI.run db upgrade
```

Expected: Migration applies successfully, no errors.

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/models.py ChatBotAI/migrations/versions/p8_escalation_add_escalated_flag.py
git commit -m "feat(escalation): add escalated flag and timestamp to conversation model"
```

---

### Task 2: Escalation Detection in Message Router

**Files:**
- Modify: `services/message_router.py:409-550` (_generate_ai_response method)

- [ ] **Step 1: Add `_is_escalation_response()` method**

Add after the `_store_message` method (after line 407) and before `_generate_ai_response`:

```python
@staticmethod
def _is_escalation_response(response_text: str) -> bool:
    """Check if AI response contains escalation phrases.

    Detects when the AI has used the escalation holding response
    (e.g. "I'll check with my colleague"). Uses only high-specificity
    phrases to avoid false positives.
    """
    if not response_text:
        return False
    text_lower = response_text.lower()
    escalation_phrases = ['kollegen', 'kollegin', 'colleague']
    return any(phrase in text_lower for phrase in escalation_phrases)
```

- [ ] **Step 2: Wire detection into `_generate_ai_response()`**

In `_generate_ai_response()`, add AFTER both the Smoobu send block and Gmail send block (after line 544, just before the `return` statement). This placement is critical — the holding response ("I'll check with my colleague") must be sent to the guest first via the platform, THEN we pause auto-respond. If we set `auto_respond = False` earlier, the send blocks (which check `conversation.auto_respond`) would skip sending.

```python
        # Check for escalation response — AFTER platform send, so the holding
        # message reaches the guest before we pause auto-respond
        if self._is_escalation_response(response_text):
            conversation.escalated = True
            conversation.escalated_at = datetime.utcnow()
            conversation.auto_respond = False
            db.session.commit()
            logger.info(f"[ESCALATION] Conversation {conversation.id} escalated — auto-respond paused")

            # Send escalation push notification
            try:
                from .push_service import get_push_service
                push = get_push_service()
                if push:
                    guest = conversation.guest
                    push.notify_escalation(
                        conversation,
                        guest.name or guest.email or 'Guest'
                    )
            except Exception as e:
                logger.warning(f"Escalation push notification failed: {e}")
```

- [ ] **Step 3: Commit**

```bash
git add ChatBotAI/services/message_router.py
git commit -m "feat(escalation): detect escalation phrases and pause auto-respond"
```

---

### Task 3: Escalation Push Notification

**Files:**
- Modify: `services/push_service.py:122-139` (after notify_new_guest_message)

- [ ] **Step 1: Add `notify_escalation()` method**

Add after `notify_new_guest_message` method (after line 139):

```python
def notify_escalation(self, conversation, guest_name: str):
    """Send push notification when a conversation is escalated.
    Assignment-aware: notifies assigned user or all users if unassigned."""
    from ..models import User

    title = 'Braucht Aufmerksamkeit'
    body = guest_name
    url = f'/chatbot/conversation/{conversation.id}'
    tag = f'escalation-{conversation.id}'

    if conversation.user_id:
        self.send_notification_to_user(conversation.user_id, title, body, url, tag)
    else:
        users = User.query.all()
        for user in users:
            self.send_notification_to_user(user.id, title, body, url, tag)
```

- [ ] **Step 2: Commit**

```bash
git add ChatBotAI/services/push_service.py
git commit -m "feat(escalation): add escalation push notification"
```

---

### Task 4: Resolve API Endpoint + Server-side Filtering

**Files:**
- Modify: `routes.py:343-367` (api_get_conversations) and add new endpoint

- [ ] **Step 1: Add `?escalated=true` filter to conversations API**

In `api_get_conversations()` (routes.py), after line 351 (`if status: query = query.filter_by(status=status)`), add:

```python
    escalated = request.args.get('escalated')
    if escalated == 'true':
        query = query.filter_by(escalated=True)
```

- [ ] **Step 2: Add resolve endpoint**

Add after the `api_toggle_auto_respond` function (after line 1378):

```python
@chatbot_bp.route('/api/conversations/<int:conversation_id>/resolve', methods=['POST'])
def api_resolve_escalation(conversation_id):
    """Resolve an escalated conversation. Does NOT re-enable auto-respond."""
    conversation = Conversation.query.get_or_404(conversation_id)

    conversation.escalated = False
    conversation.escalated_at = None
    db.session.commit()

    return jsonify({
        'success': True,
        'escalated': conversation.escalated,
        'auto_respond': conversation.auto_respond
    })
```

- [ ] **Step 3: Commit**

```bash
git add ChatBotAI/routes.py
git commit -m "feat(escalation): add resolve endpoint and server-side escalated filter"
```

---

### Task 5: Inbox Card — Escalation Styling + AI Badge

**Files:**
- Modify: `static/js/inbox.js:43-143` (createConversationCard, updateConversationCard)
- Modify: `static/css/style.css` (add escalation and AI status styles)

- [ ] **Step 1: Update `createConversationCard()` in inbox.js**

In `createConversationCard()`, after line 52 (`card.dataset.isRead`), add:

```javascript
    card.dataset.escalated = conv.escalated ? 'true' : 'false';
    card.dataset.autoRespond = conv.auto_respond ? 'true' : 'false';
    if (conv.escalated) card.classList.add('escalated');
```

Replace the `aiBadge` line (63) and modify the `conversation-meta` section inside innerHTML. Replace lines 63 and 79-83 with:

```javascript
    const aiBadge = conv.ai_enabled
        ? `<span class="ai-badge ${conv.auto_respond ? 'auto-respond-on' : 'auto-respond-off'}" title="${conv.auto_respond ? (i18n.t('inbox.aiActive') || 'KI aktiv') : (i18n.t('inbox.aiPaused') || 'KI pausiert')}"><i class="fas fa-robot"></i></span>`
        : '';
    const escalationLabel = conv.escalated
        ? `<span class="escalation-badge"><i class="fas fa-exclamation-triangle"></i> ${i18n.t('inbox.needsAttention') || 'Braucht Aufmerksamkeit'}</span>`
        : '';
```

And in the `conversation-meta` div inside innerHTML, replace with:

```javascript
        <div class="conversation-meta">
            <span class="platform-badge ${conv.platform}">${conv.platform.charAt(0).toUpperCase() + conv.platform.slice(1)}</span>
            ${aiBadge}
            ${escalationLabel}
            <span class="status-badge ${conv.status}">${formatStatus(conv.status)}</span>
            ${conv.status !== 'closed' ? `<button class="btn-close-conv" onclick="closeConversation(event, ${conv.id})" title="${i18n.t('inbox.closeChat') || 'Gespräch beenden'}"><i class="fas fa-times"></i></button>` : ''}
        </div>
```

- [ ] **Step 2: Update `updateConversationCard()` in inbox.js**

After line 93 (`card.dataset.isRead`), add:

```javascript
    card.dataset.escalated = conv.escalated ? 'true' : 'false';
    card.dataset.autoRespond = conv.auto_respond ? 'true' : 'false';
    card.classList.toggle('escalated', !!conv.escalated);
```

After the existing AI badge update block (lines 133-142), add:

```javascript
    // Update escalation badge
    const existingEscalation = card.querySelector('.escalation-badge');
    if (conv.escalated && !existingEscalation) {
        const badge = document.createElement('span');
        badge.className = 'escalation-badge';
        badge.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${i18n.t('inbox.needsAttention') || 'Braucht Aufmerksamkeit'}`;
        metaEl.insertBefore(badge, statusEl);
    } else if (!conv.escalated && existingEscalation) {
        existingEscalation.remove();
    }

    // Update AI badge auto-respond state
    if (existingAiBadge) {
        existingAiBadge.classList.toggle('auto-respond-on', !!conv.auto_respond);
        existingAiBadge.classList.toggle('auto-respond-off', !conv.auto_respond);
        existingAiBadge.title = conv.auto_respond
            ? (i18n.t('inbox.aiActive') || 'KI aktiv')
            : (i18n.t('inbox.aiPaused') || 'KI pausiert');
    }
```

- [ ] **Step 3: Add CSS styles**

Append to `static/css/style.css`:

```css
/* Escalation card styling */
.conversation-card.escalated {
    border-left: 4px solid var(--danger-color, #e74c3c);
    background: color-mix(in srgb, var(--danger-color, #e74c3c) 5%, var(--card-bg, white));
}

:root[data-theme="dark"] .conversation-card.escalated {
    background: color-mix(in srgb, var(--danger-color, #e74c3c) 10%, var(--card-bg, #1e1e1e));
}

.escalation-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--danger-color, #e74c3c);
    white-space: nowrap;
}

.escalation-badge i {
    font-size: 0.65rem;
}

/* AI auto-respond status indicator */
.ai-badge.auto-respond-on {
    color: var(--success-color, #27ae60);
}

.ai-badge.auto-respond-off {
    color: var(--text-muted, #999);
    opacity: 0.6;
}
```

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/static/js/inbox.js ChatBotAI/static/css/style.css
git commit -m "feat(escalation): add escalation styling and AI status badge to inbox cards"
```

---

### Task 6: Resolve Button in Conversation View

**Files:**
- Modify: `templates/chatbot/conversation.html:42-60` (conversation-actions area)
- Modify: `static/js/conversation.js` (add resolve handler)

- [ ] **Step 1: Add resolve button to conversation.html**

After the auto-respond button (line 56), add:

```html
            {% if conversation.escalated %}
            <button class="btn btn-icon btn-escalation-resolve" onclick="resolveEscalation()" id="resolveEscalationBtn"
                data-i18n-title="conversation.escalation.resolve" title="Als gelöst markieren">
                <i class="fas fa-check-circle"></i>
                <span class="toggle-status" data-i18n="conversation.escalation.resolve">Lösen</span>
            </button>
            {% endif %}
```

Also add to the mobile overflow menu after the auto-respond button (after line 78):

```html
            {% if conversation.escalated %}
            <button class="overflow-menu-item btn-escalation-resolve" onclick="resolveEscalation()" id="mobileResolveBtn">
                <i class="fas fa-check-circle"></i>
                <span data-i18n="conversation.escalation.resolve">Als gelöst markieren</span>
            </button>
            {% endif %}
```

Add the escalated flag to CONV_CONFIG (around line 181), after `autoRespond`:

```javascript
        escalated: {{ 'true' if conversation.escalated else 'false' }},
```

- [ ] **Step 2: Add an escalation banner at the top of messages area**

After the messages-container opening div (line 87), before the load-older block:

```html
        {% if conversation.escalated %}
        <div class="escalation-banner" id="escalationBanner">
            <i class="fas fa-exclamation-triangle"></i>
            <span data-i18n="conversation.escalation.banner">Dieses Gespräch wurde eskaliert und benötigt Ihre Aufmerksamkeit.</span>
            <button class="btn btn-sm btn-resolve" onclick="resolveEscalation()" data-i18n="conversation.escalation.resolve">Als gelöst markieren</button>
        </div>
        {% endif %}
```

- [ ] **Step 3: Add resolve handler to conversation.js**

Add after the `toggleAutoRespond` function in conversation.js:

```javascript
function resolveEscalation() {
    fetch(`/chatbot/api/conversations/${conversationId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            // Remove escalation UI elements
            const banner = document.getElementById('escalationBanner');
            if (banner) banner.remove();

            const resolveBtn = document.getElementById('resolveEscalationBtn');
            if (resolveBtn) resolveBtn.remove();

            const mobileResolveBtn = document.getElementById('mobileResolveBtn');
            if (mobileResolveBtn) mobileResolveBtn.remove();

            showNotification(i18n.t('conversation.escalation.resolved') || 'Eskalation gelöst', 'success');
        }
    })
    .catch(err => console.error('Failed to resolve escalation:', err));
}
```

- [ ] **Step 4: Add escalation banner + resolve button CSS**

Append to `static/css/style.css`:

```css
/* Escalation banner in conversation view */
.escalation-banner {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    background: color-mix(in srgb, var(--danger-color, #e74c3c) 10%, var(--card-bg, white));
    border: 1px solid var(--danger-color, #e74c3c);
    border-radius: 8px;
    margin: 8px 16px;
    font-size: 0.85rem;
    color: var(--danger-color, #e74c3c);
}

.escalation-banner i {
    font-size: 1rem;
    flex-shrink: 0;
}

.escalation-banner .btn-resolve {
    margin-left: auto;
    padding: 4px 12px;
    background: var(--danger-color, #e74c3c);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.8rem;
    white-space: nowrap;
}

.escalation-banner .btn-resolve:hover {
    opacity: 0.85;
}

.btn-escalation-resolve {
    color: var(--danger-color, #e74c3c) !important;
}

:root[data-theme="dark"] .escalation-banner {
    background: color-mix(in srgb, var(--danger-color, #e74c3c) 15%, var(--card-bg, #1e1e1e));
}
```

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/templates/chatbot/conversation.html ChatBotAI/static/js/conversation.js ChatBotAI/static/css/style.css
git commit -m "feat(escalation): add resolve button and escalation banner to conversation view"
```

---

### Task 7: Inbox Filter for Escalated Conversations

**Files:**
- Modify: `templates/chatbot/inbox.html:59-65` (status filter group)
- Modify: `static/js/filter-state.js:171-198` (applyFilters method)

- [ ] **Step 1: Add escalated filter button**

In `inbox.html`, after the "closed" filter button (line 64), add:

```html
            <button class="filter-btn" data-filter-status="escalated" data-i18n="inbox.filter.escalated">Eskaliert</button>
```

- [ ] **Step 2: Update `applyFilters()` in filter-state.js**

Replace line 178:

```javascript
const matchesStatus = !this.state.status || card.dataset.status === this.state.status;
```

With:

```javascript
const matchesStatus = !this.state.status
    || (this.state.status === 'escalated' ? card.dataset.escalated === 'true' : card.dataset.status === this.state.status);
```

- [ ] **Step 3: Wire server-side filtering into inbox fetch**

In `static/js/inbox.js`, update the `fullInboxFetch()` function (line 508-510). Replace:

```javascript
async function fullInboxFetch(signal) {
    const response = await fetch('/chatbot/api/conversations?per_page=50', { signal });
```

With:

```javascript
async function fullInboxFetch(signal) {
    let url = '/chatbot/api/conversations?per_page=50';
    if (filterState.getState().status === 'escalated') {
        url += '&escalated=true';
    }
    const response = await fetch(url, { signal });
```

This ensures escalated conversations beyond the first page are fetched from the server when the escalated filter is active.

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/templates/chatbot/inbox.html ChatBotAI/static/js/filter-state.js ChatBotAI/static/js/inbox.js
git commit -m "feat(escalation): add escalated filter to inbox with server-side support"
```

---

### Task 8: i18n Translation Keys

**Files:**
- Modify: `static/js/i18n.js`

- [ ] **Step 1: Add German + English translation keys**

Add to the German translations object:

```javascript
// Inbox escalation & AI status
'inbox.needsAttention': 'Braucht Aufmerksamkeit',
'inbox.aiActive': 'KI aktiv',
'inbox.aiPaused': 'KI pausiert',
'inbox.filter.escalated': 'Eskaliert',

// Conversation escalation
'conversation.escalation.resolve': 'Als gelöst markieren',
'conversation.escalation.banner': 'Dieses Gespräch wurde eskaliert und benötigt Ihre Aufmerksamkeit.',
'conversation.escalation.resolved': 'Eskalation gelöst',
```

Add to the English translations object:

```javascript
// Inbox escalation & AI status
'inbox.needsAttention': 'Needs Attention',
'inbox.aiActive': 'AI Active',
'inbox.aiPaused': 'AI Paused',
'inbox.filter.escalated': 'Escalated',

// Conversation escalation
'conversation.escalation.resolve': 'Mark as Resolved',
'conversation.escalation.banner': 'This conversation has been escalated and needs your attention.',
'conversation.escalation.resolved': 'Escalation resolved',
```

- [ ] **Step 2: Bump cache version for i18n.js**

Update the version query parameter for i18n.js in `templates/chatbot/base.html` from `?v=13` to `?v=14`.

- [ ] **Step 3: Commit**

```bash
git add ChatBotAI/static/js/i18n.js ChatBotAI/templates/chatbot/base.html
git commit -m "feat(escalation): add i18n translations for escalation UI"
```

---

### Task 9: Bump Cache Versions

**Files:**
- Modify: `templates/chatbot/base.html` (script/style version query params)

- [ ] **Step 1: Bump versions for all modified JS/CSS files**

Update in `base.html`:
- `style.css`: v14 → v15
- `inbox.js`: v12 → v13
- `conversation.js`: v11 → v12
- `filter-state.js`: v8 → v9
- `i18n.js`: v13 → v14 (already done in Task 8)

- [ ] **Step 2: Commit**

```bash
git add ChatBotAI/templates/chatbot/base.html
git commit -m "chore: bump cache versions for escalation feature"
```

---

### Task 10: Manual Integration Test

- [ ] **Step 1: Start the dev server and verify migration**

```bash
cd /c/Users/admin/Documents/FlaskApp && python -m ChatBotAI.run
```

- [ ] **Step 2: Test escalation detection**

Create a test conversation, add a knowledge base entry with category "escalation", then send a guest message that triggers it. Verify:
- AI response contains escalation phrase
- Conversation gets `escalated=True`, `auto_respond=False`
- Inbox shows orange styling + "Braucht Aufmerksamkeit" label
- AI badge shows grey (paused) state

- [ ] **Step 3: Test resolve flow**

Click into the escalated conversation. Verify:
- Escalation banner is visible at top
- "Resolve" button is visible in header
- Click resolve → banner disappears, card returns to normal in inbox
- `auto_respond` stays False (independent)

- [ ] **Step 4: Test escalated filter**

In inbox, click "Eskaliert" filter button. Verify only escalated conversations are shown.
