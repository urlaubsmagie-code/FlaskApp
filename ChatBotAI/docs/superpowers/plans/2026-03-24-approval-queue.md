# Approval Queue Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI responses are saved as pending drafts that the host must approve before they are sent to guests.

**Architecture:** Add `approval_status` column to Message model, `auto_approve` column to Conversation. Intercept `_generate_ai_response()` to conditionally save as pending instead of sending. New API endpoints for approve/reject. Conversation UI shows pending drafts with action buttons. Inbox shows badge and filter.

**Tech Stack:** Flask, SQLAlchemy, Alembic (SQLite), Jinja2, vanilla JS, CSS

**Spec:** `docs/superpowers/specs/2026-03-24-approval-queue-design.md`

---

### Task 1: Database Migration

**Files:**
- Create: `migrations/versions/p10_approval_add_approval_columns.py`
- Modify: `models.py:321-363` (Message class)
- Modify: `models.py:187-240` (Conversation class)

- [ ] **Step 1: Create migration file**

```python
"""Add approval queue columns to message and conversation

Revision ID: p10_approval
Revises: p9_summary
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'p10_approval'
down_revision = 'p9_summary'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approval_status', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('original_content', sa.Text(), nullable=True))
        batch_op.create_index(op.f('ix_message_approval_status'), ['approval_status'])

    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_approve', sa.Boolean(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_column('auto_approve')

    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_message_approval_status'))
        batch_op.drop_column('original_content')
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approval_status')
```

- [ ] **Step 2: Add columns to Message model in models.py**

In the Message class (around line 339, after `is_processed`), add:

```python
    approval_status = db.Column(db.String(20), nullable=True, index=True)  # NULL, 'pending', 'approved', 'rejected'
    approved_at = db.Column(db.DateTime, nullable=True)
    original_content = db.Column(db.Text, nullable=True)  # Deferred: populated by future "Learn from Corrections" feature (#8)
```

- [ ] **Step 3: Add column to Conversation model in models.py**

In the Conversation class (around line 222, after `escalated_at`), add:

```python
    auto_approve = db.Column(db.Boolean, default=False, nullable=False)
```

- [ ] **Step 4: Update Message.to_dict() in models.py**

In `to_dict()` (around line 352-363), add the three new fields to the returned dict:

```python
    'approval_status': self.approval_status,
    'approved_at': self.approved_at.isoformat() if self.approved_at else None,
    'original_content': self.original_content,
```

- [ ] **Step 5: Update Conversation.to_dict() in models.py**

In `Conversation.to_dict()` (around line 249-278), add:

```python
    'auto_approve': self.auto_approve,
```

- [ ] **Step 6: Add default settings in _populate_default_settings()**

In `_populate_default_settings()` (around line 640-650), add to the defaults list:

```python
    ('approval_queue_enabled', 'true', 'AI responses require host approval before sending'),
    ('auto_approve_new_conversations', 'false', 'New conversations auto-approve AI responses (skip queue)'),
```

- [ ] **Step 7: Run migration**

```bash
cd C:/Users/admin/Documents/FlaskApp && python -m ChatBotAI.run db upgrade
```

- [ ] **Step 8: Commit**

```bash
git add migrations/versions/p10_approval_add_approval_columns.py models.py
git commit -m "feat(approval): add approval_status columns and migration p10"
```

---

### Task 2: Message Router — Pending Draft Logic

**Files:**
- Modify: `services/message_router.py:333-370` (_find_or_create_conversation)
- Modify: `services/message_router.py:423-637` (_generate_ai_response)

- [ ] **Step 1: Update _find_or_create_conversation() to set auto_approve for new conversations**

Around line 349 where `auto_respond_default` is read, add similar logic:

```python
auto_approve_default = AISettings.get('auto_approve_new_conversations', 'false') == 'true'
```

And in the Conversation creation (around line 350-360), add:

```python
auto_approve=auto_approve_default,
```

- [ ] **Step 2: Update _generate_ai_response() to handle pending drafts**

In `_generate_ai_response()`, after the AI message is created and committed (around lines 561-570), replace the platform-send section (lines 572-609) with conditional logic:

