# Email Candidate Promotion (On-Open Auto-Insert + Recover Button) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let queued email candidates reach conversations two new ways — silent auto-insert of ≥0.95 matches when a chat is opened (toggleable), and a per-chat button that pulls already-detected matches down to the 0.8 bar.

**Architecture:** One shared, dedup-guarded helper `promote_email_candidates(conversation_id, min_confidence)` in `services/email_reconcile.py` does the insert work. `conversation_view` calls it at the 0.95 bar on open (gated by a Settings toggle); a new `POST /api/conversation/<id>/recover-emails` calls it at the 0.8 bar on button click. No new daemon behavior, no migration (settings are AISettings key/value).

**Tech Stack:** Flask blueprint, SQLAlchemy, SQLite, Jinja2, vanilla JS, pytest. German-first UI with `static/js/i18n.js`.

## Global Constraints

- Reuse the existing insert path `MessageRouter._store_message(conversation_id, sender_type='guest', content, platform_message_id=f"email:<gmail-id>", sent_at, sent_via_app=False)` — do NOT write a new insert.
- Reuse `has_equivalent_message(conversation_id, notif, window_minutes)` for dedup; it reads only `notif.sent_at`.
- Reuse `get_reconcile_config()` → keys `threshold` (default 0.8) and `window_minutes` (default 10).
- New settings: `email_autoinsert_on_open` (bool string, default `'true'`), `email_onopen_threshold` (float string, default `'0.95'`). Read with `AISettings.get(key, default)`; persisted generically by the existing `saveToggleSetting`/`saveRangeSetting` JS — no settings-save route change.
- Silent insert: no banner/undo. German UI default, English fallback.
- Do not modify the background daemon or the shadow-mode flags.
- Tests live in `ChatBotAI/tests/test_email_reconcile.py`; run from `C:/Users/admin/Documents/FlaskApp` with `python -m pytest`.
- Commit in the nested ChatBotAI repo (`cd ChatBotAI`), branch `feat/notion-knowledge-sync`.

---

## File Structure

- **Modify** `services/email_reconcile.py` — add `promote_email_candidates()` helper near `has_equivalent_message`/`get_reconcile_config`.
- **Modify** `routes.py` — call helper in `conversation_view` (Mode 1); add `conversation_recover_emails` endpoint (Mode 2).
- **Modify** `templates/chatbot/settings.html` — two new setting-items in the Email Reconciliation card.
- **Modify** `templates/chatbot/conversation.html` — recover button beside the sync button; bump `conversation.js` cache version.
- **Modify** `static/js/conversation.js` — `recoverEmails()` function.
- **Modify** `static/js/i18n.js` — de/en keys; bump cache version where referenced.
- **Modify** `tests/test_email_reconcile.py` — unit + route tests.

---

### Task 1: `promote_email_candidates` helper

**Files:**
- Modify: `ChatBotAI/services/email_reconcile.py` (add after `get_reconcile_config`, ~line 470)
- Test: `ChatBotAI/tests/test_email_reconcile.py`

**Interfaces:**
- Consumes: `EmailBackfillCandidate` model, `has_equivalent_message`, `get_reconcile_config`, `MessageRouter._store_message`.
- Produces: `promote_email_candidates(conversation_id: int, min_confidence: float) -> int` (count inserted).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_email_reconcile.py`:

```python
from ChatBotAI.services.email_reconcile import promote_email_candidates


def _pending_candidate(conv_id, confidence, ts, gmail_id, text='Hallo, Frage zur Anreise'):
    c = EmailBackfillCandidate(
        gmail_message_id=gmail_id, platform='booking', parsed_name='Carolin Janowski',
        parsed_text=text, parsed_timestamp=ts, guessed_conversation_id=conv_id,
        confidence=confidence, status='pending')
    db.session.add(c); db.session.commit()
    return c


def _bare_conv():
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking')
    db.session.add(conv); db.session.commit()
    return conv


def test_promote_inserts_at_or_above_bar(app):
    conv = _bare_conv()
    _pending_candidate(conv.id, 0.97, datetime(2026, 6, 20, 9, 0), 'e1')
    n = promote_email_candidates(conv.id, 0.95)
    assert n == 1
    msgs = Message.query.filter_by(conversation_id=conv.id).all()
    assert len(msgs) == 1
    assert msgs[0].platform_message_id == 'email:e1'
    assert EmailBackfillCandidate.query.filter_by(gmail_message_id='e1').first().status == 'confirmed'


