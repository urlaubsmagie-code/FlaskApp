# Read Cursor & Improved Unread Tracking Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the boolean `is_read` flag with a message-ID-based read cursor (`last_read_message_id`) so unread detection is precise, and add `last_synced_message_at` to skip old messages during Smoobu sync.

**Architecture:** Add two columns to `Conversation`: `last_read_message_id` (FK → message.id) as the read cursor, and `last_synced_message_at` (DateTime) for sync optimization. Keep `is_read` as a fast denormalized boolean derived from the cursor. Frontend mark-read calls send the latest message ID; backend updates the cursor and recomputes `is_read`. Smoobu sync uses `last_synced_message_at` to skip already-imported messages.

**Tech Stack:** Flask, SQLAlchemy, SQLite (WAL mode), Flask-Migrate (Alembic), vanilla JS frontend

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `models.py` | Modify (lines 187-279) | Add `last_read_message_id`, `last_synced_message_at` columns; add `unread_count` property |
| `migrations/versions/p7_readcursor_*.py` | Create | Alembic migration for new columns |
| `services/message_router.py` | Modify (lines 327-403) | Update `_find_or_create_conversation` and `_store_message` to maintain `last_synced_message_at`; stop blindly setting `is_read=False` on duplicates |
| `services/smoobu_service.py` | Modify (lines 283-566, 568-726) | Use `last_synced_message_at` to skip old messages in both sync methods |
| `routes.py` | Modify (lines 484-500, 328-338) | Update mark-read endpoints to accept/set `last_read_message_id`; update heartbeat to use cursor |
| `static/js/conversation.js` | Modify (lines 833-839) | Send `last_message_id` when marking read |
| `static/js/inbox.js` | Modify (line 571) | Update mark-all-read to use new response format |
| `utils/search.py` | Modify (lines 113, 135) | Keep `is_read` usage (no change needed — derived field still works) |

---

### Task 1: Database Migration — Add Read Cursor Columns

**Files:**
- Create: `migrations/versions/p7_readcursor_add_read_cursor_columns.py`
- Modify: `models.py:187-227`

- [ ] **Step 1: Add columns to Conversation model**

In `models.py`, after line 212 (`is_read` column), add:

```python
# Read cursor: points to the last message the user has seen
last_read_message_id = db.Column(db.Integer, db.ForeignKey('message.id', ondelete='SET NULL', use_alter=True), nullable=True)

# Sync watermark: timestamp of the newest synced message (for skipping old messages during platform sync)
last_synced_message_at = db.Column(db.DateTime, nullable=True)
```

Note: `use_alter=True` is needed because Message has an FK back to Conversation (circular dependency). `ondelete='SET NULL'` prevents issues if a message is ever deleted.

- [ ] **Step 2: Add `unread_count` property to Conversation model**

After the existing `message_count` property (line 278), add:

```python
@property
def unread_count(self):
    """Count guest messages newer than the read cursor."""
    query = self.messages.filter(Message.sender_type == 'guest')
    if self.last_read_message_id:
        query = query.filter(Message.id > self.last_read_message_id)
    return query.count()
```

- [ ] **Step 3: Add `recompute_is_read` helper method**

After the `unread_count` property, add:

```python
def recompute_is_read(self):
    """Recompute is_read from the read cursor. Returns True if state changed."""
    has_unread = self.messages.filter(
        Message.sender_type == 'guest',
        Message.id > (self.last_read_message_id or 0)
    ).first() is not None
    new_is_read = not has_unread
    if self.is_read != new_is_read:
        self.is_read = new_is_read
        return True
    return False
```

This is used by the mark-read endpoint (Task 3) to safely derive `is_read` from the cursor position, handling race conditions where a new guest message arrives between page load and mark-read.

- [ ] **Step 4: Update `to_dict()` to include `unread_count`**

In `to_dict()` (line 247), after `'is_read': self.is_read,` add:

```python
'unread_count': self.unread_count,
'last_read_message_id': self.last_read_message_id,
```

- [ ] **Step 5: Create the Alembic migration**

Create `migrations/versions/p7_readcursor_add_read_cursor_columns.py`:

```python
"""Add read cursor and sync watermark columns to conversation

Revision ID: p7_readcursor
Revises: p6_knowledge
Create Date: 2026-03-23
"""
from alembic import op
import sqlalchemy as sa

revision = 'p7_readcursor'
down_revision = 'p6_knowledge'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_read_message_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_synced_message_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            op.f('fk_conversation_last_read_message_id_message'),
            'message', ['last_read_message_id'], ['id'],
            ondelete='SET NULL'
        )

    # Backfill: for conversations marked as read, set cursor to their latest message
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE conversation
        SET last_read_message_id = (
            SELECT MAX(m.id) FROM message m WHERE m.conversation_id = conversation.id
        )
        WHERE is_read = 1
    """))
    # Backfill: set last_synced_message_at to the latest message sent_at per conversation
    conn.execute(sa.text("""
        UPDATE conversation
        SET last_synced_message_at = (
            SELECT MAX(m.sent_at) FROM message m WHERE m.conversation_id = conversation.id
        )
    """))


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_conversation_last_read_message_id_message'), type_='foreignkey')
        batch_op.drop_column('last_synced_message_at')
        batch_op.drop_column('last_read_message_id')
```

