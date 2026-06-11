# Inbox Sort by Last Message — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sort the inbox by the real timestamp of each conversation's latest message (matching Smoobu's order), without breaking the polling tripwire that `Conversation.updated_at` currently provides.

**Architecture:** Add a new column `Conversation.last_message_at` that always mirrors `MAX(Message.sent_at)` for the conversation. Backfill from existing messages. Update every code path that creates/syncs a message to set `last_message_at = msg.sent_at`. Switch every inbox-style query from `order_by(updated_at.desc())` to `order_by(last_message_at.desc())`. Keep `updated_at` as the polling tripwire (so out-of-order sync still triggers a client refresh).

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate (Alembic), SQLite (WAL), pytest.

---

## File Structure

**Modify:**
- `ChatBotAI/models.py` — add `last_message_at` column on `Conversation`, include in `to_dict()`.
- `ChatBotAI/services/message_router.py` — set `last_message_at` on guest store (line ~156), owner store (~276), AI store (~712).
- `ChatBotAI/services/smoobu_service.py` — set `last_message_at` on synced owner messages (lines ~653 and ~887).
- `ChatBotAI/routes.py` — set `last_message_at` on manual owner sends (~948), AI sends (~1145); update sort sites (~255, ~332, ~681, ~2539); update the fix-timestamps route (~3660).
- `ChatBotAI/utils/search.py:126` — change `ORDER BY c.updated_at DESC` to `ORDER BY c.last_message_at DESC`.
- `ChatBotAI/tools/profile_pages.py:85` — same.

**Create:**
- `ChatBotAI/migrations/versions/p15_last_message_at_add_column.py` — schema migration + backfill.
- `ChatBotAI/tests/test_inbox_sort_by_last_message.py` — regression tests.

**Out of scope:** removing `Conversation.updated_at`. It stays as the polling tripwire. Removing it is a separate cleanup if/when polling is rewired.

---

## Task 1: Add `last_message_at` column to the `Conversation` model

**Files:**
- Modify: `ChatBotAI/models.py:266-269` (Timestamps block on `Conversation`)

- [ ] **Step 1: Add column declaration**

In `ChatBotAI/models.py`, locate the Timestamps block on `Conversation`:

```python
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Only updated explicitly on message activity (not on read/toggle/assign changes)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
```

Replace with:

```python
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Polling tripwire: bumped whenever ANY change should refresh inbox clients
    # (new message, out-of-order sync, owner reply). Do NOT use for ordering.
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Sort key: timestamp of the most recent message in this conversation.
    # Mirrors MAX(Message.sent_at). Used for inbox ordering — matches Smoobu order.
    last_message_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
```

- [ ] **Step 2: Include `last_message_at` in `to_dict()`**

In `ChatBotAI/models.py`, in `Conversation.to_dict()`, add inside the `data = {...}` block (near `'updated_at'`):

```python
            'last_message_at': self.last_message_at.isoformat() if self.last_message_at else None,
```

- [ ] **Step 3: Commit**

```bash
git add ChatBotAI/models.py
git commit -m "feat(model): add Conversation.last_message_at column for inbox sort"
```

---

## Task 2: Migration — add column + backfill from MAX(message.sent_at)

**Files:**
- Create: `ChatBotAI/migrations/versions/p15_last_message_at_add_column.py`

- [ ] **Step 1: Write the migration file**

Create `ChatBotAI/migrations/versions/p15_last_message_at_add_column.py`:

```python
"""Add Conversation.last_message_at + backfill from MAX(message.sent_at).

Revision ID: p15_last_message_at
Revises: p14_uniq_platform_msg_id
Create Date: 2026-05-15

Inbox previously sorted by Conversation.updated_at, which gets bumped to
"now" for out-of-order synced messages and for any owner/AI reply. That
made our inbox order diverge from Smoobu's, which sorts by the real
message timestamp. This migration introduces a dedicated sort column
that always mirrors MAX(Message.sent_at). Backfill computes it from
existing messages; conversations with no messages fall back to
created_at.
"""
from alembic import op
import sqlalchemy as sa


revision = 'p15_last_message_at'
down_revision = 'p14_uniq_platform_msg_id'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Add the column (nullable initially so backfill can populate it).
    with op.batch_alter_table('conversation') as batch_op:
        batch_op.add_column(sa.Column('last_message_at', sa.DateTime(), nullable=True))

    # 2. Backfill: for each conversation, set last_message_at to the newest
    #    message's sent_at. Conversations with zero messages get created_at.
    conn.execute(sa.text("""
        UPDATE conversation
        SET last_message_at = COALESCE(
            (SELECT MAX(m.sent_at) FROM message m WHERE m.conversation_id = conversation.id),
            conversation.created_at,
            conversation.updated_at
        )
    """))

    # 3. Add index for inbox ORDER BY performance.
    op.create_index(
        'ix_conversation_last_message_at',
        'conversation',
        ['last_message_at'],
    )


def downgrade():
    op.drop_index('ix_conversation_last_message_at', table_name='conversation')
    with op.batch_alter_table('conversation') as batch_op:
        batch_op.drop_column('last_message_at')
```