```python
# Check if this should be a pending draft
approval_queue_enabled = AISettings.get('approval_queue_enabled', 'true') == 'true'

if approval_queue_enabled and not conversation.auto_approve:
    # Save as pending draft — do NOT send
    ai_message.approval_status = 'pending'
    db.session.commit()
    logger.info(f"AI response saved as pending draft (message_id={ai_message.id})")
    return {
        'content': response_text,
        'message_id': ai_message.id,
        'approval_status': 'pending'
    }
else:
    # Auto-approve path: send immediately (existing behavior)
    # ... existing platform send code stays here ...
```

Keep the existing Smoobu/Gmail send logic in the `else` branch.

Also update the conversation history query in `_generate_ai_response()` (around line 496-498 where messages are loaded for AI context) to exclude pending/rejected drafts:

```python
.filter(db.or_(Message.approval_status.is_(None), Message.approval_status == 'approved'))
```

- [ ] **Step 3: Delete existing pending draft before generating new one**

At the beginning of `_generate_ai_response()` (after the acknowledgment skip check), add:

```python
# Delete any existing pending draft for this conversation
from models import Message
existing_pending = Message.query.filter_by(
    conversation_id=conversation.id,
    approval_status='pending'
).first()
if existing_pending:
    db.session.delete(existing_pending)
    db.session.commit()
    logger.info(f"Replaced existing pending draft (message_id={existing_pending.id})")
```

- [ ] **Step 4: Update process_incoming_message() return dict**

In `process_incoming_message()` (around lines 159-170), after `_generate_ai_response()` returns, check if the response is pending and set `ai_response=None` in the return dict so external callers (Smoobu webhook, Gmail sync) don't treat it as sent:

```python
ai_result = self._generate_ai_response(conversation, ...)
if ai_result and ai_result.get('approval_status') == 'pending':
    result['ai_response'] = None
    result['ai_response_id'] = None
    result['pending_approval'] = True
else:
    result['ai_response'] = ai_result.get('content') if ai_result else None
    result['ai_response_id'] = ai_result.get('message_id') if ai_result else None
```

- [ ] **Step 5: Commit**

```bash
git add services/message_router.py
git commit -m "feat(approval): add pending draft logic to message router"
```

---

### Task 3: API Endpoints — Approve, Reject, Toggle

**Files:**
- Modify: `routes.py` (add new endpoints after escalation resolve ~line 1397)
- Modify: `routes.py:591-753` (api_generate_ai_response)
- Modify: `routes.py:343-370` (api_get_conversations)
- Modify: `routes.py:444-487` (api_get_messages)

- [ ] **Step 1: Add approve endpoint**

After the escalation resolve endpoint (~line 1397), add:

```python
@chatbot_bp.route('/api/messages/<int:message_id>/approve', methods=['POST'])
def api_approve_message(message_id):
    """Approve a pending AI draft and send it via platform."""
    message = Message.query.get_or_404(message_id)

    if message.approval_status != 'pending':
        return jsonify({'error': 'Message is not pending approval'}), 400

    conversation = Conversation.query.get(message.conversation_id)

    # Mark as approved
    message.approval_status = 'approved'
    message.approved_at = datetime.utcnow()
    db.session.commit()

    # Send via platform (same logic as api_generate_ai_response, routes.py ~line 700-743)
    email_sent = False
    smoobu_sent = False

    if conversation.platform == 'email' and conversation.guest:
        try:
            from .services.gmail_service import get_gmail_service
            gmail = get_gmail_service()
            if gmail and gmail.is_authenticated() and conversation.guest.email:
                # Find latest guest message for reply_to_message_id
                latest_guest_msg = Message.query.filter_by(
                    conversation_id=conversation.id,
                    sender_type='guest'
                ).order_by(Message.sent_at.desc()).first()

                send_result = gmail.send_email(
                    to=conversation.guest.email,
                    subject=conversation.subject or 'Re: Your inquiry',
                    body=message.content,
                    thread_id=conversation.platform_id,
                    reply_to_message_id=latest_guest_msg.platform_message_id if latest_guest_msg and latest_guest_msg.platform_message_id else None
                )
                email_sent = bool(send_result)
        except Exception as e:
            logger.warning(f"Failed to send approved message via Gmail: {e}")

    elif conversation.platform == 'smoobu' and conversation.smoobu_reservation_id:
        try:
            from .services.smoobu_service import get_smoobu_service
            smoobu = get_smoobu_service()
            if smoobu and smoobu.is_configured():
                send_result = smoobu.send_message(conversation.smoobu_reservation_id, message.content)
                smoobu_sent = bool(send_result)
                # Set platform_message_id to prevent duplicate on next sync
                if smoobu_sent and isinstance(send_result, dict):
                    smoobu_msg_id = str(send_result.get('id') or send_result.get('message_id')
                                       or send_result.get('messageId') or '')
                    if smoobu_msg_id:
                        message.platform_message_id = (
                            f"smoobu-{conversation.smoobu_reservation_id}-{smoobu_msg_id}")
                        db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to send approved message via Smoobu: {e}")

    return jsonify({
        'success': True,
        'email_sent': email_sent,
        'smoobu_sent': smoobu_sent,
        'message': message.to_dict()
    })
```

