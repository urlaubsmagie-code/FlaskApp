# Email Auto-Insert Flush Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-click Settings action that files all already-gathered E-Mail-Abgleich candidates (match ≥ 0.8) into their matched chats without manual confirmation, with a one-click undo and a subtle in-chat marker; keep the ongoing Booking daemon path enabled.

**Architecture:** Reuse the existing `promote_email_candidates(conv_id, min_confidence)` helper. Add a batch wrapper that loops it over every conversation with pending ≥0.8 candidates and records the inserted message IDs in `AISettings` so an undo can delete exactly those rows. Two thin admin-gated routes drive it from the existing "E-Mail-Abgleich" Settings card. A marker is rendered wherever a message's `platform_message_id` starts with `email:`.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, vanilla JS, pytest. Design spec: `docs/superpowers/specs/2026-07-01-email-autoinsert-flush-design.md`.

## Global Constraints

- Confidence floor is the existing `email_confidence_threshold` setting (default `0.8`). Do not hardcode `0.8` in new logic — read it from `get_reconcile_config()['threshold']`.
- Auto-inserted messages MUST carry `platform_message_id = f"email:{gmail_message_id}"` (already the case in `promote_email_candidates`). This tag is the marker key and the undo key.
- Booking auto-insert stays on; Airbnb stays in the review tray (`email_autoinsert_airbnb='false'`). No change to Airbnb behavior.
- All user-facing copy is German first (English via i18n keys).
- New mutating routes are admin-gated with `@admin_required` (consistent with other Settings actions).
- Bump the `?v=` cache-busting query for every static file touched (`conversation.js`, `style.css`, `i18n.js`) in `templates/chatbot/base.html`.
- Tests use the existing pattern in `tests/test_email_reconcile.py`: `app` fixture, `create_app(config_map['testing'])`, real in-app-context DB.

---

### Task 1: `promote_email_candidates` returns inserted message IDs

Change the shared helper to return the list of newly inserted `Message.id`s instead of a bare count, so the batch flush (Task 2) can record exactly what it inserted for undo. Only two callers exist; one ignores the return, the other needs a `len()`.

**Files:**
- Modify: `services/email_reconcile.py:477-515` (`promote_email_candidates`)
- Modify: `routes.py:4736-4745` (`conversation_recover_emails` — the one caller that uses the return)
- Test: `tests/test_email_flush.py` (new)

**Interfaces:**
- Produces: `promote_email_candidates(conversation_id: int, min_confidence: float) -> list[int]` — IDs of messages newly inserted (excludes dedup-skipped and already-existing rows). Order follows candidate `parsed_timestamp` ascending.

- [ ] **Step 1: Write the failing test**

Create `tests/test_email_flush.py`:

```python
import pytest
from datetime import datetime
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, EmailBackfillCandidate, Guest, Conversation, Message
from ChatBotAI.services.email_reconcile import promote_email_candidates


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _conv_with_candidate(confidence, gmail_id, text="Hallo", ts=None):
    guest = Guest(name="Test Gast")
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform="booking")
    db.session.add(conv)
    db.session.flush()
    cand = EmailBackfillCandidate(
        gmail_message_id=gmail_id, platform="booking", parsed_name="Test Gast",
        parsed_text=text, parsed_timestamp=ts or datetime(2026, 6, 9, 12, 0, 0),
        guessed_conversation_id=conv.id, confidence=confidence, status="pending",
    )
    db.session.add(cand)
    db.session.commit()
    return conv, cand


def test_promote_returns_inserted_message_ids(app):
    conv, cand = _conv_with_candidate(0.9, "gmail-1")
    ids = promote_email_candidates(conv.id, 0.8)
    assert isinstance(ids, list)
    assert len(ids) == 1
    msg = Message.query.get(ids[0])
    assert msg.platform_message_id == "email:gmail-1"
    assert EmailBackfillCandidate.query.get(cand.id).status == "confirmed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_flush.py::test_promote_returns_inserted_message_ids -v`
Expected: FAIL — `promote_email_candidates` returns `int`, so `msg = Message.query.get(ids[0])` raises `TypeError: 'int' object is not subscriptable`.

- [ ] **Step 3: Change the helper to collect and return IDs**