- [ ] **Step 2: Run the migration**

Run from the FlaskApp root (where `app.py` lives):

```bash
cd C:/Users/admin/Documents/FlaskApp && python -m flask --app app db upgrade
```

Expected output: `INFO  [alembic.runtime.migration] Running upgrade p14_uniq_platform_msg_id -> p15_last_message_at`.

- [ ] **Step 3: Verify backfill with a sanity query**

```bash
cd C:/Users/admin/Documents/FlaskApp && python -c "from app import create_app; from ChatBotAI.models import db, Conversation, Message; from sqlalchemy import func; app=create_app(); ctx=app.app_context(); ctx.push(); rows=db.session.query(Conversation.id, Conversation.last_message_at, func.max(Message.sent_at)).outerjoin(Message, Message.conversation_id==Conversation.id).group_by(Conversation.id).limit(10).all(); [print(r) for r in rows]"
```

Expected: for every row, `last_message_at` equals `MAX(message.sent_at)` (or `NULL`/`created_at` if the conversation has no messages).

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/migrations/versions/p15_last_message_at_add_column.py
git commit -m "feat(migration): add last_message_at column with backfill from messages"
```

---

## Task 3: Write failing regression tests for inbox sort

**Files:**
- Create: `ChatBotAI/tests/test_inbox_sort_by_last_message.py`

- [ ] **Step 1: Inspect an existing test for the right fixtures/patterns**

Run:

```bash
ls C:/Users/admin/Documents/FlaskApp/ChatBotAI/tests/
```

Open one of the existing test files (e.g. `test_read_cursor.py` or any `test_*.py`) and reuse its `app` / `db` / `client` fixture pattern. If `conftest.py` exists in `tests/`, lean on its fixtures.

- [ ] **Step 2: Write the failing tests**

Create `ChatBotAI/tests/test_inbox_sort_by_last_message.py`:

```python
"""Inbox must order conversations by the real timestamp of the latest
message (Conversation.last_message_at), not by updated_at. This matches
Smoobu's inbox order even when messages arrive out-of-order via sync.
"""
from datetime import datetime, timedelta

import pytest

from ChatBotAI.models import db, Conversation, Guest, Message


def _make_conv(name, last_msg_sent_at, updated_at=None):
    guest = Guest(name=name, email=f"{name.lower()}@example.com")
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(
        guest_id=guest.id,
        platform='smoobu',
        platform_id=f"smoobu-test-{name}",
        last_message_at=last_msg_sent_at,
        updated_at=updated_at or last_msg_sent_at,
    )
    db.session.add(conv)
    db.session.flush()
    msg = Message(
        conversation_id=conv.id,
        sender_type='guest',
        content=f"hi from {name}",
        sent_at=last_msg_sent_at,
    )
    db.session.add(msg)
    db.session.commit()
    return conv


def test_inbox_orders_by_last_message_at_not_updated_at(app):
    """A conversation whose last real message is older must appear BELOW a
    conversation with a newer last message — even if its updated_at is newer
    (e.g. because of an out-of-order sync that bumped updated_at to now)."""
    with app.app_context():
        now = datetime.utcnow()
        # Older real message, but updated_at bumped to "now" (the bug we're fixing).
        old_conv = _make_conv(
            "Old", last_msg_sent_at=now - timedelta(days=3), updated_at=now
        )
        # Newer real message, normal updated_at.
        new_conv = _make_conv(
            "New",
            last_msg_sent_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        )

        ordered = (
            Conversation.query
            .order_by(Conversation.last_message_at.desc())
            .all()
        )
        ids = [c.id for c in ordered]
        assert ids.index(new_conv.id) < ids.index(old_conv.id), (
            "Conversation with the newer real message must come first; "
            "updated_at must not influence sort."
        )


