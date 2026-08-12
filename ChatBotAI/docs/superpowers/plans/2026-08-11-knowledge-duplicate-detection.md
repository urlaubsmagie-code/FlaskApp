# Knowledge Duplicate Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the Wissensdatenbank from silently storing the same fact twice, on both the manual form and the 🎓 per-message extraction button.

**Architecture:** One private helper in `routes.py` compares a normalised label within a scope `(category, property_id, street)`. Three call sites use it: create returns `409` with the clashing entry, update excludes itself, and the 🎓 batch filters proposed entries against the KB and against each other. Normalisation happens in Python because SQLite's `LOWER()` is ASCII-only and this KB is full of umlauts.

**Tech Stack:** Flask, SQLAlchemy, SQLite, pytest, vanilla JS (no build step).

## Global Constraints

- Duplicate scope is `(category, property_id, street)` matched exactly. Different scope or different category = not a duplicate.
- Label normalisation: `casefold()`, collapse internal whitespace to single spaces, strip leading/trailing whitespace, strip trailing `.,;:!?` characters.
- **Do not add `street` handling to the manual create/update routes.** They pass `None`. Only the 🎓 path sets `street`.
- The 🎓 path must not gain an AI call — it is already the slowest endpoint and the source of the "Wissensextraktion fehlgeschlagen" reports.
- All user-facing strings go through `i18n.t()` with both a German and an English entry. German is the default.
- Bump the `?v=` cache-buster for every JS file you edit, in the template that loads it.
- Existing tests must stay green: `python -m pytest tests/ -q` (354 passing as of 2026-08-11).

---

### Task 1: Normalisation and lookup helper

**Files:**
- Modify: `routes.py` (add helpers immediately above `api_list_knowledge`, currently line 4917)
- Test: `tests/test_knowledge_duplicates.py` (create)

**Interfaces:**
- Consumes: `KnowledgeEntry` from `.models` (already imported at `routes.py:35`)
- Produces:
  - `_normalize_kb_label(label: str) -> str`
  - `_find_duplicate_knowledge(category: str, label: str, property_id: int | None, street: str | None, exclude_id: int | None = None) -> KnowledgeEntry | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_knowledge_duplicates.py`:

```python
"""The Wissensdatenbank must not silently store the same fact twice.

Matching is an exact comparison of a normalised label within one scope
(category + property + street). Normalisation runs in Python: SQLite's LOWER()
is ASCII-only and would let 'Gaestekarte' and 'gaestekarte' both through once
umlauts are involved.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, KnowledgeEntry, Property, User
from ChatBotAI.routes import _normalize_kb_label, _find_duplicate_knowledge


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _entry(**kw):
    defaults = dict(category='faq', label='Gaestekarte', value='Im Buero abholen',
                    property_id=None, street=None)
    defaults.update(kw)
    e = KnowledgeEntry(**defaults)
    db.session.add(e)
    db.session.commit()
    return e


def test_normalize_collapses_case_and_whitespace():
    assert _normalize_kb_label('  WLAN   Passwort  ') == _normalize_kb_label('wlan passwort')


def test_normalize_handles_umlauts():
    assert _normalize_kb_label('GAESTEKARTE') == _normalize_kb_label('gaestekarte')


def test_normalize_strips_trailing_punctuation():
    assert _normalize_kb_label('Checkout-Zeit:') == _normalize_kb_label('Checkout-Zeit')


def test_finds_exact_duplicate(app):
    existing = _entry()
    hit = _find_duplicate_knowledge('faq', 'Gaestekarte', None, None)
    assert hit is not None and hit.id == existing.id


def test_case_and_space_variant_is_a_duplicate(app):
    existing = _entry()
    hit = _find_duplicate_knowledge('faq', '  gaestekarte ', None, None)
    assert hit is not None and hit.id == existing.id


def test_different_category_is_not_a_duplicate(app):
    _entry()
    assert _find_duplicate_knowledge('nearby', 'Gaestekarte', None, None) is None


def test_different_property_scope_is_not_a_duplicate(app):
    prop = Property(name='Haus 4')
    db.session.add(prop)
    db.session.commit()
    _entry()                                  # global entry
    assert _find_duplicate_knowledge('faq', 'Gaestekarte', prop.id, None) is None


def test_different_street_scope_is_not_a_duplicate(app):
    _entry()                                  # street=None
    assert _find_duplicate_knowledge('faq', 'Gaestekarte', None, 'Hauptstr') is None


def test_exclude_id_ignores_the_entry_itself(app):
    existing = _entry()
    assert _find_duplicate_knowledge('faq', 'Gaestekarte', None, None,
                                     exclude_id=existing.id) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_knowledge_duplicates.py -v`