In `services/email_reconcile.py`, edit the loop body and return of `promote_email_candidates`:

```python
    window = get_reconcile_config()['window_minutes']
    router = get_message_router()
    inserted_ids = []
    for cand in cands:
        shim = SimpleNamespace(sent_at=cand.parsed_timestamp)
        if has_equivalent_message(conversation_id, shim, window):
            continue  # leave pending; an equivalent message already exists
        msg, is_new = router._store_message(
            conversation_id=conversation_id, sender_type='guest',
            content=cand.parsed_text,
            platform_message_id=f"email:{cand.gmail_message_id}",
            sent_at=cand.parsed_timestamp, sent_via_app=False,
        )
        cand.status = 'confirmed'
        if is_new:
            inserted_ids.append(msg.id)
    db.session.commit()
    return inserted_ids
```

Also update the docstring's return line from "Returns the number of NEW messages" to "Returns the ids of NEW messages actually inserted". Update the early `return 0` (when `cands` is empty) to `return []`.

- [ ] **Step 4: Fix the one caller that uses the return value**

In `routes.py:4736-4745`, `conversation_recover_emails`, change:

```python
    threshold = get_reconcile_config()['threshold']
    inserted = len(promote_email_candidates(conversation_id, threshold))
    return jsonify({'success': True, 'inserted': inserted})
```