Note: The backfill SQL is included directly in the `upgrade()` function above, so it runs automatically with the migration.

- [ ] **Step 6: Run migration**

```bash
cd C:\Users\admin\Documents\FlaskApp && python -m ChatBotAI.run db upgrade
```

Or if using Flask-Migrate CLI:
```bash
flask db upgrade
```

- [ ] **Step 7: Commit**

```bash
git add models.py migrations/versions/p7_readcursor_add_read_cursor_columns.py
git commit -m "feat: add last_read_message_id and last_synced_message_at to Conversation model"
```

---

### Task 2: Update MessageRouter — Maintain Cursor on New Messages

**Files:**
- Modify: `services/message_router.py:327-403`

- [ ] **Step 1: Fix `_find_or_create_conversation` — only mark unread for genuinely new messages**

Currently (line 363), `is_read = False` is set every time a conversation is found, even before we know if the message is a duplicate. Move the unread logic out of this method.

In `_find_or_create_conversation` (line 358-364), replace:

```python
        else:
            # Update conversation
            if subject and not conversation.subject:
                conversation.subject = subject
            conversation.updated_at = datetime.utcnow()
            conversation.is_read = False
            db.session.commit()
```

with:

```python
        else:
            # Update conversation metadata (unread state set later after dedup check)
            if subject and not conversation.subject:
                conversation.subject = subject
            db.session.commit()
```

- [ ] **Step 2: Update `process_incoming_message` — set unread after confirming message is new**

In `process_incoming_message`, after the `is_new` check (after line 126 `logger.info(f"Message stored: {message.id}")`), add the unread + timestamp updates. Replace lines 128-131:

```python
            # Step 4: Update conversation and guest timestamps
            conversation.updated_at = message.sent_at or datetime.utcnow()
            guest.last_contact = datetime.utcnow()
            db.session.commit()
```

with:

```python
            # Step 4: Update conversation timestamps and unread state
            conversation.updated_at = message.sent_at or datetime.utcnow()
            # Update sync watermark to the newest message timestamp
            msg_ts = message.sent_at or datetime.utcnow()
            if not conversation.last_synced_message_at or msg_ts > conversation.last_synced_message_at:
                conversation.last_synced_message_at = msg_ts
            # Mark unread: new guest message means is_read = False
            conversation.is_read = False
            guest.last_contact = datetime.utcnow()
            db.session.commit()
```

- [ ] **Step 3: Commit**

```bash
git add services/message_router.py
git commit -m "fix: only mark conversation unread after confirming message is new"
```

---

### Task 3: Update Mark-Read Endpoints — Use Read Cursor

**Files:**
- Modify: `routes.py:484-500, 328-338`

- [ ] **Step 1: Update single conversation mark-read endpoint**

Replace `api_mark_conversation_read` (routes.py lines 493-500):

```python
@chatbot_bp.route('/api/conversations/<int:conversation_id>/read', methods=['PATCH'])
def api_mark_conversation_read(conversation_id):
    """Mark a conversation as read by advancing the read cursor.

    Accepts optional JSON body: { "last_message_id": 123 }
    If not provided, uses the conversation's latest message ID.
    """
    conversation = Conversation.query.get_or_404(conversation_id)

    data = request.get_json(silent=True) or {}
    last_message_id = data.get('last_message_id')

    if not last_message_id:
        # Fall back to the latest message in the conversation
        latest = conversation.messages.order_by(Message.sent_at.desc()).first()
        last_message_id = latest.id if latest else None

    changed = False
    if last_message_id:
        # Only advance the cursor forward, never backward
        if not conversation.last_read_message_id or last_message_id > conversation.last_read_message_id:
            conversation.last_read_message_id = last_message_id
            changed = True

    # Derive is_read from cursor (handles race: new guest msg may have arrived since page load)
    if conversation.recompute_is_read():
        changed = True

    if changed:
        db.session.commit()

    return jsonify({'success': True, 'is_read': conversation.is_read, 'last_read_message_id': conversation.last_read_message_id})
```

- [ ] **Step 2: Update mark-all-read endpoint**

Replace `api_mark_all_read` (routes.py lines 484-490):