def test_promote_skips_below_bar(app):
    conv = _bare_conv()
    _pending_candidate(conv.id, 0.90, datetime(2026, 6, 20, 9, 0), 'e2')
    n = promote_email_candidates(conv.id, 0.95)
    assert n == 0
    assert Message.query.filter_by(conversation_id=conv.id).count() == 0
    assert EmailBackfillCandidate.query.filter_by(gmail_message_id='e2').first().status == 'pending'


def test_promote_skips_duplicate_in_window(app):
    conv = _bare_conv()
    db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                           content='schon da', sent_at=datetime(2026, 6, 20, 9, 3)))
    db.session.commit()
    _pending_candidate(conv.id, 0.99, datetime(2026, 6, 20, 9, 0), 'e3')  # 3 min from existing
    n = promote_email_candidates(conv.id, 0.95)
    assert n == 0
    assert EmailBackfillCandidate.query.filter_by(gmail_message_id='e3').first().status == 'pending'


def test_promote_orders_oldest_first(app):
    conv = _bare_conv()
    _pending_candidate(conv.id, 0.99, datetime(2026, 6, 20, 11, 0), 'late', text='zweite')
    _pending_candidate(conv.id, 0.99, datetime(2026, 6, 20, 9, 0), 'early', text='erste')
    promote_email_candidates(conv.id, 0.95)
    msgs = Message.query.filter_by(conversation_id=conv.id).order_by(Message.id).all()
    assert [m.platform_message_id for m in msgs] == ['email:early', 'email:late']


def test_promote_is_idempotent(app):
    conv = _bare_conv()
    _pending_candidate(conv.id, 0.99, datetime(2026, 6, 20, 9, 0), 'e4')
    assert promote_email_candidates(conv.id, 0.95) == 1
    assert promote_email_candidates(conv.id, 0.95) == 0
    assert Message.query.filter_by(conversation_id=conv.id).count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_email_reconcile.py -k promote -q`
Expected: FAIL — `ImportError: cannot import name 'promote_email_candidates'`.

- [ ] **Step 3: Write the helper**

In `services/email_reconcile.py`, after `get_reconcile_config()`:

```python
def promote_email_candidates(conversation_id: int, min_confidence: float) -> int:
    """Insert pending EmailBackfillCandidate rows matched to `conversation_id`
    whose confidence >= min_confidence, oldest first. Dedup-guarded and
    idempotent (confirmed rows are never reconsidered). Returns count inserted."""
    from types import SimpleNamespace
    from ..models import EmailBackfillCandidate
    from .message_router import get_message_router

    cands = EmailBackfillCandidate.query.filter_by(
        guessed_conversation_id=conversation_id, status='pending'
    ).filter(
        EmailBackfillCandidate.confidence >= min_confidence
    ).order_by(EmailBackfillCandidate.parsed_timestamp.asc()).all()
    if not cands:
        return 0

    window = get_reconcile_config()['window_minutes']
    router = get_message_router()
    inserted = 0
    for cand in cands:
        shim = SimpleNamespace(sent_at=cand.parsed_timestamp)
        if has_equivalent_message(conversation_id, shim, window):
            continue  # leave pending; an equivalent message already exists
        router._store_message(
            conversation_id=conversation_id, sender_type='guest',
            content=cand.parsed_text,
            platform_message_id=f"email:{cand.gmail_message_id}",
            sent_at=cand.parsed_timestamp, sent_via_app=False,
        )
        cand.status = 'confirmed'
        inserted += 1
    db.session.commit()
    return inserted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_email_reconcile.py -k promote -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
cd C:/Users/admin/Documents/FlaskApp/ChatBotAI
git add services/email_reconcile.py tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): promote_email_candidates helper (dedup-guarded, idempotent)"
```

---

### Task 2: Mode 1 — auto-insert on chat open

**Files:**
- Modify: `ChatBotAI/routes.py` (`conversation_view`, after `get_or_404` at ~line 271)
- Test: `ChatBotAI/tests/test_email_reconcile.py`

**Interfaces:**
- Consumes: `promote_email_candidates` (Task 1), `AISettings.get`.
- Produces: side effect only — opening a conversation inserts ≥`email_onopen_threshold` candidates when `email_autoinsert_on_open != 'false'`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_email_reconcile.py` (uses the existing `client` fixture):