Expected: FAIL at import — `ImportError: cannot import name '_normalize_kb_label' from 'ChatBotAI.routes'`

- [ ] **Step 3: Write the implementation**

In `routes.py`, immediately above the `@chatbot_bp.route('/api/knowledge')` decorator on `api_list_knowledge`:

```python
def _normalize_kb_label(label):
    """Fold a knowledge label to its comparison form.

    Python, not SQL: SQLite's LOWER() is ASCII-only, so it would treat
    'Gaestekarte' and 'gaestekarte' as different once umlauts are involved.
    """
    return ' '.join((label or '').split()).casefold().rstrip('.,;:!?')


def _find_duplicate_knowledge(category, label, property_id, street, exclude_id=None):
    """An existing entry with the same normalised label in the same scope, or None.

    Scope is (category, property_id, street) matched exactly — the same fact
    stored globally and for one room are deliberately different entries.
    """
    target = _normalize_kb_label(label)
    if not target:
        return None
    candidates = KnowledgeEntry.query.filter_by(
        category=category, property_id=property_id, street=street
    ).all()
    for entry in candidates:
        if exclude_id is not None and entry.id == exclude_id:
            continue
        if _normalize_kb_label(entry.label) == target:
            return entry
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_knowledge_duplicates.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_knowledge_duplicates.py routes.py
git commit -m "feat(knowledge): normalised-label duplicate lookup helper"
```

---

### Task 2: Block duplicates on manual create

**Files:**
- Modify: `routes.py` — `api_create_knowledge`, insert after the `property_id` validation block and before the `# Auto-increment sort_order` comment (currently around line 5028)
- Test: `tests/test_knowledge_duplicates.py` (append)

**Interfaces:**
- Consumes: `_find_duplicate_knowledge` from Task 1
- Produces: `POST /api/knowledge` returns `409` with body `{'error': str, 'existing': {'id': int, 'label': str, 'value': str}}`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_knowledge_duplicates.py`:

```python
@pytest.fixture
def client(app):
    user = User(username='tester', display_name='Tester', is_admin=True)
    user.set_password('pw')
    db.session.add(user)
    db.session.commit()
    c = app.test_client()
    c.post('/chatbot/login', data={'username': 'tester', 'password': 'pw'},
           follow_redirects=True)
    return c


def test_create_rejects_duplicate_with_409(client, app):
    existing = _entry()
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'faq', 'label': 'gaestekarte', 'value': 'Etwas anderes',
    })
    assert resp.status_code == 409
    body = resp.get_json()
    assert body['existing']['id'] == existing.id
    assert body['existing']['label'] == 'Gaestekarte'
    assert KnowledgeEntry.query.count() == 1


def test_create_allows_a_genuinely_new_entry(client, app):
    _entry()
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'faq', 'label': 'WLAN Passwort', 'value': 'sonne2026',
    })
    assert resp.status_code == 201
    assert KnowledgeEntry.query.count() == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_knowledge_duplicates.py -k create -v`
Expected: `test_create_rejects_duplicate_with_409` FAILS with `assert 201 == 409`

- [ ] **Step 3: Write the implementation**

In `api_create_knowledge`, directly before the `# Auto-increment sort_order` comment:

```python
    # The form has no street field, so manual entries are always street=None.
    duplicate = _find_duplicate_knowledge(category, label, property_id, None)
    if duplicate:
        return jsonify({
            'error': f'Es gibt bereits einen Eintrag "{duplicate.label}" in dieser Kategorie.',
            'existing': {
                'id': duplicate.id,
                'label': duplicate.label,
                'value': duplicate.value,
            },
        }), 409
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_knowledge_duplicates.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_knowledge_duplicates.py routes.py
git commit -m "feat(knowledge): reject duplicate labels on create with 409"
```