def test_inbox_endpoint_sorts_by_last_message_at(client, app, login_as_admin):
    """The actual /chatbot/ inbox endpoint must return conversations sorted by
    last_message_at desc."""
    with app.app_context():
        now = datetime.utcnow()
        _make_conv("Alpha", last_msg_sent_at=now - timedelta(days=2), updated_at=now)
        _make_conv("Bravo", last_msg_sent_at=now - timedelta(minutes=5))
        _make_conv("Charlie", last_msg_sent_at=now - timedelta(hours=6))

    resp = client.get('/chatbot/api/conversations?page=1&per_page=10')
    assert resp.status_code == 200
    items = resp.get_json()['conversations']
    names = [c['guest']['name'] for c in items if c['guest']['name'] in {'Alpha', 'Bravo', 'Charlie'}]
    assert names == ['Bravo', 'Charlie', 'Alpha'], (
        f"Expected Bravo, Charlie, Alpha (newest last_message_at first); got {names}"
    )
```

> If the existing test suite does NOT have `client` / `login_as_admin` fixtures, replace the second test with a direct call: build the same query that `routes.py:681` builds and assert the order. Do not invent fixtures that don't exist.

- [ ] **Step 3: Run tests to verify they FAIL on the second test (sort site not yet changed)**

```bash
cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_inbox_sort_by_last_message.py -v
```

Expected: `test_inbox_orders_by_last_message_at_not_updated_at` PASSES (column exists from Task 1+2). `test_inbox_endpoint_sorts_by_last_message_at` FAILS because the inbox route still sorts by `updated_at`.

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/tests/test_inbox_sort_by_last_message.py
git commit -m "test(inbox): add failing regression test for sort by last_message_at"
```

---

## Task 4: Update guest-message write site in `message_router.py`

**Files:**
- Modify: `ChatBotAI/services/message_router.py:141-166`

- [ ] **Step 1: Set `last_message_at` to the real message timestamp**

In `ChatBotAI/services/message_router.py`, find:

```python
            # Always advance updated_at so the inbox poller's MAX(updated_at)
            # tripwire fires and clients refresh — even for out-of-order
            # deliveries. For forward-in-time messages we use msg_ts (truthful);
            # for out-of-order ones we use now() so the conversation still
            # surfaces in the inbox without lying about the message time.
            conversation.updated_at = msg_ts if is_forward else max(old_updated_at, now_ts)
```

Replace with:

```python
            # updated_at remains the polling tripwire — always bump it so
            # clients refresh, even for out-of-order deliveries.
            conversation.updated_at = msg_ts if is_forward else max(old_updated_at, now_ts)

            # last_message_at is the sort key — only advance it when this
            # message is genuinely the newest one we've seen for this
            # conversation. Out-of-order syncs MUST NOT push older threads
            # to the top of the inbox.
            if not conversation.last_message_at or msg_ts > conversation.last_message_at:
                conversation.last_message_at = msg_ts
```

- [ ] **Step 2: Commit**

```bash
git add ChatBotAI/services/message_router.py
git commit -m "feat(router): set Conversation.last_message_at on guest message store"
```

---

## Task 5: Update owner + AI write sites in `message_router.py`

**Files:**
- Modify: `ChatBotAI/services/message_router.py:276` (owner store)
- Modify: `ChatBotAI/services/message_router.py:712` (AI store)

- [ ] **Step 1: Owner store — set `last_message_at`**

In `services/message_router.py`, find:

```python
            # Update conversation timestamp
            conversation.updated_at = datetime.utcnow()
            db.session.commit()
```

Replace with:

```python
            # Update conversation timestamps. updated_at = tripwire, bumped
            # every time. last_message_at = sort key, set to this message's
            # real sent_at.
            now_ts = datetime.utcnow()
            conversation.updated_at = now_ts
            msg_sent_at = message.sent_at or now_ts
            if not conversation.last_message_at or msg_sent_at > conversation.last_message_at:
                conversation.last_message_at = msg_sent_at
            db.session.commit()
```

- [ ] **Step 2: AI store — set `last_message_at`**

In `services/message_router.py`, find:

```python
        db.session.add(ai_message)
        conversation.updated_at = datetime.utcnow()
        db.session.commit()
```

Replace with:

```python
        db.session.add(ai_message)
        now_ts = datetime.utcnow()
        conversation.updated_at = now_ts
        ai_sent_at = ai_message.sent_at or now_ts
        if not conversation.last_message_at or ai_sent_at > conversation.last_message_at:
            conversation.last_message_at = ai_sent_at
        db.session.commit()
```

- [ ] **Step 3: Commit**

```bash
git add ChatBotAI/services/message_router.py
git commit -m "feat(router): set last_message_at on owner and AI message stores"
```

---

## Task 6: Update Smoobu sync write sites

