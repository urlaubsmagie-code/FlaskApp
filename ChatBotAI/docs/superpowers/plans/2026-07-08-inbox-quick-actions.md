# Inbox Quick-Actions Menu (⋮) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A per-card ⋮ menu on the inbox that manages a chat without opening it: mark read/unread, toggle auto-respond, close, and generate a UMI reply (preview→send, or instant send behind a global toggle).

**Architecture:** Reuse existing endpoints. The ⋮ menu is a single reused popover on the inbox list. UMI-Antwort = generate a **draft** (`/ai-response` with `draft_only`) then **approve** it (which already delivers to the guest) or **reject** it. A global `inbox_umi_instant_send` AISetting flips preview↔instant.

**Tech Stack:** Flask (blueprint routes), SQLite/SQLAlchemy, vanilla JS (inbox.js), Jinja templates, CSS variables (theme-aware), i18n.js.

## Global Constraints

- Inbox cards render in TWO places — server Jinja (`inbox.html`) and JS (`createConversationCard` in `inbox.js`). Any card markup change goes in BOTH.
- German-default UI; every user-facing string needs a `data-i18n` key with DE + EN in `i18n.js`.
- Theme-aware CSS (`:root[data-theme="dark"]` overrides) for any new visible element.
- Cards are `<a>` links — menu button and all menu actions MUST `event.stopPropagation()` + `event.preventDefault()`.
- `flask db` is NEVER run here (touches prod DB). No schema migration — `AISettings` is a key/value table, no migration needed.
- Bump `?v=` cache versions for any changed static file (current: inbox.js v30, style.css v51, i18n.js v31).
- Safety: UMI-Antwort item shown ONLY when `ai_enabled` true, `escalated` false, and the last message is from the guest.

---

### Task 1: Backend — mark-unread endpoint + `draft_only` on generate

**Files:**
- Modify: `routes.py` (add `/unread` route near the `/read` route ~line 1047; add `draft_only` handling in `api_generate_ai_response` ~line 1141)
- Test: `tests/test_inbox_quick_actions.py` (new)

**Interfaces:**
- Produces: `POST /api/conversations/<id>/unread` → `{is_read: bool}`
- Produces: `POST /api/conversations/<id>/ai-response` accepts JSON `{draft_only: true}` → always returns `{success, approval_status:'pending', message: {...}}` (never auto-sends).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_inbox_quick_actions.py
from datetime import datetime
from ChatBotAI.models import db, Conversation, Guest, Message

def _mk_conv(app):
    with app.app_context():
        g = Guest(name='T'); db.session.add(g); db.session.commit()
        c = Conversation(guest_id=g.id, platform='smoobu', platform_id='r1',
                         status='active', ai_enabled=True, is_read=True,
                         last_message_at=datetime.utcnow())
        db.session.add(c); db.session.commit()
        m = Message(conversation_id=c.id, sender_type='guest', content='hi',
                    sent_at=datetime.utcnow())
        db.session.add(m); db.session.commit()
        c.last_read_message_id = m.id
        c.is_read = True
        db.session.commit()
        return c.id

def test_mark_unread_sets_unread(client, app):
    cid = _mk_conv(app)
    r = client.post(f'/chatbot/api/conversations/{cid}/unread')
    assert r.status_code == 200
    assert r.get_json()['is_read'] is False
    with app.app_context():
        assert Conversation.query.get(cid).is_read is False
```

- [ ] **Step 2: Run to confirm FAIL**

Run: `python -m pytest tests/test_inbox_quick_actions.py -v`
Expected: FAIL (404 — route not defined).

- [ ] **Step 3: Add the `/unread` route** (in `routes.py`, right after `api_mark_conversation_read`)

```python
@chatbot_bp.route('/api/conversations/<int:conversation_id>/unread', methods=['POST'])
@login_required
def api_mark_conversation_unread(conversation_id):
    """Mark a conversation as unread: rewind the read cursor, recompute is_read."""
    conversation = Conversation.query.get_or_404(conversation_id)
    conversation.last_read_message_id = None
    conversation.recompute_is_read()   # unread iff a guest message exists
    db.session.commit()
    return jsonify({'is_read': conversation.is_read})
```

- [ ] **Step 4: Add `draft_only` to `api_generate_ai_response`**

Near the top of the function (after `conversation = ...get_or_404`), read the flag:

```python
    draft_only = bool((request.get_json(silent=True) or {}).get('draft_only'))