```python
@chatbot_bp.route('/api/conversations/mark-all-read', methods=['PATCH'])
def api_mark_all_read():
    """Mark all unread conversations as read — advances cursor to latest message for each."""
    from sqlalchemy import func

    unread_convs = Conversation.query.filter_by(is_read=False).all()
    if not unread_convs:
        return jsonify({'success': True, 'marked': 0})

    # Batch-fetch max message ID per conversation in a single query
    conv_ids = [c.id for c in unread_convs]
    max_ids = dict(db.session.query(
        Message.conversation_id, func.max(Message.id)
    ).filter(Message.conversation_id.in_(conv_ids)).group_by(Message.conversation_id).all())

    for conv in unread_convs:
        max_id = max_ids.get(conv.id)
        if max_id and (not conv.last_read_message_id or max_id > conv.last_read_message_id):
            conv.last_read_message_id = max_id
        conv.is_read = True

    db.session.commit()
    return jsonify({'success': True, 'marked': len(unread_convs)})
```

- [ ] **Step 3: Update heartbeat endpoint to include unread count**

In `api_conversations_last_updated` (routes.py lines 328-338), the current implementation already works because `is_read` is still maintained as a denormalized boolean. No change needed here — it will continue to work as-is.

- [ ] **Step 4: Commit**

```bash
git add routes.py
git commit -m "feat: update mark-read endpoints to use read cursor (last_read_message_id)"
```

---

### Task 4: Update Frontend — Send Last Message ID on Mark-Read

**Files:**
- Modify: `static/js/conversation.js:833-839`

- [ ] **Step 1: Update conversation.js mark-read call**

Replace the fire-and-forget mark-read (conversation.js lines 836-839):

```javascript
    fetch(`/chatbot/api/conversations/${conversationId}/read`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' }
    }).catch(err => console.error('Failed to mark as read:', err));
```

with:

```javascript
    // Mark read with the latest known message ID for precise cursor tracking
    fetch(`/chatbot/api/conversations/${conversationId}/read`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ last_message_id: maxKnownMessageId || null })
    }).catch(err => console.error('Failed to mark as read:', err));
```

- [ ] **Step 2: Also mark read when new messages arrive via polling**

In the `updateMessages` function (conversation.js ~line 712), after `scrollToBottom()`, add a re-mark-read so the cursor advances as new messages arrive while viewing:

```javascript
    if (hasNewMessages) {
        scrollToBottom();
        // Advance read cursor to include newly arrived messages
        fetch(`/chatbot/api/conversations/${conversationId}/read`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ last_message_id: maxKnownMessageId })
        }).catch(err => console.error('Failed to advance read cursor:', err));
    }
```

- [ ] **Step 3: Bump conversation.js cache version**

In `templates/chatbot/conversation.html`, bump the conversation.js version from v10 to v11:

Find: `conversation.js?v=10`
Replace: `conversation.js?v=11`

- [ ] **Step 4: Commit**

```bash
git add static/js/conversation.js templates/chatbot/conversation.html
git commit -m "feat: send last_message_id when marking conversations as read"
```

---

### Task 5: Optimize Smoobu Sync — Use `last_synced_message_at` Watermark

**Files:**
- Modify: `services/smoobu_service.py:283-566, 568-726`

- [ ] **Step 1: Add watermark check to full sync (`sync_messages`)**

In `sync_messages`, the per-message loop already has `existing_conv` (resolved at line 374 from `conv_by_platform_id`) and `conv_known_ids` (set at line 413-415). We add a watermark check using these existing variables to avoid any new DB queries.

After the timestamp parsing (line 437-439, `msg_time = _parse_smoobu_timestamp(...)`), and before the sender type determination (line 432), add an early skip using the already-available `existing_conv` and `conv_known_ids`:

```python
                    # Parse Smoobu timestamp (convert to UTC)
                    msg_time = _parse_smoobu_timestamp(
                        msg.get('created_at') or msg.get('createdAt') or msg.get('date')
                    )

                    # Skip messages older than our sync watermark (already imported)
                    # Uses existing_conv (resolved at line 374) and conv_known_ids (line 413)
                    if existing_conv and existing_conv.last_synced_message_at and msg_time:
                        if msg_time <= existing_conv.last_synced_message_at:
                            # Double-check with platform_message_id for boundary timestamps
                            if platform_msg_id and platform_msg_id in conv_known_ids:
                                continue  # Definitely already imported
```

Note: We do NOT skip purely on timestamp — we double-check with `platform_message_id` (from the already-loaded `conv_known_ids` set) if the message is at or before the watermark. This handles the edge case of messages with identical timestamps. No new DB query is needed.

- [ ] **Step 2: Update sync watermark after importing owner messages**

In `sync_messages`, after storing an owner message (around line 542-543), also update the sync watermark:

After line 542 (`conv.updated_at = owner_msg.sent_at`), add:

```python
                            if not conv.last_synced_message_at or owner_msg.sent_at > conv.last_synced_message_at:
                                conv.last_synced_message_at = owner_msg.sent_at
```

- [ ] **Step 3: Add watermark check to single conversation sync (`sync_conversation_messages`)**

Apply the same watermark logic to `sync_conversation_messages`. After parsing the message timestamp (around line 634), add the same early skip:

```python
                    # Skip messages older than sync watermark
                    if conv and conv.last_synced_message_at and msg_time:
                        if msg_time <= conv.last_synced_message_at:
                            if platform_msg_id and platform_msg_id in known_ids:
                                continue
```

And after storing owner messages in this method, update the watermark similarly.

- [ ] **Step 4: Commit**

```bash
git add services/smoobu_service.py
git commit -m "perf: use last_synced_message_at watermark to skip old messages during Smoobu sync"
```

---

### Task 6: Update `preload_last_messages` for Unread Count Efficiency

**Files:**
- Modify: `models.py:522-552`

- [ ] **Step 1: Extend preload to cache unread counts**

The current `preload_last_messages` function prevents N+1 queries for last messages. We should also preload unread counts to avoid N+1 when serializing conversations to JSON.

After the existing `preload_last_messages` function (around line 552), add:

```python
def preload_unread_counts(conversations):
    """Batch-load unread counts for a list of conversations.

    Sets _cached_unread_count on each conversation so that
    conversation.unread_count uses the cache instead of per-conversation queries.
    """
    if not conversations:
        return

    conv_ids = [c.id for c in conversations]

    # Count guest messages after each conversation's read cursor
    counts = {}
    for c in conversations:
        counts[c.id] = 0

    # Single query: count unread guest messages per conversation
    from sqlalchemy import func, and_, case
    rows = db.session.query(
        Message.conversation_id,
        func.count(Message.id)
    ).join(
        Conversation, Message.conversation_id == Conversation.id
    ).filter(
        Message.conversation_id.in_(conv_ids),
        Message.sender_type == 'guest'
    ).filter(
        db.or_(
            Conversation.last_read_message_id.is_(None),
            Message.id > Conversation.last_read_message_id
        )
    ).group_by(Message.conversation_id).all()

    for conv_id, count in rows:
        counts[conv_id] = count

    for c in conversations:
        c._cached_unread_count = counts.get(c.id, 0)
```

- [ ] **Step 2: Update `unread_count` property to use cache**

Update the `unread_count` property added in Task 1:

```python
@property
def unread_count(self):
    """Count guest messages newer than the read cursor."""
    if hasattr(self, '_cached_unread_count'):
        return self._cached_unread_count
    query = self.messages.filter(Message.sender_type == 'guest')
    if self.last_read_message_id:
        query = query.filter(Message.id > self.last_read_message_id)
    return query.count()
```

- [ ] **Step 3: Wire up preload in routes that serialize conversations**

In `routes.py`, wherever `preload_last_messages` is called, also call `preload_unread_counts`. There are 3 call sites:

1. Line 143: `preload_last_messages(conversations)` → add `preload_unread_counts(conversations)` after
2. Line 208: `preload_last_messages(conversations)` → add `preload_unread_counts(conversations)` after
3. Line 357: `preload_last_messages(pagination.items)` → add `preload_unread_counts(pagination.items)` after

Import at top of routes.py (line 18), add `preload_unread_counts`:
```python
from .models import db, User, Guest, GuestDetail, Conversation, Message, Property, AISettings, ReplyTemplate, KnowledgeEntry, preload_last_messages, preload_unread_counts
```

- [ ] **Step 4: Commit**

```bash
git add models.py routes.py
git commit -m "perf: batch-preload unread counts to avoid N+1 queries in inbox"
```

---

## Summary of Changes

| What | Before | After |
|------|--------|-------|
| Unread detection | Boolean `is_read` set blindly on conversation find | `last_read_message_id` cursor; `is_read` derived from cursor |
| Mark read | Sets `is_read = True` | Advances `last_read_message_id` to latest message; derives `is_read` |
| Unread count | `COUNT(*) WHERE is_read=False` (conversation-level) | `COUNT(messages WHERE id > cursor AND sender_type='guest')` (message-level) |
| Smoobu sync | Processes ALL messages every sync, relies on dedup | Skips messages older than `last_synced_message_at`, dedup as fallback |
| Frontend mark-read | Sends PATCH with no body | Sends `{ last_message_id: N }` for precise cursor |

## Migration Safety

- `last_read_message_id` and `last_synced_message_at` are nullable — existing rows get NULL safely
- Backfill sets cursor for already-read conversations to their latest message
- `is_read` boolean kept for backward compatibility — all existing queries continue working
- No breaking changes to API responses (new fields are additive)