(The on-open caller at `routes.py:282` ignores the return value — leave it unchanged.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_flush.py::test_promote_returns_inserted_message_ids -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/routes.py ChatBotAI/tests/test_email_flush.py
git commit -m "refactor(email-flush): promote_email_candidates returns inserted message ids"
```

---

### Task 2: `promote_all_email_candidates` batch flush

Batch wrapper that flushes every conversation with pending ≥floor candidates and records the inserted IDs for undo.

**Files:**
- Modify: `services/email_reconcile.py` (add function after `promote_email_candidates`, ~line 516)
- Test: `tests/test_email_flush.py`

**Interfaces:**
- Consumes: `promote_email_candidates(conv_id, min_confidence) -> list[int]` (Task 1)
- Produces: `promote_all_email_candidates(min_confidence: float) -> dict` returning `{'inserted': int, 'conversations': int, 'skipped_no_conv': int}`. Side effect: writes JSON list of inserted message IDs to `AISettings['email_last_flush_message_ids']`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_email_flush.py`:

```python
import json
from ChatBotAI.models import AISettings
from ChatBotAI.services.email_reconcile import promote_all_email_candidates


def test_flush_all_inserts_only_above_floor_and_records_ids(app):
    conv_hi, _ = _conv_with_candidate(0.9, "gmail-hi")
    conv_lo, cand_lo = _conv_with_candidate(0.5, "gmail-lo")
    # a pending high-conf candidate with no conversation -> counted as skipped
    orphan = EmailBackfillCandidate(
        gmail_message_id="gmail-orphan", platform="booking", parsed_name="X",
        parsed_text="hi", parsed_timestamp=datetime(2026, 6, 9, 12, 0, 0),
        guessed_conversation_id=None, confidence=0.95, status="pending",
    )
    db.session.add(orphan)
    db.session.commit()

    result = promote_all_email_candidates(0.8)

    assert result['inserted'] == 1
    assert result['conversations'] == 1
    assert result['skipped_no_conv'] == 1
    # low-conf untouched
    assert EmailBackfillCandidate.query.get(cand_lo.id).status == "pending"
    # recorded ids match the one inserted message
    recorded = json.loads(AISettings.get('email_last_flush_message_ids', '[]'))
    assert len(recorded) == 1
    assert Message.query.get(recorded[0]).platform_message_id == "email:gmail-hi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_flush.py::test_flush_all_inserts_only_above_floor_and_records_ids -v`
Expected: FAIL — `ImportError: cannot import name 'promote_all_email_candidates'`.

- [ ] **Step 3: Implement the batch function**

In `services/email_reconcile.py`, add after `promote_email_candidates` (after line ~515):

```python
def promote_all_email_candidates(min_confidence: float) -> dict:
    """Flush every pending EmailBackfillCandidate with confidence >= min_confidence
    into its guessed conversation, reusing promote_email_candidates per conversation.
    Records the inserted message ids in AISettings['email_last_flush_message_ids']
    (JSON) so undo_last_flush() can remove exactly those rows.

    Returns {'inserted': N, 'conversations': M, 'skipped_no_conv': K} where
    skipped_no_conv counts pending >= floor candidates that had no conversation to
    file into (they stay in the review tray)."""
    import json
    from ..models import EmailBackfillCandidate, AISettings

    pending = EmailBackfillCandidate.query.filter_by(status='pending').filter(
        EmailBackfillCandidate.confidence >= min_confidence
    ).all()
    conv_ids = sorted({c.guessed_conversation_id for c in pending
                       if c.guessed_conversation_id is not None})
    skipped_no_conv = sum(1 for c in pending if c.guessed_conversation_id is None)

    all_ids = []
    for conv_id in conv_ids:
        all_ids.extend(promote_email_candidates(conv_id, min_confidence))

    AISettings.set('email_last_flush_message_ids', json.dumps(all_ids),
                   'Message ids inserted by the last email flush (for undo)')
    return {'inserted': len(all_ids),
            'conversations': len(conv_ids),
            'skipped_no_conv': skipped_no_conv}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_flush.py::test_flush_all_inserts_only_above_floor_and_records_ids -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_flush.py
git commit -m "feat(email-flush): promote_all_email_candidates batch flush with recorded ids"
```

---

### Task 3: `undo_last_flush` service helper

Deletes exactly the messages recorded by the last flush and returns their candidates to `pending`.

**Files:**
- Modify: `services/email_reconcile.py` (add after `promote_all_email_candidates`)
- Test: `tests/test_email_flush.py`

**Interfaces:**
- Produces: `undo_last_flush() -> int` — number of messages deleted. Reads/clears `AISettings['email_last_flush_message_ids']`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_email_flush.py`:

```python
from ChatBotAI.services.email_reconcile import undo_last_flush


def test_undo_removes_flush_and_restores_candidates(app):
    conv, cand = _conv_with_candidate(0.9, "gmail-u")
    promote_all_email_candidates(0.8)
    assert Message.query.filter_by(platform_message_id="email:gmail-u").count() == 1

    removed = undo_last_flush()

    assert removed == 1
    assert Message.query.filter_by(platform_message_id="email:gmail-u").count() == 0
    assert EmailBackfillCandidate.query.get(cand.id).status == "pending"
    # second undo is a no-op
    assert undo_last_flush() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_flush.py::test_undo_removes_flush_and_restores_candidates -v`
Expected: FAIL — `ImportError: cannot import name 'undo_last_flush'`.

- [ ] **Step 3: Implement undo**

In `services/email_reconcile.py`, add after `promote_all_email_candidates`:

```python
def undo_last_flush() -> int:
    """Delete the messages recorded by the last flush and reset their candidates to
    'pending' so they can be re-reviewed or re-flushed. Precise to the recorded batch
    even if the daemon inserted other email messages in the meantime. No-op if there
    is no recorded batch."""
    import json
    from ..models import EmailBackfillCandidate, AISettings, Message

    ids = json.loads(AISettings.get('email_last_flush_message_ids', '[]'))
    if not ids:
        return 0

    removed = 0
    for msg in Message.query.filter(Message.id.in_(ids)).all():
        pmid = msg.platform_message_id or ''
        if pmid.startswith('email:'):
            gmail_id = pmid.split('email:', 1)[1]
            cand = EmailBackfillCandidate.query.filter_by(
                gmail_message_id=gmail_id).first()
            if cand:
                cand.status = 'pending'
        db.session.delete(msg)
        removed += 1

    AISettings.set('email_last_flush_message_ids', '[]')
    db.session.commit()
    return removed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_flush.py -v`
Expected: PASS (all four tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_flush.py
git commit -m "feat(email-flush): undo_last_flush removes recorded batch and restores candidates"
```

---

### Task 4: Flush / undo / count routes

Thin admin-gated JSON endpoints the Settings buttons call.

**Files:**
- Modify: `routes.py` (add near the other email-review routes, after `email_review_pending_count` at ~line 4700)
- Test: `tests/test_email_flush.py`

**Interfaces:**
- Produces:
  - `POST /chatbot/api/email-reconcile/flush-all` → `{'success': True, 'inserted': N, 'conversations': M, 'skipped_no_conv': K}`
  - `POST /chatbot/api/email-reconcile/undo-flush` → `{'success': True, 'removed': N}`
  - `GET /chatbot/api/email-reconcile/pending-count` → `{'count': N}` (pending candidates at/above the configured floor with a conversation)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_email_flush.py`:

```python
@pytest.fixture
def client(app):
    return app.test_client()


def _login_admin(app, client):
    from ChatBotAI.models import User
    user = User(username="admin", is_admin=True)
    user.set_password("pw")
    db.session.add(user)
    db.session.commit()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
    return user


def test_flush_and_undo_routes(app, client):
    _login_admin(app, client)
    conv, cand = _conv_with_candidate(0.9, "gmail-route")

    r = client.post('/chatbot/api/email-reconcile/flush-all')
    assert r.status_code == 200
    data = r.get_json()
    assert data['inserted'] == 1

    r2 = client.post('/chatbot/api/email-reconcile/undo-flush')
    assert r2.get_json()['removed'] == 1
    assert EmailBackfillCandidate.query.get(cand.id).status == "pending"
```

Note: if the `User` construction / login shim does not match this app's auth (check `models.py` `User` and how `@admin_required` reads the session — Flask-Login uses `_user_id`), adapt `_login_admin` to the real mechanism before running. Confirm by reading `models.py` `class User` and the `admin_required` decorator definition.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_flush.py::test_flush_and_undo_routes -v`
Expected: FAIL — 404 (routes not registered yet).

- [ ] **Step 3: Add the routes**

In `routes.py`, after `email_review_pending_count` (~line 4700), add:

```python
@chatbot_bp.route('/api/email-reconcile/flush-all', methods=['POST'])
@admin_required
def email_reconcile_flush_all():
    """File all pending email candidates (>= configured floor) into their matched
    chats at once, without manual confirmation."""
    from .services.email_reconcile import promote_all_email_candidates, get_reconcile_config
    threshold = get_reconcile_config()['threshold']
    result = promote_all_email_candidates(threshold)
    return jsonify({'success': True, **result})


@chatbot_bp.route('/api/email-reconcile/undo-flush', methods=['POST'])
@admin_required
def email_reconcile_undo_flush():
    """Remove the messages inserted by the last flush and restore their candidates."""
    from .services.email_reconcile import undo_last_flush
    removed = undo_last_flush()
    return jsonify({'success': True, 'removed': removed})


@chatbot_bp.route('/api/email-reconcile/pending-count')
@login_required
def email_reconcile_pending_count():
    """Count pending candidates at/above the configured floor that have a chat to
    file into (what the flush button would insert)."""
    from .services.email_reconcile import get_reconcile_config
    threshold = get_reconcile_config()['threshold']
    count = EmailBackfillCandidate.query.filter_by(status='pending').filter(
        EmailBackfillCandidate.confidence >= threshold,
        EmailBackfillCandidate.guessed_conversation_id.isnot(None),
    ).count()
    return jsonify({'count': count})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_flush.py::test_flush_and_undo_routes -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/routes.py ChatBotAI/tests/test_email_flush.py
git commit -m "feat(email-flush): flush-all / undo-flush / pending-count routes"
```

---

### Task 5: Settings buttons + JS

Add the flush and undo buttons (plus a live count) into the existing "E-Mail-Abgleich" card.

**Files:**
- Modify: `templates/chatbot/settings.html` (add a setting-item after the on-open threshold block ~line 535; add JS functions near `syncSmoobuMessages` ~line 1765)

**Interfaces:**
- Consumes: routes from Task 4.

- [ ] **Step 1: Add the buttons block**

In `templates/chatbot/settings.html`, after the `email_onopen_threshold` `setting-item` closes (locate the `</div>` ending that block, ~line 535), insert:

```html
                <div class="setting-item">
                    <div class="setting-info">
                        <label data-i18n="settings.emailReconcile.flushAll">Gesammelte E-Mails jetzt einfügen</label>
                        <p class="setting-description" data-i18n="settings.emailReconcile.flushAll.desc">
                            Alle bereits erkannten E-Mail-Treffer (ab Mindest-Konfidenz) ohne Einzelbestätigung in die passenden Chats einfügen.
                            <span id="emailFlushPendingCount"></span>
                        </p>
                    </div>
                    <div class="setting-actions">
                        <button class="btn btn-primary btn-sm" onclick="flushAllEmails()">
                            <i class="fas fa-inbox"></i> <span data-i18n="settings.emailReconcile.flushAll.btn">Alle einfügen</span>
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="undoEmailFlush()">
                            <i class="fas fa-rotate-left"></i> <span data-i18n="settings.emailReconcile.undo.btn">Rückgängig</span>
                        </button>
                    </div>
                </div>
```

- [ ] **Step 2: Add the JS functions**

In `templates/chatbot/settings.html`, near `syncSmoobuMessages` (~line 1765), add:

```javascript
    function refreshEmailFlushCount() {
        fetch('/chatbot/api/email-reconcile/pending-count')
            .then(r => r.json())
            .then(d => {
                const el = document.getElementById('emailFlushPendingCount');
                if (el) el.textContent = (d.count || 0) + ' bereit.';
            })
            .catch(() => {});
    }

    function flushAllEmails() {
        const btn = event.target.closest('button');
        const originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        fetch('/chatbot/api/email-reconcile/flush-all', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                if (d.success) {
                    let msg = `${d.inserted} Nachricht(en) in ${d.conversations} Chat(s) eingefügt`;
                    if (d.skipped_no_conv) msg += ` (${d.skipped_no_conv} ohne Chat übersprungen)`;
                    showNotification(msg, 'success');
                    refreshEmailFlushCount();
                } else {
                    showNotification('Einfügen fehlgeschlagen', 'error');
                }
            })
            .catch(() => showNotification('Einfügen fehlgeschlagen', 'error'))
            .finally(() => { btn.disabled = false; btn.innerHTML = originalHtml; });
    }

    function undoEmailFlush() {
        if (!confirm('Letzten Abgleich rückgängig machen?')) return;
        const btn = event.target.closest('button');
        const originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        fetch('/chatbot/api/email-reconcile/undo-flush', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                showNotification(`${d.removed || 0} Nachricht(en) entfernt`, 'success');
                refreshEmailFlushCount();
            })
            .catch(() => showNotification('Rückgängig fehlgeschlagen', 'error'))
            .finally(() => { btn.disabled = false; btn.innerHTML = originalHtml; });
    }

    document.addEventListener('DOMContentLoaded', refreshEmailFlushCount);
```

- [ ] **Step 3: Manual verification**

Run the app (`python -m ChatBotAI.run`), open `/chatbot/settings` as an admin, confirm the "E-Mail-Abgleich" card shows the two buttons and a "N bereit." count. Click "Alle einfügen" → success toast; open an affected Booking chat → the emails appear. Click "Rückgängig" → messages removed.

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/templates/chatbot/settings.html
git commit -m "feat(email-flush): Settings buttons for flush-all and undo"
```

---

### Task 6: Subtle in-chat marker

Show "via E-Mail-Abgleich" on messages whose `platform_message_id` starts with `email:`, in both the server-rendered thread and the JS-appended path.

**Files:**
- Modify: `templates/chatbot/conversation.html:228` (message-text block)
- Modify: `static/js/conversation.js:1095-1105` (`addMessageToUI` innerHTML)
- Modify: `static/css/style.css` (add `.email-source-tag` rule)
- Modify: `static/js/i18n.js` (add `conversation.emailSource` key, both languages)
- Modify: `templates/chatbot/base.html` (bump `?v=` for `conversation.js`, `style.css`, `i18n.js`)

**Interfaces:**
- Consumes: `Message.platform_message_id` (already exposed via `Message.to_dict()` at `models.py:429` for the JS path).

- [ ] **Step 1: Server-rendered marker**

In `templates/chatbot/conversation.html`, immediately after line 228 (`<div class="message-text">{{ message.content }}</div>`), add:

```html
                {% if message.platform_message_id and message.platform_message_id.startswith('email:') %}
                <div class="email-source-tag" data-i18n="conversation.emailSource">via E-Mail-Abgleich</div>
                {% endif %}
```

- [ ] **Step 2: JS-appended marker**

In `static/js/conversation.js`, inside `addMessageToUI` update the `messageDiv.innerHTML` template (line ~1095) so the message-content block becomes:

```javascript
    const emailTag = (message.platform_message_id || '').startsWith('email:')
        ? `<div class="email-source-tag">${i18n.t('conversation.emailSource')}</div>` : '';
    messageDiv.innerHTML = `
        <div class="message-avatar"><i class="fas ${icon}"></i></div>
        <div class="message-content">
            <div class="message-header">
                <span class="sender-name">${name}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-text">${escapeHtml(message.content || '')}</div>
            ${emailTag}
        </div>
        ${perMsgActionBtn}
    `;
```

- [ ] **Step 3: CSS**

In `static/css/style.css`, add:

```css
.email-source-tag {
    font-size: 0.7rem;
    color: var(--text-muted, #888);
    font-style: italic;
    margin-top: 2px;
}
```

- [ ] **Step 4: i18n strings**

In `static/js/i18n.js`, add to the `conversation` group in both the German (`de`) and English (`en`) translation objects:

```javascript
        // de
        "conversation.emailSource": "via E-Mail-Abgleich",
```
```javascript
        // en
        "conversation.emailSource": "via email reconciliation",
```

(Match the exact nesting/format used by neighboring `conversation.*` keys in the file.)

- [ ] **Step 5: Cache-bust**

In `templates/chatbot/base.html`, bump the `?v=` query string for `conversation.js`, `style.css`, and `i18n.js` (e.g. `conversation.js?v=26` → `v=27`, `style.css?v=51` → `v=52`, `i18n.js?v=25` → `v=26`; use the actual current values found in the file).

- [ ] **Step 6: Manual verification**

Reload an affected Booking chat (hard refresh). Confirm the inserted email messages show the small "via E-Mail-Abgleich" tag and Smoobu-native messages do not. Trigger a poll-in (or reopen) to confirm the JS-appended path also shows the tag.

- [ ] **Step 7: Commit**

```bash
git add ChatBotAI/templates/chatbot/conversation.html ChatBotAI/static/js/conversation.js ChatBotAI/static/css/style.css ChatBotAI/static/js/i18n.js ChatBotAI/templates/chatbot/base.html
git commit -m "feat(email-flush): subtle 'via E-Mail-Abgleich' marker on inserted messages"
```

---

### Task 7: Full test run + enable ongoing

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest ChatBotAI/tests/ -v`
Expected: all pass (existing 225 + the 3 new flush tests).

- [ ] **Step 2: Enable ongoing Booking auto-insert (operator action, no code)**

In `/chatbot/settings` → "E-Mail-Abgleich": turn ON "E-Mail-Abgleich aktivieren" (`email_reconcile_enabled`) and confirm "Booking.com-Treffer automatisch einfügen" is ON and "Airbnb-Treffer automatisch einfügen" is OFF. The daemon (`app.py:370-388`) then keeps filing new ≥0.8 Booking emails going forward. No code change — this is a runtime toggle, done after the backlog flush is spot-checked.

---

## Self-Review

**Spec coverage:**
- Batch flush (spec §1) → Task 2. ✅
- Settings buttons + live count (spec §2) → Task 5. ✅
- Undo (spec §3) → Task 3 (service) + Task 4 (route) + Task 5 (button). ✅
- Ongoing Booking daemon (spec §4) → Task 7 Step 2 (existing toggle, no code). ✅
- In-chat marker + `platform_message_id` exposure (spec §5) → Task 6; exposure already present via `to_dict()`, verified. ✅
- Testing (spec §Testing) → floor (Task 2), dedup (reused, exercised via `has_equivalent_message`), captured IDs (Task 2), undo + no-op second undo (Task 3), `skipped_no_conv` (Task 2). ✅

**Placeholder scan:** No TBD/TODO; every code step shows full code. The only "adapt to real code" note is Task 4 Step 1's login shim, which points at the exact files to confirm — acceptable because auth wiring wasn't read during planning.

**Type consistency:** `promote_email_candidates` returns `list[int]` everywhere after Task 1; `promote_all_email_candidates` returns the dict consumed by the route and JS; `undo_last_flush` returns `int` consumed as `removed`. Setting key `email_last_flush_message_ids` is written in Task 2 and read/cleared in Task 3 consistently. Marker key `platform_message_id` prefix `email:` matches the insert tag from Task 1.