```

Change the send/draft branch condition (currently `if approval_queue_enabled and not conversation.auto_approve:`) to:

```python
        if draft_only or (approval_queue_enabled and not conversation.auto_approve):
```

(Everything else in that branch is unchanged — it saves `approval_status='pending'` and returns `{success, approval_status:'pending', message: ai_message.to_dict()}`.)

- [ ] **Step 5: Run tests — PASS**

Run: `python -m pytest tests/test_inbox_quick_actions.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add routes.py tests/test_inbox_quick_actions.py
git commit -m "feat(inbox): mark-unread endpoint + draft_only guard on ai-response"
```

---

### Task 2: Backend — expose instant-send flag + Settings toggle

**Files:**
- Modify: `routes.py` (`index()` ~line 252 — pass flag to template)
- Modify: `templates/chatbot/inbox.html` (add flag to `window.inboxConfig`)
- Modify: `templates/chatbot/settings.html` (admin toggle)
- Modify: `static/js/i18n.js` (settings + menu keys)

**Interfaces:**
- Produces: `window.inboxConfig.instantSend` (bool) on the inbox page.
- Uses existing `PUT /api/settings` with `{inbox_umi_instant_send: 'true'|'false'}` (saved via `AISettings.set`).

- [ ] **Step 1: Pass the flag from `index()`**

In `routes.py` `index()`, before `render_template`:

```python
    instant_send = AISettings.get('inbox_umi_instant_send', 'false') == 'true'
    return render_template('chatbot/inbox.html', conversations=conversations,
                           total_conversations=total_conversations,
                           inbox_instant_send=instant_send)
```

- [ ] **Step 2: Expose to JS** in `inbox.html` `window.inboxConfig` block:

```javascript
    window.inboxConfig = {
        loadedCount: {{ conversations|length }},
        totalCount: {{ total_conversations }},
        instantSend: {{ 'true' if inbox_instant_send else 'false' }}
    };
```

- [ ] **Step 3: Add the Settings toggle** in `settings.html` (in the AI settings section; follow the existing toggle/checkbox pattern in that file — a labeled checkbox bound to key `inbox_umi_instant_send`, saved by the page's existing settings-save JS via `PUT /api/settings`). Include a warning line:

```html
<label class="setting-row">
  <input type="checkbox" id="inboxInstantSend" data-setting="inbox_umi_instant_send">
  <span data-i18n="settings.inboxInstantSend.label">UMI-Antwort aus dem Posteingang sofort senden (ohne Vorschau)</span>
</label>
<p class="setting-hint" data-i18n="settings.inboxInstantSend.hint">Achtung: UMI-Antworten gehen dann ohne Vorschau direkt an den Gast.</p>
```

(Match the actual markup/JS wiring used by other toggles in `settings.html`; if toggles there post individually, wire this one the same way.)

- [ ] **Step 4: i18n keys** — add to BOTH locales in `i18n.js`:

```javascript
// DE
'settings.inboxInstantSend.label': 'UMI-Antwort aus dem Posteingang sofort senden (ohne Vorschau)',
'settings.inboxInstantSend.hint': 'Achtung: UMI-Antworten gehen dann ohne Vorschau direkt an den Gast.',
// EN
'settings.inboxInstantSend.label': 'Send UMI reply from the inbox instantly (no preview)',
'settings.inboxInstantSend.hint': 'Warning: UMI replies then go straight to the guest with no preview.',
```

- [ ] **Step 5: Manual check** — open Settings, toggle on, reload, confirm it persists (GET /api/settings returns it). Commit.

```bash
git add routes.py templates/chatbot/inbox.html templates/chatbot/settings.html static/js/i18n.js
git commit -m "feat(inbox): instant-send setting + expose flag to inbox JS"
```

---

### Task 3: Frontend — ⋮ button + popover shell (both render paths)

**Files:**
- Modify: `static/css/style.css` (menu styles; bump v51→v52 in `base.html`)
- Modify: `templates/chatbot/inbox.html` (replace X with ⋮ in server card meta)
- Modify: `static/js/inbox.js` (`createConversationCard`: replace X with ⋮; add menu engine)
- Modify: `static/js/i18n.js` (`inbox.menu.*` keys)

**Interfaces:**
- Produces: `window.openCardMenu(convId, anchorEl)`, `window.closeCardMenu()`.
- Card button markup: `<button class="card-menu-btn" onclick="openCardMenu(event, <id>)">⋮</button>` (replaces `btn-close-conv`).

- [ ] **Step 1: CSS** — add to `style.css` (theme-aware): `.card-menu-btn` (icon button), `.card-menu` (fixed popover, `z-index:1000`, rounded, shadow, `min-width:220px`), `.card-menu-item` (full-width button, icon+label, hover), `.card-menu-sep` (divider), `.card-menu-preview` (text block + Senden/Abbrechen row), `.card-menu-danger` (close item). Dark overrides under `:root[data-theme="dark"]`.

- [ ] **Step 2: Server card markup** — in `inbox.html`, replace the `btn-close-conv` block (lines ~131-133) with:

```html
                    <button class="card-menu-btn" onclick="openCardMenu(event, {{ conv.id }})" data-i18n-title="inbox.menu.title" title="Optionen" aria-label="Optionen">
                        <i class="fas fa-ellipsis-v"></i>
                    </button>