- [ ] **Step 2: Add reject endpoint**

```python
@chatbot_bp.route('/api/messages/<int:message_id>/reject', methods=['POST'])
def api_reject_message(message_id):
    """Reject a pending AI draft."""
    message = Message.query.get_or_404(message_id)

    if message.approval_status != 'pending':
        return jsonify({'error': 'Message is not pending approval'}), 400

    message.approval_status = 'rejected'
    db.session.commit()

    return jsonify({'success': True})
```

- [ ] **Step 3: Add toggle-auto-approve endpoint**

```python
@chatbot_bp.route('/api/conversations/<int:conv_id>/toggle-auto-approve', methods=['POST'])
def api_toggle_auto_approve(conv_id):
    """Toggle auto-approve for a conversation."""
    conversation = Conversation.query.get_or_404(conv_id)
    conversation.auto_approve = not conversation.auto_approve
    db.session.commit()

    return jsonify({'auto_approve': conversation.auto_approve})
```

- [ ] **Step 4: Add bulk auto-approve endpoint**

```python
@chatbot_bp.route('/api/settings/bulk-auto-approve', methods=['POST'])
def api_bulk_auto_approve():
    """Enable/disable auto-approve for all active conversations."""
    data = request.get_json()
    enabled = data.get('enabled', False)

    updated = Conversation.query.filter(
        Conversation.status != 'closed'
    ).update({Conversation.auto_approve: enabled})
    db.session.commit()

    return jsonify({'success': True, 'updated_count': updated})
```

- [ ] **Step 5: Update api_get_conversations to include has_pending_approval**

In `api_get_conversations()` (around line 343-370), after building the conversation list, add a subquery or post-processing to flag conversations with pending drafts:

```python
# Get conversation IDs with pending approvals
pending_conv_ids = set(
    row[0] for row in db.session.query(Message.conversation_id)
    .filter(Message.approval_status == 'pending')
    .distinct()
    .all()
)

# In the response building loop, add:
conv_dict['has_pending_approval'] = conv.id in pending_conv_ids
```

Also add the "pending_approval" filter option:

```python
if status_filter == 'pending_approval':
    query = query.filter(Conversation.id.in_(
        db.session.query(Message.conversation_id)
        .filter(Message.approval_status == 'pending')
        .distinct()
    ))
```

- [ ] **Step 6: Update api_get_messages to filter out rejected messages**

In `api_get_messages()` (around line 444-487), add to the base query:

```python
.filter(db.or_(Message.approval_status.is_(None), Message.approval_status != 'rejected'))
```

This shows pending drafts (for the UI to render with special styling) but hides rejected ones.

- [ ] **Step 7: Update api_generate_ai_response to create pending draft**

In `api_generate_ai_response()` (around line 591-753):

**7a.** At the start (after conversation lookup), delete any existing pending draft:

```python
# Delete existing pending draft for this conversation
existing_pending = Message.query.filter_by(
    conversation_id=conversation_id,
    approval_status='pending'
).first()
if existing_pending:
    db.session.delete(existing_pending)
    db.session.commit()
```

**7b.** After AI message creation (around line 690-698), check if approval queue is enabled. **IMPORTANT:** The manual button ALWAYS creates a pending draft when the queue is enabled, regardless of `auto_approve`. Auto-approve only applies to the auto-respond flow in message_router.py.

```python
approval_queue_enabled = AISettings.get('approval_queue_enabled', 'true') == 'true'

if approval_queue_enabled:
    # Manual button always creates pending draft
    ai_message.approval_status = 'pending'
    db.session.commit()
    return jsonify({
        'success': True,
        'approval_status': 'pending',
        'message': ai_message.to_dict()
    })
else:
    # Queue disabled: send immediately (existing platform send logic)
    # ... existing Smoobu/Gmail send code (lines 701-743) stays here ...
```