**Files:**
- Modify: `ChatBotAI/services/smoobu_service.py:651-653`
- Modify: `ChatBotAI/services/smoobu_service.py:885-887`

- [ ] **Step 1: First write site (~line 651)**

In `services/smoobu_service.py`, find:

```python
                                # Update conversation timestamp for inbox ordering
                                if not conv.updated_at or owner_msg.sent_at > conv.updated_at:
                                    conv.updated_at = owner_msg.sent_at
```

Replace with:

```python
                                # updated_at: polling tripwire — bump on any
                                # new owner message so clients refresh.
                                conv.updated_at = datetime.utcnow()
                                # last_message_at: sort key — only advance
                                # when this is genuinely the newest message.
                                if not conv.last_message_at or owner_msg.sent_at > conv.last_message_at:
                                    conv.last_message_at = owner_msg.sent_at
```

- [ ] **Step 2: Second write site (~line 885)**

In `services/smoobu_service.py`, find:

```python
                            # Update conversation timestamp for inbox ordering
                            if not conv.updated_at or owner_msg.sent_at > conv.updated_at:
                                conv.updated_at = owner_msg.sent_at
```

Replace with:

```python
                            # updated_at: polling tripwire — bump on any
                            # new owner message so clients refresh.
                            conv.updated_at = datetime.utcnow()
                            # last_message_at: sort key — only advance
                            # when this is genuinely the newest message.
                            if not conv.last_message_at or owner_msg.sent_at > conv.last_message_at:
                                conv.last_message_at = owner_msg.sent_at
```

- [ ] **Step 3: Verify `datetime` import is present**

Run:

```bash
grep -n "^from datetime\|^import datetime" C:/Users/admin/Documents/FlaskApp/ChatBotAI/services/smoobu_service.py
```

Expected: at least one match. If `datetime` isn't imported, add `from datetime import datetime` at the top of the file.

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/services/smoobu_service.py
git commit -m "feat(smoobu): set last_message_at on synced owner messages"
```

---

## Task 7: Update routes.py write sites

**Files:**
- Modify: `ChatBotAI/routes.py:948` (manual owner send)
- Modify: `ChatBotAI/routes.py:1145` (AI send)
- Modify: `ChatBotAI/routes.py:3660-3668` (timestamp-fix route)

- [ ] **Step 1: Manual owner send (~line 948)**

In `routes.py`, find:

```python
    db.session.add(message)
    conversation.updated_at = datetime.utcnow()
```

(Choose the occurrence near line 948, inside the owner-send handler — it sets `sender_type='owner'`, `sent_via_app=True`.) Replace with:

```python
    db.session.add(message)
    now_ts = datetime.utcnow()
    conversation.updated_at = now_ts
    msg_sent_at = message.sent_at or now_ts
    if not conversation.last_message_at or msg_sent_at > conversation.last_message_at:
        conversation.last_message_at = msg_sent_at
```

- [ ] **Step 2: AI send (~line 1145)**

In `routes.py`, find:

```python
        db.session.add(ai_message)
        conversation.updated_at = datetime.utcnow()
        db.session.commit()
```

(The occurrence creating `ai_message` with `sender_type='ai'`.) Replace with:

```python
        db.session.add(ai_message)
        now_ts = datetime.utcnow()
        conversation.updated_at = now_ts
        ai_sent_at = ai_message.sent_at or now_ts
        if not conversation.last_message_at or ai_sent_at > conversation.last_message_at:
            conversation.last_message_at = ai_sent_at
        db.session.commit()
```

- [ ] **Step 3: Timestamp-fix admin route (~line 3660)**

In `routes.py`, find:

```python
    # Also fix conversation.updated_at to match the latest message
    for conv in conversations:
        latest_msg = Message.query.filter_by(
            conversation_id=conv.id
        ).order_by(Message.sent_at.desc()).first()
        if latest_msg and latest_msg.sent_at:
            if not conv.updated_at or conv.updated_at != latest_msg.sent_at:
                conv.updated_at = latest_msg.sent_at
                fixed += 1
```

Replace with:

```python
    # Also fix conversation timestamps to match the latest message.
    # last_message_at is authoritative for sort; updated_at is the polling
    # tripwire and we align it to the latest message during a full fix.
    for conv in conversations:
        latest_msg = Message.query.filter_by(
            conversation_id=conv.id
        ).order_by(Message.sent_at.desc()).first()
        if latest_msg and latest_msg.sent_at:
            changed = False
            if not conv.last_message_at or conv.last_message_at != latest_msg.sent_at:
                conv.last_message_at = latest_msg.sent_at
                changed = True
            if not conv.updated_at or conv.updated_at != latest_msg.sent_at:
                conv.updated_at = latest_msg.sent_at
                changed = True
            if changed:
                fixed += 1