```

- [ ] **Step 3: JS card markup** — in `createConversationCard` in `inbox.js`, replace the close-button string with the same `.card-menu-btn` markup (using template-literal `${conv.id}` and `i18n.t('inbox.menu.title')`).

- [ ] **Step 4: Menu engine** — add to `inbox.js`. One shared popover element appended to `document.body`, positioned under the anchor (flip above if near viewport bottom). `openCardMenu(event, convId)` stops propagation/prevents default, closes any open menu, builds items (see Task 4/5), positions, shows. `closeCardMenu()` hides. Global listeners: outside-click, `Esc`, and `scroll` (capture) on the conversation list → `closeCardMenu()`. Store `currentMenuConvId`.

- [ ] **Step 5: i18n** — `inbox.menu.title`='Optionen'/'Options', plus the item labels used in Tasks 4–5. Add to both locales.

- [ ] **Step 6: Verify** — `node --check static/js/inbox.js`; load inbox (playtest ok), click ⋮ → empty popover opens/positions, outside-click/Esc/scroll close it, card does NOT navigate. Commit.

```bash
git add static/css/style.css templates/chatbot/inbox.html templates/chatbot/base.html static/js/inbox.js static/js/i18n.js
git commit -m "feat(inbox): three-dots card menu shell (button + popover)"
```

---

### Task 4: Frontend — safe actions (mark read/unread, auto-respond, close)

**Files:**
- Modify: `static/js/inbox.js` (menu item builders + handlers)
- Modify: `static/js/i18n.js` (labels)

**Interfaces:**
- Consumes: `openCardMenu`, `closeCardMenu` from Task 3; existing `updateConversationCard(card, conv)`; endpoints `PATCH /read`, `POST /unread`, `POST /toggle-auto-respond`, `PUT /status`.

- [ ] **Step 1: Build the safe items** in the menu for `convId`, reading current state from the card's dataset (`data-is-read`, `data-status`, and the card's ai/auto badges):
  - Read toggle: if `data-is-read==='true'` → "Als ungelesen markieren" → `POST /unread`; else "Als gelesen markieren" → `PATCH /read` (empty body).
  - Auto-Antwort: "Auto-Antwort AN"/"…AUS" → `POST /toggle-auto-respond`; on `{error}` (AI off) show toast.
  - Chat schließen (`.card-menu-danger`): only if `data-status!=='closed'` → `PUT /status` body `{status:'closed'}`.

- [ ] **Step 2: Handlers** — each: `fetch` the endpoint, on success `closeCardMenu()` and refresh the one card. For read/unread and status, update the card's dataset + classes directly (toggle `unread` class, update status badge) or call `refreshConversations()` if simpler. For auto-respond, update the card's auto badge.

- [ ] **Step 3: i18n** — `inbox.menu.markRead`/`markUnread`/`autoOn`/`autoOff`/`close` (DE+EN).

- [ ] **Step 4: Verify** (playtest chat): each action works, card updates in place, menu closes. `node --check`. Commit.

```bash
git add static/js/inbox.js static/js/i18n.js
git commit -m "feat(inbox): card menu — mark read/unread, auto-respond, close"
```

---

### Task 5: Frontend — UMI-Antwort (preview→send / instant)

**Files:**
- Modify: `static/js/inbox.js` (UMI item + preview panel + instant path)
- Modify: `static/js/i18n.js` (labels)

**Interfaces:**
- Consumes: `POST /api/conversations/<id>/ai-response` body `{draft_only:true}` → `{message:{id,content}, approval_status:'pending'}` (or `{skipped}`/`{error}`); `POST /api/messages/<id>/approve`; `POST /api/messages/<id>/reject`; `window.inboxConfig.instantSend`.

- [ ] **Step 1: Visibility guard** — add the UMI item ONLY when the card is eligible: `ai_enabled` (card has the ai badge / dataset), not escalated (`data-status!=='escalated'` and no escalation marker), and the last message is from the guest. Derive "last message is guest" from the card preview: guest messages have no `Ich:/Team:/UMI:` prefix. Add `data-last-sender` to the card in Task 3 markup (server: `conv.last_message.sender_type`; JS: same) and gate on `data-last-sender==='guest'`.
  - Label: instant mode → "UMI-Antwort senden"; preview mode → "UMI-Antwort".

- [ ] **Step 2: Generate** — on click: swap menu to a spinner, `POST /ai-response` with `{draft_only:true}`. Handle `{skipped}` → toast "Keine Antwort nötig", close. Handle `{error}`/non-200 → toast error, keep menu. On success keep `message.id` and `message.content`.

- [ ] **Step 3a: Preview mode** (`!instantSend`) — render `.card-menu-preview`: the drafted `content` (escaped) + `[Abbrechen]` `[Senden]`.
  - Senden → `POST /api/messages/<id>/approve` → toast "Gesendet", close, refresh card.
  - Abbrechen → `POST /api/messages/<id>/reject` → close.

- [ ] **Step 3b: Instant mode** (`instantSend`) — immediately `POST /api/messages/<id>/approve` (no preview) → toast "Gesendet"/"Fehler", close, refresh card.

- [ ] **Step 4: i18n** — `inbox.menu.umiReply`/`umiReplySend`/`send`/`cancel`/`sent`/`sendError`/`noReplyNeeded`/`generating` (DE+EN).

- [ ] **Step 5: Verify on a PLAYTEST chat only** (never a real guest during dev): preview shows text; Senden posts & appears in the chat; Abbrechen discards; flip `inbox_umi_instant_send` on → one-tap send; confirm UMI item hidden on an escalated chat and when our reply is already last. `node --check`. Commit.

```bash
git add static/js/inbox.js static/js/i18n.js
git commit -m "feat(inbox): card menu — UMI-Antwort preview/instant send"
```

---

### Task 6: Cache bumps + Hilfe note + final verification

**Files:**
- Modify: `templates/chatbot/inbox.html` (inbox.js v30→v31), `base.html` (style v51→v52, i18n v31→v32 if not already bumped)
- Modify: `templates/chatbot/help.html` (one card documenting the ⋮ menu)

- [ ] **Step 1: Bump versions** for every changed static file (inbox.js, style.css, i18n.js) that isn't already bumped this feature.

- [ ] **Step 2: Hilfe** — add a `help-card` under the Posteingang tab describing the ⋮ menu and its actions (incl. the instant-send setting), German, matching existing style.

- [ ] **Step 3: Full manual pass** (desktop + mobile via DevTools) against playtest chats: every action, both send modes, close/Esc/scroll/outside-click, both render paths (initial load + after a poll refresh). `python -m pytest tests/test_inbox_quick_actions.py -v` green.

- [ ] **Step 4: Commit**

```bash
git add templates/chatbot/inbox.html templates/chatbot/base.html templates/chatbot/help.html
git commit -m "chore(inbox): cache bumps + Hilfe entry for card menu"
```

---

## Self-Review

- **Spec coverage:** trigger/popover (T3) ✓; mark read/unread (T1 backend, T4 UI) ✓; auto-respond (T4) ✓; close + X removal (T3 markup, T4 handler) ✓; UMI preview→approve/reject (T5) ✓; instant-send toggle (T2 + T5) ✓; safety rails escalation/AI-off/last-sender-guest (T5) ✓; two render paths (T3 constraint) ✓; Hilfe (T6) ✓.
- **Placeholders:** backend code is complete; frontend steps reference exact endpoints/return shapes and existing helpers (`updateConversationCard`, `refreshConversations`). CSS/settings-markup steps say "match existing pattern" because those files' conventions must be followed verbatim — the implementer reads the neighbouring markup.
- **Types:** `draft_only` (bool) and return `{message:{id,content}}` consistent across T1/T5; `window.inboxConfig.instantSend` consistent T2/T5; endpoint paths match routes.py verbatim.