**7c.** Also filter pending/rejected drafts from the conversation history query used for AI context (around line 660-670 where messages are loaded for the AI prompt). Add:

```python
.filter(db.or_(Message.approval_status.is_(None), Message.approval_status == 'approved'))
```

- [ ] **Step 8: Update preload_last_messages()**

In `preload_last_messages()` (around line 562-592 in models.py), update the subquery to filter:

```python
.filter(db.or_(Message.approval_status.is_(None), Message.approval_status == 'approved'))
```

This ensures the inbox shows the last "real" message, not a pending draft.

- [ ] **Step 9: Commit**

```bash
git add routes.py models.py
git commit -m "feat(approval): add approve/reject/toggle API endpoints and query filters"
```

---

### Task 4: Conversation UI — Pending Draft Display

**Files:**
- Modify: `templates/chatbot/conversation.html:116-139` (message rendering)
- Modify: `templates/chatbot/conversation.html:161-166` (AI buttons)
- Modify: `templates/chatbot/conversation.html:49-56` (toggle buttons)
- Modify: `static/js/conversation.js:467-517` (generateAIResponse)
- Modify: `static/js/conversation.js:665-709` (addMessageToUI)

- [ ] **Step 1: Rename "KI-Antwort senden" button**

In `conversation.html` (around line 164-166), change:

```html
<button class="btn btn-secondary" onclick="generateAIResponse()" id="generateAiBtn">
    <i class="fas fa-magic"></i> <span data-i18n="conversation.ai.create">KI-Antwort erstellen</span>
</button>
```

- [ ] **Step 2: Add auto-approve toggle to conversation header**

In `conversation.html` (around lines 49-56, after the auto-respond toggle), add:

```html
<button class="btn btn-sm" id="autoApproveToggle"
    onclick="toggleAutoApprove()"
    style="display:none;"
    title="Auto-Freigabe">
    <i class="fas fa-check-double"></i> <span data-i18n="conversation.autoApprove">Auto-Freigabe</span>
</button>
```

The visibility is controlled by JS: only shown when approval queue is enabled globally.

- [ ] **Step 3: Update addMessageToUI() in conversation.js for pending drafts**

In `addMessageToUI()` (around line 665-709), after creating the message div, add conditional styling:

```javascript
if (msg.approval_status === 'pending') {
    messageDiv.classList.add('pending-approval');
    // Add label
    const label = document.createElement('div');
    label.className = 'pending-approval-label';
    label.setAttribute('data-i18n', 'conversation.approval.waiting');
    label.textContent = t('conversation.approval.waiting', 'Wartet auf Freigabe');
    messageDiv.querySelector('.message-content').prepend(label);

    // Add action buttons
    const actions = document.createElement('div');
    actions.className = 'pending-approval-actions';
    actions.innerHTML = `
        <button class="btn btn-sm btn-success" onclick="approveMessage(${msg.id})">
            <i class="fas fa-check"></i> <span data-i18n="conversation.approval.send">${t('conversation.approval.send', 'Absenden')}</span>
        </button>
        <button class="btn btn-sm btn-secondary" onclick="editMessage(${msg.id})">
            <i class="fas fa-edit"></i> <span data-i18n="conversation.approval.edit">${t('conversation.approval.edit', 'Bearbeiten')}</span>
        </button>
        <button class="btn btn-sm btn-outline-danger" onclick="rejectMessage(${msg.id})">
            <i class="fas fa-times"></i> <span data-i18n="conversation.approval.reject">${t('conversation.approval.reject', 'Ablehnen')}</span>
        </button>
    `;
    messageDiv.querySelector('.message-content').appendChild(actions);
}
```

- [ ] **Step 4: Add approveMessage(), editMessage(), rejectMessage() functions to conversation.js**

After the `resolveEscalation()` function (around line 660), add:

```javascript
async function approveMessage(messageId) {
    try {
        const response = await fetch(`/chatbot/api/messages/${messageId}/approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await response.json();
        if (data.success) {
            // Remove pending styling, show as normal AI message
            const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
            if (msgEl) {
                msgEl.classList.remove('pending-approval');
                msgEl.querySelector('.pending-approval-label')?.remove();
                msgEl.querySelector('.pending-approval-actions')?.remove();
            }
            showNotification(t('conversation.approval.sent', 'Nachricht gesendet'), 'success');

            if (!data.email_sent && !data.smoobu_sent) {
                showNotification(t('conversation.approval.sendWarning', 'Nachricht genehmigt, aber Versand fehlgeschlagen'), 'warning');
            }
        }
    } catch (error) {
        showNotification(t('conversation.approval.error', 'Fehler beim Genehmigen'), 'error');
    }
}