```python
def test_conversation_open_auto_inserts_high_conf(app, client):
    conv = _bare_conv()
    _pending_candidate(conv.id, 0.97, datetime(2026, 6, 20, 9, 0), 'open1')
    # default: email_autoinsert_on_open unset -> treated as enabled
    resp = client.get(f'/chatbot/conversation/{conv.id}')
    assert resp.status_code == 200
    assert Message.query.filter_by(conversation_id=conv.id, platform_message_id='email:open1').count() == 1


def test_conversation_open_respects_off_toggle(app, client):
    AISettings.set('email_autoinsert_on_open', 'false')
    conv = _bare_conv()
    _pending_candidate(conv.id, 0.97, datetime(2026, 6, 20, 9, 0), 'open2')
    resp = client.get(f'/chatbot/conversation/{conv.id}')
    assert resp.status_code == 200
    assert Message.query.filter_by(conversation_id=conv.id).count() == 0


def test_conversation_open_skips_below_onopen_threshold(app, client):
    conv = _bare_conv()
    _pending_candidate(conv.id, 0.85, datetime(2026, 6, 20, 9, 0), 'open3')  # below 0.95
    client.get(f'/chatbot/conversation/{conv.id}')
    assert Message.query.filter_by(conversation_id=conv.id).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "conversation_open" -q`
Expected: FAIL — the high-conf message is not inserted (count 0 where 1 expected).

- [ ] **Step 3: Wire the helper into `conversation_view`**

In `routes.py`, immediately after `conversation = ... .get_or_404(conversation_id)` (before the `base_filter =` line):

```python
    # Silently pull near-certain email candidates matched to this chat into the
    # thread on open (toggleable). Idempotent; failures must never block the view.
    if AISettings.get('email_autoinsert_on_open', 'true') != 'false':
        try:
            from .services.email_reconcile import promote_email_candidates
            try:
                onopen_threshold = float(AISettings.get('email_onopen_threshold', '0.95'))
            except (TypeError, ValueError):
                onopen_threshold = 0.95
            promote_email_candidates(conversation_id, onopen_threshold)
        except Exception:
            current_app.logger.exception(
                "on-open email promote failed for conv %s", conversation_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "conversation_open" -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd C:/Users/admin/Documents/FlaskApp/ChatBotAI
git add routes.py tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): silent auto-insert of >=0.95 matches on chat open (toggleable)"
```

---

### Task 3: Mode 2 — per-chat recover-emails endpoint

**Files:**
- Modify: `ChatBotAI/routes.py` (add near the email-review API routes, ~line 4710)
- Test: `ChatBotAI/tests/test_email_reconcile.py`

**Interfaces:**
- Consumes: `promote_email_candidates` (Task 1), `get_reconcile_config`.
- Produces: `POST /chatbot/api/conversation/<int:conversation_id>/recover-emails` → JSON `{'success': True, 'inserted': N}`.

- [ ] **Step 1: Write the failing test**

```python
def test_recover_emails_endpoint_inserts_at_standard_bar(app, client):
    conv = _bare_conv()
    _pending_candidate(conv.id, 0.85, datetime(2026, 6, 20, 9, 0), 'rec1')  # >=0.8, <0.95
    _pending_candidate(conv.id, 0.50, datetime(2026, 6, 20, 10, 0), 'rec2')  # below 0.8
    resp = client.post(f'/chatbot/api/conversation/{conv.id}/recover-emails')
    assert resp.status_code == 200
    assert resp.get_json() == {'success': True, 'inserted': 1}
    assert Message.query.filter_by(conversation_id=conv.id, platform_message_id='email:rec1').count() == 1
    assert EmailBackfillCandidate.query.filter_by(gmail_message_id='rec2').first().status == 'pending'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_email_reconcile.py -k recover_emails -q`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 3: Add the endpoint**

In `routes.py`, after `email_review_reject` (~line 4719):

```python
@chatbot_bp.route('/api/conversation/<int:conversation_id>/recover-emails', methods=['POST'])
@login_required
def conversation_recover_emails(conversation_id):
    """Pull already-detected email candidates for this chat (>= standard match
    threshold) into the thread on demand. Returns the number inserted."""
    from .services.email_reconcile import promote_email_candidates, get_reconcile_config
    Conversation.query.get_or_404(conversation_id)
    threshold = get_reconcile_config()['threshold']
    inserted = promote_email_candidates(conversation_id, threshold)
    return jsonify({'success': True, 'inserted': inserted})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_email_reconcile.py -k recover_emails -q`
Expected: PASS.