---

### Task 3: Block duplicates on update, excluding the entry itself

**Files:**
- Modify: `routes.py` — `api_update_knowledge` (starts line 5046), insert the check after the incoming fields are read and validated, before the entry's attributes are assigned
- Test: `tests/test_knowledge_duplicates.py` (append)

**Interfaces:**
- Consumes: `_find_duplicate_knowledge` from Task 1
- Produces: `PUT /api/knowledge/<id>` returns the same `409` shape as Task 2

- [ ] **Step 1: Write the failing test**

Append to `tests/test_knowledge_duplicates.py`:

```python
def test_update_can_save_an_entry_unchanged(client, app):
    existing = _entry()
    resp = client.put(f'/chatbot/api/knowledge/{existing.id}', json={
        'category': 'faq', 'label': 'Gaestekarte', 'value': 'Neuer Text',
    })
    assert resp.status_code == 200
    assert KnowledgeEntry.query.get(existing.id).value == 'Neuer Text'


def test_update_cannot_rename_onto_another_entry(client, app):
    _entry(label='Gaestekarte')
    other = _entry(label='WLAN Passwort', value='sonne2026')
    resp = client.put(f'/chatbot/api/knowledge/{other.id}', json={
        'category': 'faq', 'label': 'gaestekarte', 'value': 'sonne2026',
    })
    assert resp.status_code == 409
    assert KnowledgeEntry.query.get(other.id).label == 'WLAN Passwort'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_knowledge_duplicates.py -k update -v`
Expected: `test_update_cannot_rename_onto_another_entry` FAILS with `assert 200 == 409`

- [ ] **Step 3: Write the implementation**

Read `api_update_knowledge` first to find the local variable names it uses for the
incoming category and label, and the point after validation where the entry is
still unmodified. Insert there:

```python
    duplicate = _find_duplicate_knowledge(category, label, entry.property_id,
                                          entry.street, exclude_id=entry.id)
    if duplicate:
        return jsonify({
            'error': f'Es gibt bereits einen Eintrag "{duplicate.label}" in dieser Kategorie.',
            'existing': {
                'id': duplicate.id,
                'label': duplicate.label,
                'value': duplicate.value,
            },
        }), 409
```

If the route allows the category to change, use the incoming category for the
check, not `entry.category` — otherwise moving an entry into a category that
already has that label slips through.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_knowledge_duplicates.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_knowledge_duplicates.py routes.py
git commit -m "feat(knowledge): block renaming an entry onto an existing label"
```

---

### Task 4: 🎓 batch skips known facts and records its provenance

**Files:**
- Modify: `routes.py` — `api_extract_knowledge_from_message`, the `saved = []` loop (currently lines 4975-4986)
- Test: `tests/test_knowledge_duplicates.py` (append)

**Interfaces:**
- Consumes: `_find_duplicate_knowledge` from Task 1
- Produces: `POST /api/messages/<id>/extract-knowledge` response gains `skipped: int`; created entries carry `source='ai'`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_knowledge_duplicates.py`. This patches the AI service so no
model is called — the test is about the filtering, not extraction quality:

```python
from unittest.mock import patch

from ChatBotAI.models import Guest, Conversation, Message


@pytest.fixture
def owner_message(app):
    g = Guest(name='Anna')
    db.session.add(g)
    db.session.commit()
    conv = Conversation(guest_id=g.id, platform='smoobu')
    db.session.add(conv)
    db.session.commit()
    m = Message(conversation_id=conv.id, sender_type='owner', content='Die Gaestekarte gibt es im Buero.')
    db.session.add(m)
    db.session.commit()
    return m


def _fake_ai(entries):
    svc = type('S', (), {'extract_knowledge_from_message': lambda self, _c: entries})()
    return patch('ChatBotAI.routes.get_ai_service', return_value=svc)


def test_extract_skips_facts_already_in_the_kb(client, app, owner_message):
    _entry(label='Gaestekarte')
    proposed = [
        {'category': 'faq', 'label': 'gaestekarte', 'value': 'Im Buero abholen'},
        {'category': 'faq', 'label': 'Kurtaxe', 'value': '2 Euro pro Nacht'},
    ]
    with _fake_ai(proposed):
        resp = client.post(f'/chatbot/api/messages/{owner_message.id}/extract-knowledge',
                           json={'scope': 'general'})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['saved'] == 1
    assert body['skipped'] == 1
    assert KnowledgeEntry.query.count() == 2


def test_extract_dedupes_within_one_batch(client, app, owner_message):
    proposed = [
        {'category': 'faq', 'label': 'Kurtaxe', 'value': '2 Euro pro Nacht'},
        {'category': 'faq', 'label': ' kurtaxe ', 'value': '2 Euro pro Nacht'},
    ]
    with _fake_ai(proposed):
        resp = client.post(f'/chatbot/api/messages/{owner_message.id}/extract-knowledge',
                           json={'scope': 'general'})
    body = resp.get_json()
    assert body['saved'] == 1
    assert body['skipped'] == 1


def test_extract_marks_entries_as_ai_sourced(client, app, owner_message):
    proposed = [{'category': 'faq', 'label': 'Kurtaxe', 'value': '2 Euro pro Nacht'}]
    with _fake_ai(proposed):
        client.post(f'/chatbot/api/messages/{owner_message.id}/extract-knowledge',
                    json={'scope': 'general'})
    assert KnowledgeEntry.query.filter_by(label='Kurtaxe').first().source == 'ai'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_knowledge_duplicates.py -k extract -v`
Expected: FAIL — `KeyError: 'skipped'`, and the source assertion fails with `'manual' != 'ai'`

- [ ] **Step 3: Write the implementation**

Replace the `saved = []` loop in `api_extract_knowledge_from_message` with:

```python
    saved = []
    skipped = 0
    # Track this batch's own labels: one extraction can emit the same fact twice.
    batch_seen = set()
    for entry in entries:
        scope_key = (entry['category'], _normalize_kb_label(entry['label']))
        if scope_key in batch_seen or _find_duplicate_knowledge(
                entry['category'], entry['label'], target_property_id, target_street):
            skipped += 1
            continue
        batch_seen.add(scope_key)
        ke = KnowledgeEntry(
            property_id=target_property_id,
            street=target_street,
            category=entry['category'],
            label=entry['label'],
            value=entry['value'],
            source='ai',
        )
        db.session.add(ke)
        saved.append(entry)
    db.session.commit()

    return jsonify({'saved': len(saved), 'skipped': skipped, 'entries': saved}), 201
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_knowledge_duplicates.py -v`
Expected: 16 passed

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: 370 passed (354 existing + 16 new). If anything else fails, an existing test
depended on the old response shape or the `'manual'` source default — fix that test only
if the new behaviour is correct.

- [ ] **Step 6: Commit**

```bash
git add tests/test_knowledge_duplicates.py routes.py
git commit -m "feat(knowledge): skip known facts in extraction, tag entries as ai-sourced"
```

---

### Task 5: Frontend — warning on the form, count in the toast

**Files:**
- Modify: `static/js/knowledge.js:422-427` (the `if (!resp.ok)` block in `saveEntry`)
- Modify: `static/js/conversation.js:875-887` (the `.then(data => ...)` toast block)
- Modify: `static/js/i18n.js` — German block near line 443, English block near line 1030
- Modify: `templates/chatbot/knowledge.html:142` — `knowledge.js?v=9` → `?v=10`
- Modify: `templates/chatbot/base.html:234` — `i18n.js?v=39` → `?v=40`
- Modify: `templates/chatbot/conversation.html:375` — `conversation.js?v=38` → `?v=39`

**Interfaces:**
- Consumes: the `409` body from Tasks 2-3 and the `skipped` count from Task 4

There is no JS test harness in this repo, so this task is verified by hand.

- [ ] **Step 1: Add the i18n strings**

In `static/js/i18n.js`, in the German block beside the other
`conversation.knowledge.*` keys:

```javascript
        'conversation.knowledge.savedWithSkipped': '{count} gespeichert, {skipped} bereits bekannt',
        'knowledge.duplicate.open': 'Vorhandenen Eintrag öffnen',
```

In the English block, beside the matching keys:

```javascript
        'conversation.knowledge.savedWithSkipped': '{count} saved, {skipped} already known',
        'knowledge.duplicate.open': 'Open existing entry',
```

- [ ] **Step 2: Handle the 409 in the knowledge form**

Replace the `if (!resp.ok)` block in `saveEntry`:

```javascript
            if (resp.status === 409) {
                const err = await resp.json();
                const openLabel = typeof i18n !== 'undefined'
                    ? i18n.t('knowledge.duplicate.open') : 'Vorhandenen Eintrag öffnen';
                if (confirm(`${err.error}\n\n${openLabel}?`)) {
                    this.closeModal();
                    await this.loadEntries();
                    this.openModal(err.existing.id);
                }
                return;
            }
            if (!resp.ok) {
                const err = await resp.json();
                alert(err.error || 'Save failed');
                return;
            }
```

Check the real name and signature of the edit-modal opener before writing this —
`openModal(id)` is the assumed name. Grep `static/js/knowledge.js` for the function the
edit button calls and use that.

- [ ] **Step 3: Report skipped entries in the 🎓 toast**

In `static/js/conversation.js`, replace the `else` branch of the toast block:

```javascript
        } else if (data.skipped) {
            showNotification(
                i18n.t('conversation.knowledge.savedWithSkipped')
                    .replace('{count}', data.saved)
                    .replace('{skipped}', data.skipped),
                'success', 4000
            );
        } else {
            showNotification(
                i18n.t('conversation.knowledge.saved').replace('{count}', data.saved),
                'success', 4000
            );
        }
```

Note the existing `data.saved === 0` branch above it still wins when nothing was found.
When everything was a duplicate, `saved` is 0 and the "nothing found" toast shows — that
is misleading. Change that branch's condition to `data.saved === 0 && !data.skipped` so
the all-duplicates case falls through to the skipped message.

- [ ] **Step 4: Bump the three cache-busters**

`knowledge.html` `?v=9` → `?v=10`, `base.html` `?v=39` → `?v=40`,
`conversation.html` `?v=38` → `?v=39`.

- [ ] **Step 5: Verify by hand**

Restart the server (kill the old process first — `Start_Server.bat` does not).

1. Wissensdatenbank → new entry with the label of an existing one in the same category → confirm dialog appears naming it; accepting opens that entry.
2. Same label, different category → saves normally.
3. Open an existing entry, change only its value, save → succeeds.
4. 🎓 on a message whose facts are already stored → toast reads "0 gespeichert, N bereits bekannt", not "nichts gefunden".
5. Repeat 1 and 4 with the language switched to English.

- [ ] **Step 6: Commit**

```bash
git add static/js/knowledge.js static/js/conversation.js static/js/i18n.js \
        templates/chatbot/knowledge.html templates/chatbot/base.html \
        templates/chatbot/conversation.html
git commit -m "feat(knowledge): surface duplicates in the form and the extraction toast"
```

---

## Self-review notes

Spec coverage checked against `docs/superpowers/specs/2026-08-11-knowledge-duplicate-detection-design.md`:

| Spec requirement | Task |
|---|---|
| Normalised label, Python not SQL | 1 |
| Scope = category + property_id + street | 1 |
| Manual create → 409 with existing entry | 2 |
| Update excludes self | 3 |
| 🎓 filters against KB and within batch | 4 |
| 🎓 sets `source='ai'` | 4 |
| Toast reports saved + skipped | 5 |
| Form offers to open the existing entry | 5 |
| No street handling added to the form | Global constraint, Task 2 |
| Tests 1-7 from the spec | 1 (1-4), 3 (5), 4 (6-7) |

Two assumptions the implementer must verify rather than trust, both flagged in place:
`api_update_knowledge`'s local variable names (Task 3, Step 3) and the knowledge modal
opener's real name (Task 5, Step 2).