async function editMessage(messageId) {
    // Get the message text and put it in the textarea
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
    const content = msgEl?.querySelector('.message-text')?.textContent || '';

    // Put text in textarea
    const textarea = document.getElementById('messageInput');
    if (textarea) {
        textarea.value = content;
        textarea.focus();
        autoResizeTextarea(textarea);
    }

    // Reject/delete the pending draft
    try {
        await fetch(`/chatbot/api/messages/${messageId}/reject`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        // Remove from UI
        msgEl?.remove();
    } catch (error) {
        console.error('Failed to remove pending draft:', error);
    }
}

async function rejectMessage(messageId) {
    try {
        const response = await fetch(`/chatbot/api/messages/${messageId}/reject`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await response.json();
        if (data.success) {
            // Remove from UI
            const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
            msgEl?.remove();
            showNotification(t('conversation.approval.rejected', 'Entwurf abgelehnt'), 'info');
        }
    } catch (error) {
        showNotification(t('conversation.approval.error', 'Fehler'), 'error');
    }
}
```

- [ ] **Step 5: Add toggleAutoApprove() function to conversation.js**

```javascript
async function toggleAutoApprove() {
    try {
        const response = await fetch(`/chatbot/api/conversations/${conversationId}/toggle-auto-approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await response.json();
        updateAutoApproveButton(data.auto_approve);
    } catch (error) {
        showNotification(t('conversation.approval.toggleError', 'Fehler'), 'error');
    }
}

function updateAutoApproveButton(isEnabled) {
    const btn = document.getElementById('autoApproveToggle');
    if (btn) {
        btn.classList.toggle('active', isEnabled);
        btn.title = isEnabled
            ? t('conversation.autoApprove.on', 'Auto-Freigabe: AN')
            : t('conversation.autoApprove.off', 'Auto-Freigabe: AUS');
    }
}
```

- [ ] **Step 6: Update generateAIResponse() in conversation.js**

In `generateAIResponse()` (around line 467-517), update to expect a pending draft response:

```javascript
// After the fetch response is received:
if (data.approval_status === 'pending') {
    showNotification(t('conversation.approval.created', 'KI-Entwurf erstellt — wartet auf Freigabe'), 'info');
}
```

Remove or update any "message sent successfully" notification that would be misleading for pending drafts.

Also update the `finally` block (around line 515) which restores the button text using the old i18n key `conversation.ai.generate` — change it to `conversation.ai.create` to match the renamed button.

- [ ] **Step 7: Show/hide auto-approve toggle based on global setting**

In the conversation page initialization (when conversation data is loaded), check the global approval_queue_enabled setting and show/hide the auto-approve toggle:

```javascript
// In the conversation load/init function:
if (data.approval_queue_enabled) {
    document.getElementById('autoApproveToggle').style.display = '';
    updateAutoApproveButton(data.auto_approve);
}
```

Pass `approval_queue_enabled` to the frontend by adding a `data-approval-queue` attribute to the conversation container div in `conversation.html`:

```html
<div id="conversationContainer"
    data-approval-queue="{{ 'true' if settings_dict.get('approval_queue_enabled', 'true') != 'false' else 'false' }}"
    data-auto-approve="{{ conversation.auto_approve|lower }}">
```

Then read it in JS:

```javascript
const container = document.getElementById('conversationContainer');
const approvalQueueEnabled = container?.dataset.approvalQueue === 'true';
const autoApprove = container?.dataset.autoApprove === 'true';
```

The route handler for the conversation page must pass `settings_dict` to the template (a dict of AISettings key-value pairs).

- [ ] **Step 8: Commit**

```bash
git add templates/chatbot/conversation.html static/js/conversation.js
git commit -m "feat(approval): add pending draft UI with approve/edit/reject buttons"
```

---

### Task 5: Inbox UI — Badge and Filter

**Files:**
- Modify: `static/js/inbox.js:43-97` (createConversationCard)
- Modify: `static/js/inbox.js:99-150` (updateConversationCard)
- Modify: `templates/chatbot/inbox.html:60-66` (filter group)

- [ ] **Step 1: Add "KI-Freigabe" filter option to inbox.html**

In the status filter group (around line 60-66), add a new filter button:

```html
<button class="filter-btn" data-filter="status" data-value="pending_approval" data-i18n="inbox.filter.pendingApproval">KI-Freigabe</button>
```

- [ ] **Step 2: Add pending approval badge to createConversationCard() in inbox.js**

In `createConversationCard()` (around lines 66-71, where escalation badge is created), add:

```javascript
if (conv.has_pending_approval) {
    const approvalBadge = document.createElement('span');
    approvalBadge.className = 'badge badge-approval';
    approvalBadge.setAttribute('data-i18n', 'inbox.badge.pendingApproval');
    approvalBadge.textContent = t('inbox.badge.pendingApproval', 'KI-Freigabe');
    metaDiv.appendChild(approvalBadge);
}
```

- [ ] **Step 3: Update updateConversationCard() in inbox.js**

In `updateConversationCard()` (around lines 99-150), add logic to update the approval badge:

```javascript
// Update pending approval badge
const existingApprovalBadge = card.querySelector('.badge-approval');
if (conv.has_pending_approval && !existingApprovalBadge) {
    const approvalBadge = document.createElement('span');
    approvalBadge.className = 'badge badge-approval';
    approvalBadge.setAttribute('data-i18n', 'inbox.badge.pendingApproval');
    approvalBadge.textContent = t('inbox.badge.pendingApproval', 'KI-Freigabe');
    card.querySelector('.conversation-meta')?.appendChild(approvalBadge);
} else if (!conv.has_pending_approval && existingApprovalBadge) {
    existingApprovalBadge.remove();
}
```

- [ ] **Step 4: Commit**

```bash
git add templates/chatbot/inbox.html static/js/inbox.js
git commit -m "feat(approval): add KI-Freigabe badge and filter to inbox"
```

---

### Task 6: Settings UI

**Files:**
- Modify: `templates/chatbot/settings.html` (add approval queue settings section)

- [ ] **Step 1: Add Approval Queue settings section**

In `settings.html`, after the auto-respond toggle (around line 44), add:

```html
<div class="setting-item">
    <div class="setting-info">
        <label for="approvalQueueEnabled" data-i18n="settings.ai.approvalQueue">KI-Freigabe</label>
        <p class="setting-description" data-i18n="settings.ai.approvalQueue.desc">KI-Antworten müssen vor dem Versand genehmigt werden</p>
    </div>
    <label class="toggle-switch">
        <input type="checkbox" id="approvalQueueEnabled" name="approval_queue_enabled"
            onchange="saveToggleSetting('approval_queue_enabled', this.checked)"
            {% if settings|selectattr('key', 'equalto', 'approval_queue_enabled')|map(attribute='value')|first != 'false' %}checked{% endif %}>
        <span class="toggle-slider"></span>
    </label>
</div>

<div class="setting-item">
    <div class="setting-info">
        <label for="autoApproveNew" data-i18n="settings.ai.autoApproveNew">Auto-Freigabe für neue Konversationen</label>
        <p class="setting-description" data-i18n="settings.ai.autoApproveNew.desc">Neue Konversationen starten mit aktivierter Auto-Freigabe (KI sendet sofort)</p>
    </div>
    <label class="toggle-switch">
        <input type="checkbox" id="autoApproveNew" name="auto_approve_new_conversations"
            onchange="saveToggleSetting('auto_approve_new_conversations', this.checked)"
            {% if settings|selectattr('key', 'equalto', 'auto_approve_new_conversations')|map(attribute='value')|first == 'true' %}checked{% endif %}>
        <span class="toggle-slider"></span>
    </label>
</div>

<div class="setting-item">
    <div class="setting-info">
        <label data-i18n="settings.ai.bulkAutoApprove">Auto-Freigabe für alle Chats</label>
        <p class="setting-description" data-i18n="settings.ai.bulkAutoApprove.desc">Auto-Freigabe für alle aktiven Konversationen ein- oder ausschalten</p>
    </div>
    <div class="button-group">
        <button class="btn btn-sm btn-success" onclick="bulkAutoApprove(true)" data-i18n="settings.ai.bulkAutoApprove.enable">Für alle aktivieren</button>
        <button class="btn btn-sm btn-danger" onclick="bulkAutoApprove(false)" data-i18n="settings.ai.bulkAutoApprove.disable">Für alle deaktivieren</button>
    </div>
</div>
```

- [ ] **Step 2: Add bulkAutoApprove() JS function**

In the settings page `<script>` section (or in a referenced JS file), add:

```javascript
async function bulkAutoApprove(enabled) {
    try {
        const response = await fetch('/chatbot/api/settings/bulk-auto-approve', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({enabled: enabled})
        });
        const data = await response.json();
        if (data.success) {
            showNotification(
                `Auto-Freigabe für ${data.updated_count} Konversationen ${enabled ? 'aktiviert' : 'deaktiviert'}`,
                'success'
            );
        }
    } catch (error) {
        showNotification('Fehler beim Aktualisieren', 'error');
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add templates/chatbot/settings.html
git commit -m "feat(approval): add approval queue settings UI"
```

---

### Task 7: CSS Styling

**Files:**
- Modify: `static/css/style.css` (add pending approval styles after escalation styles ~line 3063)

- [ ] **Step 1: Add pending approval message styling**

After the escalation styling (around line 3063), add:

```css
/* Pending Approval */
.message.pending-approval .message-content-box {
    background: var(--pending-approval-bg, #fff3cd);
    border: 2px solid var(--pending-approval-border, #ffc107);
    border-radius: 12px;
}

:root[data-theme="dark"] .message.pending-approval .message-content-box {
    --pending-approval-bg: #3d2e00;
    --pending-approval-border: #ffc107;
}

.pending-approval-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--pending-approval-label, #856404);
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

:root[data-theme="dark"] .pending-approval-label {
    color: #ffc107;
}

.pending-approval-actions {
    display: flex;
    gap: 8px;
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid var(--pending-approval-border, #ffc107);
    flex-wrap: wrap;
}

.pending-approval-actions .btn {
    font-size: 0.8rem;
    padding: 4px 12px;
}
```

- [ ] **Step 2: Add inbox approval badge styling**

```css
.badge-approval {
    background-color: #ffc107;
    color: #212529;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 12px;
    font-weight: 600;
}
```

- [ ] **Step 3: Add auto-approve toggle active state**

```css
#autoApproveToggle.active {
    background-color: var(--success-color, #28a745);
    color: white;
}
```

- [ ] **Step 4: Commit**

```bash
git add static/css/style.css
git commit -m "feat(approval): add pending approval CSS styling"
```

---

### Task 8: Translations (i18n)

**Files:**
- Modify: `static/js/i18n.js` (German ~line 50-62, English ~line 426-438)

- [ ] **Step 1: Add German translations**

In the `de` section (around line 62, after conversation.ai entries), add:

```javascript
'conversation.approval.waiting': 'Wartet auf Freigabe',
'conversation.approval.send': 'Absenden',
'conversation.approval.edit': 'Bearbeiten',
'conversation.approval.reject': 'Ablehnen',
'conversation.approval.sent': 'Nachricht gesendet',
'conversation.approval.sendWarning': 'Genehmigt, aber Versand fehlgeschlagen',
'conversation.approval.rejected': 'Entwurf abgelehnt',
'conversation.approval.created': 'KI-Entwurf erstellt — wartet auf Freigabe',
'conversation.approval.error': 'Fehler beim Verarbeiten',
'conversation.approval.toggleError': 'Fehler beim Umschalten',
'conversation.autoApprove': 'Auto-Freigabe',
'conversation.autoApprove.on': 'Auto-Freigabe: AN',
'conversation.autoApprove.off': 'Auto-Freigabe: AUS',
'conversation.ai.create': 'KI-Antwort erstellen',
'inbox.badge.pendingApproval': 'KI-Freigabe',
'inbox.filter.pendingApproval': 'KI-Freigabe',
'settings.ai.approvalQueue': 'KI-Freigabe',
'settings.ai.approvalQueue.desc': 'KI-Antworten müssen vor dem Versand genehmigt werden',
'settings.ai.autoApproveNew': 'Auto-Freigabe für neue Konversationen',
'settings.ai.autoApproveNew.desc': 'Neue Konversationen starten mit Auto-Freigabe',
'settings.ai.bulkAutoApprove': 'Auto-Freigabe für alle Chats',
'settings.ai.bulkAutoApprove.desc': 'Auto-Freigabe für alle aktiven Konversationen',
'settings.ai.bulkAutoApprove.enable': 'Für alle aktivieren',
'settings.ai.bulkAutoApprove.disable': 'Für alle deaktivieren',
```

- [ ] **Step 2: Add English translations**

In the `en` section (around line 438, after conversation.ai entries), add equivalent English translations:

```javascript
'conversation.approval.waiting': 'Waiting for approval',
'conversation.approval.send': 'Send',
'conversation.approval.edit': 'Edit',
'conversation.approval.reject': 'Reject',
'conversation.approval.sent': 'Message sent',
'conversation.approval.sendWarning': 'Approved, but sending failed',
'conversation.approval.rejected': 'Draft rejected',
'conversation.approval.created': 'AI draft created — waiting for approval',
'conversation.approval.error': 'Error processing',
'conversation.approval.toggleError': 'Toggle error',
'conversation.autoApprove': 'Auto-approve',
'conversation.autoApprove.on': 'Auto-approve: ON',
'conversation.autoApprove.off': 'Auto-approve: OFF',
'conversation.ai.create': 'Create AI response',
'inbox.badge.pendingApproval': 'AI Approval',
'inbox.filter.pendingApproval': 'AI Approval',
'settings.ai.approvalQueue': 'AI Approval',
'settings.ai.approvalQueue.desc': 'AI responses must be approved before sending',
'settings.ai.autoApproveNew': 'Auto-approve for new conversations',
'settings.ai.autoApproveNew.desc': 'New conversations start with auto-approve enabled',
'settings.ai.bulkAutoApprove': 'Auto-approve for all chats',
'settings.ai.bulkAutoApprove.desc': 'Toggle auto-approve for all active conversations',
'settings.ai.bulkAutoApprove.enable': 'Enable for all',
'settings.ai.bulkAutoApprove.disable': 'Disable for all',
```

- [ ] **Step 3: Commit**

```bash
git add static/js/i18n.js
git commit -m "feat(approval): add German and English translations"
```

---

### Task 9: Edge Cases and Conversation Close Handling

**Files:**
- Modify: `routes.py` (close conversation endpoint)
- Modify: `services/message_router.py` (if conversation close logic exists there)

- [ ] **Step 1: Find and update the close conversation logic**

Find the endpoint that closes a conversation (sets `status='closed'`). Add logic to auto-reject any pending drafts when a conversation is closed:

```python
# When closing a conversation:
pending_messages = Message.query.filter_by(
    conversation_id=conv_id,
    approval_status='pending'
).all()
for msg in pending_messages:
    msg.approval_status = 'rejected'
db.session.commit()
```

- [ ] **Step 2: Commit**

```bash
git add routes.py
git commit -m "feat(approval): auto-reject pending drafts when conversation is closed"
```

---

### Task 10: Cache Version Bumps and Manual Testing

**Files:**
- Modify: `templates/chatbot/base.html` or wherever CSS/JS cache versions are set

- [ ] **Step 1: Bump cache versions**

Update cache version strings for all modified static files:
- `style.css` → v16
- `i18n.js` → v15
- `conversation.js` → v13
- `inbox.js` → v14

- [ ] **Step 2: Manual testing checklist**

Test the following scenarios:

1. **Pending draft creation**: Enable approval queue in settings. Send a test guest message. Verify AI response appears as pending draft with yellow/orange styling and action buttons.
2. **Approve**: Click "Absenden" on a pending draft. Verify it changes to a normal AI message and is sent via platform.
3. **Edit**: Click "Bearbeiten" on a pending draft. Verify text moves to textarea, draft disappears, and you can edit and send as owner message.
4. **Reject**: Click "Ablehnen" on a pending draft. Verify it disappears from conversation.
5. **Auto-approve**: Enable auto-approve on a conversation. Send a guest message. Verify AI response sends immediately (no pending state).
6. **Replace draft**: With a pending draft visible, send another guest message. Verify old draft is replaced with new one.
7. **Inbox badge**: Verify "KI-Freigabe" badge appears on conversations with pending drafts.
8. **Inbox filter**: Click "KI-Freigabe" filter. Verify only conversations with pending drafts are shown.
9. **Settings**: Test all three settings toggles (master, auto-approve new, bulk).
10. **Close conversation**: Close a conversation with a pending draft. Verify draft is auto-rejected.
11. **Dark mode**: Verify pending draft styling looks correct in dark mode.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(approval): bump cache versions for approval queue feature"
```