- [ ] **Step 5: Run the full email-reconcile suite (no regressions)**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_email_reconcile.py -q`
Expected: PASS (all prior + new).

- [ ] **Step 6: Commit**

```bash
cd C:/Users/admin/Documents/FlaskApp/ChatBotAI
git add routes.py tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): per-chat recover-emails endpoint (0.8 bar)"
```

---

### Task 4: Settings UI — toggle + on-open threshold

**Files:**
- Modify: `ChatBotAI/templates/chatbot/settings.html` (inside Email Reconciliation card, after the confidence-threshold setting-item ~line 509)
- Modify: `ChatBotAI/static/js/i18n.js` (de + en keys)

**Interfaces:**
- Consumes: existing `saveToggleSetting(key, checked)` and `saveRangeSetting(key, value)` JS (persist AISettings generically).
- Produces: UI that writes `email_autoinsert_on_open` and `email_onopen_threshold`.

- [ ] **Step 1: Add the two setting-items**

In `settings.html`, immediately before the `</div>` that closes the Email Reconciliation `card-body` (right after the `emailConfidenceThreshold` setting-item, line ~509):

```html
                <div class="setting-item">
                    <div class="setting-info">
                        <label for="emailAutoinsertOnOpen" data-i18n="settings.emailReconcile.autoinsertOnOpen">Treffer beim Öffnen eines Chats einfügen</label>
                        <p class="setting-description" data-i18n="settings.emailReconcile.autoinsertOnOpen.desc">Beim Öffnen einer Konversation werden sehr sichere E-Mail-Treffer automatisch eingefügt</p>
                    </div>
                    <label class="toggle-switch">
                        <input type="checkbox" id="emailAutoinsertOnOpen" name="email_autoinsert_on_open"
                            onchange="saveToggleSetting('email_autoinsert_on_open', this.checked)"
                            {% if settings|selectattr('key', 'equalto', 'email_autoinsert_on_open')|map(attribute='value')|first != 'false' %}checked{% endif %}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>

                <div class="setting-item">
                    <div class="setting-info">
                        <label for="emailOnopenThreshold" data-i18n="settings.emailReconcile.onopenThreshold">Schwelle für Einfügen beim Öffnen</label>
                        <p class="setting-description" data-i18n="settings.emailReconcile.onopenThreshold.desc">Nur Treffer ab diesem Score beim Öffnen automatisch einfügen (Standard 0.95)</p>
                    </div>
                    <div class="range-with-value">
                        <input type="range" id="emailOnopenThreshold" name="email_onopen_threshold"
                            min="0" max="1" step="0.05"
                            value="{{ settings|selectattr('key', 'equalto', 'email_onopen_threshold')|map(attribute='value')|first or '0.95' }}"
                            oninput="document.getElementById('onopenThresholdValue').textContent = parseFloat(this.value).toFixed(2); saveRangeSetting('email_onopen_threshold', this.value)">
                        <span class="range-value" id="onopenThresholdValue">{{ settings|selectattr('key', 'equalto', 'email_onopen_threshold')|map(attribute='value')|first or '0.95' }}</span>
                    </div>
                </div>
```

- [ ] **Step 2: Add i18n keys**

In `static/js/i18n.js`, add to the German (`de`) settings block and the English (`en`) block, matching the file's existing key style:

German:
```javascript
        'settings.emailReconcile.autoinsertOnOpen': 'Treffer beim Öffnen eines Chats einfügen',
        'settings.emailReconcile.autoinsertOnOpen.desc': 'Beim Öffnen einer Konversation werden sehr sichere E-Mail-Treffer automatisch eingefügt',
        'settings.emailReconcile.onopenThreshold': 'Schwelle für Einfügen beim Öffnen',
        'settings.emailReconcile.onopenThreshold.desc': 'Nur Treffer ab diesem Score beim Öffnen automatisch einfügen (Standard 0.95)',
```

English:
```javascript
        'settings.emailReconcile.autoinsertOnOpen': 'Insert matches when opening a chat',
        'settings.emailReconcile.autoinsertOnOpen.desc': 'On opening a conversation, very confident email matches are inserted automatically',
        'settings.emailReconcile.onopenThreshold': 'On-open insert threshold',
        'settings.emailReconcile.onopenThreshold.desc': 'Only insert matches at or above this score on open (default 0.95)',
```

- [ ] **Step 3: Bump the i18n cache version**

Find the i18n.js include (grep `i18n.js?v=` under `templates/`) and increment the `?v=` number by 1. Run:
`cd C:/Users/admin/Documents/FlaskApp/ChatBotAI && grep -rn "i18n.js?v=" templates/`

- [ ] **Step 4: Smoke-test settings renders**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/ -k "settings or email_review" -q`
Expected: PASS (no template break). If no settings-render test exists, add:

```python
def test_settings_page_has_onopen_toggle(app, client):
    resp = client.get('/chatbot/settings')
    assert resp.status_code == 200
    assert b'email_autoinsert_on_open' in resp.data
```

- [ ] **Step 5: Commit**