```

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/routes.py
git commit -m "feat(routes): set last_message_at on owner/AI sends and timestamp-fix"
```

---

## Task 8: Switch every inbox sort site to `last_message_at`

**Files:**
- Modify: `ChatBotAI/routes.py:255`
- Modify: `ChatBotAI/routes.py:332`
- Modify: `ChatBotAI/routes.py:681`
- Modify: `ChatBotAI/routes.py:2539`
- Modify: `ChatBotAI/utils/search.py:126`
- Modify: `ChatBotAI/tools/profile_pages.py:85`

- [ ] **Step 1: Replace `order_by(Conversation.updated_at.desc())` in routes.py**

Apply this change at lines 255, 332, 681, and 2539:

Old:
```python
.order_by(Conversation.updated_at.desc())
```

New:
```python
.order_by(Conversation.last_message_at.desc())
```

Each occurrence is in a different function — change each individually so you don't replace any unrelated `updated_at` ordering (search filters, audit pages, etc.). Verify after each edit that the surrounding code is the inbox/conversation list and NOT some other entity.

- [ ] **Step 2: Update raw SQL in `utils/search.py:126`**

Find:

```sql
        ORDER BY c.updated_at DESC
```

Replace with:

```sql
        ORDER BY c.last_message_at DESC
```

- [ ] **Step 3: Update `tools/profile_pages.py:85`**

Find:

```python
            .order_by(Conversation.updated_at.desc())
```

Replace with:

```python
            .order_by(Conversation.last_message_at.desc())
```

- [ ] **Step 4: Run the regression tests — both must PASS now**

```bash
cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_inbox_sort_by_last_message.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run the full test suite to catch any regressions**

```bash
cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/ -v
```

Expected: all tests pass. If any unrelated test fails because it asserts ordering by `updated_at`, fix the assertion (the contract has changed: inbox sorts by `last_message_at`).

- [ ] **Step 6: Commit**

```bash
git add ChatBotAI/routes.py ChatBotAI/utils/search.py ChatBotAI/tools/profile_pages.py
git commit -m "feat(inbox): sort by last_message_at (matches Smoobu order)"
```

---

## Task 9: Manual smoke test against the running app

**Files:** none

- [ ] **Step 1: Restart the server**

Stop the running Flask/Waitress process and re-launch via `start_server.bat` (or `python app.py` for dev). `services/smoobu_service.py` keeps an in-memory API-key cache, so a restart is required to pick up DB schema changes cleanly.

- [ ] **Step 2: Open the inbox and compare to Smoobu**

In a browser:
1. Open `https://umteamsbz.com/chatbot/` (or local equivalent).
2. Open Smoobu's inbox in another tab.
3. Compare the top 10–15 conversations. Order should match.

- [ ] **Step 3: Trigger an out-of-order sync to confirm the fix**

Pick a conversation whose newest real message is ≥1 day old. Click "Vollständige Synchronisierung" (Settings → Smoobu) or the per-conversation sync button. The conversation must NOT jump to the top of the inbox — it should stay in its real chronological slot.

- [ ] **Step 4: Confirm polling still refreshes on out-of-order sync**

While the inbox is open in one tab, trigger a per-conversation sync from another tab on a conversation that has a backfilled-but-older message. The inbox poller (which still watches `updated_at`) must visibly refresh the conversation card. Verify via the network tab that the conversations API was re-fetched.

- [ ] **Step 5: Report results to the user**

Write a one-paragraph summary: did the inbox order match Smoobu? Did out-of-order sync stop pushing old threads to the top? Did polling still refresh? Include any conversation IDs that still look wrong.

---

## Self-Review Notes

- **Spec coverage:** Every place `Conversation.updated_at` was written or sorted is touched (verified via the two greps earlier in the session). Polling tripwire preserved — `updated_at` is still bumped on every message event. Migration includes index for sort performance.
- **Backfill correctness:** `COALESCE(MAX(message.sent_at), created_at, updated_at)` covers conversations with no messages and conversations created without timestamps.
- **No placeholder steps:** every code step shows exact text to find and exact text to insert.
- **Type consistency:** `last_message_at` is `db.DateTime` everywhere; comparisons use `>`; `to_dict` returns ISO string; tests construct it via `datetime.utcnow() - timedelta(...)`.
- **Risk:** if a test fixture in this codebase doesn't expose `client` / `login_as_admin`, Task 3 Step 2 explicitly says to fall back to a direct query test. Don't fabricate fixtures.