```bash
cd C:/Users/admin/Documents/FlaskApp/ChatBotAI
git add templates/chatbot/settings.html static/js/i18n.js tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): Settings toggle + on-open threshold for auto-insert"
```

---

### Task 5: Conversation recover button + JS

**Files:**
- Modify: `ChatBotAI/templates/chatbot/conversation.html` (button beside `syncBtn` ~line 87; bump conversation.js `?v=`)
- Modify: `ChatBotAI/static/js/conversation.js` (`recoverEmails()`)
- Modify: `ChatBotAI/static/js/i18n.js` (button title + toast keys)

**Interfaces:**
- Consumes: `POST /chatbot/api/conversation/<id>/recover-emails` (Task 3); the existing `syncConversation()` pattern + conversation-id global in `conversation.js`.
- Produces: a clickable "Find emails for this chat" button.

- [ ] **Step 1: Inspect the existing sync button JS to mirror it**

Run: `cd C:/Users/admin/Documents/FlaskApp/ChatBotAI && grep -n "function syncConversation\|conversationId\|CONVERSATION_ID\|showToast\|function t(" static/js/conversation.js`
Note the exact conversation-id variable name and toast helper used; reuse them verbatim in Step 3.

- [ ] **Step 2: Add the desktop button**

In `conversation.html`, immediately after the sync button block (the `<button ... id="syncBtn">…</button>`, ~line 89):

```html
            <button class="btn btn-icon" onclick="recoverEmails()" id="recoverEmailsBtn" data-i18n-title="conversation.recoverEmails" title="E-Mails für diesen Chat suchen">
                <i class="fas fa-envelope-open-text"></i>
            </button>
```

- [ ] **Step 3: Add `recoverEmails()` to `conversation.js`**

Mirror `syncConversation()`. Use the conversation-id variable name found in Step 1 (shown here as `CONV_ID` — replace with the real one):

```javascript
function recoverEmails() {
    const btn = document.getElementById('recoverEmailsBtn');
    if (btn) { btn.disabled = true; btn.classList.add('loading'); }
    fetch(`/chatbot/api/conversation/${CONV_ID}/recover-emails`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(r => r.json())
    .then(data => {
        if (data.success && data.inserted > 0) {
            window.location.reload();   // inserted messages render in-thread
        } else {
            if (btn) { btn.disabled = false; btn.classList.remove('loading'); }
        }
    })
    .catch(() => { if (btn) { btn.disabled = false; btn.classList.remove('loading'); } });
}
```

- [ ] **Step 4: Add i18n key + bump conversation.js cache version**

In `static/js/i18n.js`, add under de and en respectively:
```javascript
        'conversation.recoverEmails': 'E-Mails für diesen Chat suchen',
```
```javascript
        'conversation.recoverEmails': 'Find emails for this chat',
```

Then bump the conversation.js include version:
`cd C:/Users/admin/Documents/FlaskApp/ChatBotAI && grep -n "conversation.js?v=" templates/chatbot/conversation.html`
Increment the `?v=` by 1.

- [ ] **Step 5: Manual verification**

Start the app, open a conversation that has a pending candidate at 0.8–0.95, click the envelope button. Expected: page reloads and the message appears in the thread; the candidate disappears from `/chatbot/email-review`.

Run the full suite to confirm no regressions:
`cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/ -q`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
cd C:/Users/admin/Documents/FlaskApp/ChatBotAI
git add templates/chatbot/conversation.html static/js/conversation.js static/js/i18n.js
git commit -m "feat(email-reconcile): per-chat 'find emails' recover button"
```

---

## Self-Review

**Spec coverage:**
- Shared helper → Task 1. ✓
- Mode 1 auto-insert on open + toggle + threshold → Task 2 (logic) + Task 4 (settings). ✓
- Mode 2 button + endpoint → Task 3 (endpoint) + Task 5 (button/JS). ✓
- Dedup guard, idempotency, ordering → Task 1 tests. ✓
- Below-0.8 stays in tray → asserted in Task 3 test. ✓
- Settings keys + defaults → Global Constraints + Task 2 (read) + Task 4 (UI). ✓
- GET-that-writes wrapped in try/except → Task 2 Step 3. ✓

**Placeholder scan:** `CONV_ID` in Task 5 is explicitly flagged to be replaced with the real variable from Step 1 — not a silent placeholder. No other TBDs.

**Type consistency:** `promote_email_candidates(conversation_id, min_confidence) -> int` is defined in Task 1 and called identically in Tasks 2 and 3. `get_reconcile_config()['threshold']` / `['window_minutes']` match the verified return keys. Settings keys `email_autoinsert_on_open` / `email_onopen_threshold` are spelled identically in routes, template, and constraints.
