# Scoped + German Knowledge Save from the 🎓 Button — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a host choose Room / Street / General scope when saving knowledge via the 🎓 button, and make the AI extraction write entries in German.

**Architecture:** Add a `street` column to `Property` (from Smoobu) and to `KnowledgeEntry` (the new scope key). The 🎓 button opens a scope popup; the extract endpoint resolves the choice to `property_id`/`street`. AI-context retrieval loads general + this-room + this-street entries. The extraction prompt is told to output German.

**Tech Stack:** Flask blueprint (ChatBotAI), SQLAlchemy + Flask-Migrate (Alembic), Jinja templates, vanilla JS, Ollama (extraction), pytest + `node --check`.

## Global Constraints

- **Only the 🎓 flow** (`api_extract_knowledge_from_message` + `conversation.js`). Do NOT touch the manual Add-entry form on the Wissensdatenbank page.
- **Grouping key = exact Smoobu `location.street` string** (incl. house number, e.g. `"Hertigswalder Str. 27"`). Rooms group only on an exact match.
- **Three scopes:** Room = `property_id=<id>, street=NULL`; Street = `property_id=NULL, street=<str>`; General = `property_id=NULL, street=NULL`.
- **New columns are nullable, additive.** Migration revises head `p20_problem_report`; next revision id `p21_knowledge_street`.
- Existing English entries are left untouched. Only new saves are German.
- Static JS is cache-busted with `?v=NN` query strings; no JS test harness in repo — frontend uses `node --check` + manual verification.

---

### Task 1: `street` columns, helper, and migration

**Files:**
- Modify: `ChatBotAI/models.py` (Property + KnowledgeEntry columns, both `to_dict`, new `street_from_address` helper)
- Create: `ChatBotAI/migrations/versions/p21_knowledge_street.py`
- Test: `ChatBotAI/tests/test_knowledge_street.py`

**Interfaces:**
- Produces `Property.street` (str|None), `KnowledgeEntry.street` (str|None), and module-level `street_from_address(address: str|None) -> str` (used by the migration backfill).

- [ ] **Step 1: Write the failing test**

Create `ChatBotAI/tests/test_knowledge_street.py`:

```python
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Property, KnowledgeEntry, street_from_address


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def test_street_from_address():
    assert street_from_address('Hertigswalder Str. 27, 01855, Sebnitz, Germany') == 'Hertigswalder Str. 27'
    assert street_from_address('Bergblick 11, 01855, Lichtenhain') == 'Bergblick 11'
    assert street_from_address('') == ''
    assert street_from_address(None) == ''


def test_street_columns_persist(app):
    p = Property(name='F3', address='Hertigswalder Str. 27, 01855, Sebnitz', street='Hertigswalder Str. 27')
    db.session.add(p); db.session.commit()
    k = KnowledgeEntry(category='general', label='Müll', value='Dienstags', street='Hertigswalder Str. 27')
    db.session.add(k); db.session.commit()
    assert Property.query.first().street == 'Hertigswalder Str. 27'
    got = KnowledgeEntry.query.first()
    assert got.street == 'Hertigswalder Str. 27'
    assert got.to_dict()['street'] == 'Hertigswalder Str. 27'
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_knowledge_street.py -v`
Expected: FAIL — `ImportError: cannot import name 'street_from_address'` (and no `street` column).

- [ ] **Step 3: Add the helper and columns**

In `ChatBotAI/models.py`, add a module-level helper near the top (after imports, before the models):

```python
def street_from_address(address):
    """The street/building key is the first comma-part of a Smoobu address
    ('street, zip, city, country'). Used to backfill Property.street."""
    return (address or '').split(',')[0].strip()
```

In `class Property`, add the column right after `address` (line ~456):

```python
    street = db.Column(db.String(200), nullable=True)  # Smoobu location.street; building key
```

In `Property.to_dict` (line ~490), add after `'address': self.address,`:

```python
            'street': self.street,
```

In `class KnowledgeEntry`, add the column after `value` (line ~654):

```python
    street = db.Column(db.String(200), nullable=True, index=True)  # street-scope key
```

In `KnowledgeEntry.to_dict` (line ~681), add after `'label': self.label,`:

```python
            'street': self.street,
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_knowledge_street.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the migration**

Create `ChatBotAI/migrations/versions/p21_knowledge_street.py`:

```python
"""Add street scope to property and knowledge_entry.

Revision ID: p21_knowledge_street
Revises: p20_problem_report
Create Date: 2026-08-03

Additive. Backfills property.street from the first comma-part of the existing
address so street-scoped knowledge works without waiting for a Smoobu resync.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p21_knowledge_street'
down_revision = 'p20_problem_report'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('property') as batch:
        batch.add_column(sa.Column('street', sa.String(length=200), nullable=True))
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.add_column(sa.Column('street', sa.String(length=200), nullable=True))
    op.create_index('ix_knowledge_entry_street', 'knowledge_entry', ['street'])

    # Backfill property.street from address element 0 ("street, zip, city, country").
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, address FROM property WHERE address IS NOT NULL AND address != ''"
    )).fetchall()
    for row in rows:
        street = (row[1] or '').split(',')[0].strip()
        if street:
            conn.execute(sa.text("UPDATE property SET street=:s WHERE id=:i"),
                         {"s": street, "i": row[0]})


def downgrade():
    op.drop_index('ix_knowledge_entry_street', table_name='knowledge_entry')
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.drop_column('street')
    with op.batch_alter_table('property') as batch:
        batch.drop_column('street')
```

- [ ] **Step 6: Apply the migration to the local DB**

Run (from repo root, using the project's usual Flask-Migrate invocation):
`python -m flask --app ChatBotAI.run db upgrade`
Expected: `Running upgrade p20_problem_report -> p21_knowledge_street`. If your project uses a different `FLASK_APP`, use that; the point is `db upgrade` reaches head `p21_knowledge_street`.

- [ ] **Step 7: Verify the backfill populated real rows**

Run:
```bash
python -c "from ChatBotAI.app import create_app; from ChatBotAI.config import config as c; from ChatBotAI.models import Property; app=create_app(c['production']);\
import sys;\
app.app_context().push();\
rows=[(p.name,p.street) for p in Property.query.filter(Property.street.isnot(None)).limit(5)]; print(rows)"
```
Expected: a non-empty list like `[('F3 - Seb (27)', 'Hertigswalder Str. 27'), ...]`.

- [ ] **Step 8: Commit**

```bash
git add ChatBotAI/models.py ChatBotAI/migrations/versions/p21_knowledge_street.py ChatBotAI/tests/test_knowledge_street.py
git commit -m "feat(knowledge): add street scope columns + backfill migration"
```

---

### Task 2: Populate `Property.street` on Smoobu sync

**Files:**
- Modify: `ChatBotAI/services/smoobu_service.py` (`_extract_property_fields`, ~line 1371)
- Test: `ChatBotAI/tests/test_property_street_sync.py`

**Interfaces:**
- Consumes: nothing from Task 1 at runtime (same `street` column).
- Produces: `_extract_property_fields(apt)` now returns a `'street'` key when the apartment has a street.

- [ ] **Step 1: Write the failing test**

Create `ChatBotAI/tests/test_property_street_sync.py`:

```python
from ChatBotAI.services.smoobu_service import SmoobuService


def test_extract_property_fields_includes_street():
    svc = SmoobuService.__new__(SmoobuService)  # no __init__/network needed
    apt = {'location': {'street': 'Hertigswalder Str. 27', 'zip': '01855', 'city': 'Sebnitz'}}
    fields = svc._extract_property_fields(apt)
    assert fields['street'] == 'Hertigswalder Str. 27'
    assert fields['address'].startswith('Hertigswalder Str. 27')


def test_extract_property_fields_no_street_omits_key():
    svc = SmoobuService.__new__(SmoobuService)
    fields = svc._extract_property_fields({'location': {'city': 'Sebnitz'}})
    assert 'street' not in fields
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_property_street_sync.py -v`
Expected: FAIL — `KeyError: 'street'`.

- [ ] **Step 3: Populate the field**

In `ChatBotAI/services/smoobu_service.py`, in `_extract_property_fields`, right after the address block (after line 1371, `fields['address'] = ', '.join(address_parts)`), add:

```python
        if street:
            fields['street'] = street
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_property_street_sync.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/smoobu_service.py ChatBotAI/tests/test_property_street_sync.py
git commit -m "feat(knowledge): sync Property.street from Smoobu location"
```

---

### Task 3: Street-aware knowledge retrieval

**Files:**
- Modify: `ChatBotAI/services/message_router.py` (~lines 698-714)
- Test: `ChatBotAI/tests/test_knowledge_retrieval_scope.py`

**Interfaces:**
- Consumes: `Property.street`, `KnowledgeEntry.street` (Task 1).
- Produces: the knowledge-loading block now returns general + this-room + this-room's-street entries; general = `property_id IS NULL AND street IS NULL`.

- [ ] **Step 1: Write the failing test**

Create `ChatBotAI/tests/test_knowledge_retrieval_scope.py`. This calls the exact query the router uses, asserting scope isolation:

```python
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Property, KnowledgeEntry


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _load_for_property(property_id):
    """Mirror of message_router's street-aware knowledge query."""
    prop = Property.query.get(property_id)
    prop_street = prop.street if prop else None
    branches = [
        db.and_(KnowledgeEntry.property_id.is_(None), KnowledgeEntry.street.is_(None)),
        KnowledgeEntry.property_id == property_id,
    ]
    if prop_street:
        branches.append(KnowledgeEntry.street == prop_street)
    q = KnowledgeEntry.query.filter(KnowledgeEntry.category != 'correction', db.or_(*branches))
    return {e.label for e in q.all()}


def test_scope_isolation(app):
    f3 = Property(name='F3', street='Hertigswalder Str. 27'); db.session.add(f3)
    b1 = Property(name='B1', street='Bergblick 11'); db.session.add(b1)
    db.session.commit()

    db.session.add_all([
        KnowledgeEntry(category='general', label='general_fact', value='v'),  # scope: general
        KnowledgeEntry(category='general', label='street_fact', value='v', street='Hertigswalder Str. 27'),
        KnowledgeEntry(category='general', label='room_fact', value='v', property_id=f3.id),
    ])
    db.session.commit()

    f3_labels = _load_for_property(f3.id)
    assert f3_labels == {'general_fact', 'street_fact', 'room_fact'}

    b1_labels = _load_for_property(b1.id)
    assert b1_labels == {'general_fact'}  # not street_fact (other building), not room_fact
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_knowledge_retrieval_scope.py -v`
Expected: FAIL — `street` attribute/column missing OR (if Task 1 done) it passes only after the router is updated. Note: this test mirrors the query, so it validates the query shape; it fails before Task 1's columns exist.

- [ ] **Step 3: Update the retrieval block**

In `ChatBotAI/services/message_router.py`, replace the knowledge-loading block (currently lines ~700-714) with:

```python
            if conversation.property_id:
                prop = conversation.property
                prop_street = prop.street if prop else None
                branches = [
                    db.and_(KnowledgeEntry.property_id.is_(None), KnowledgeEntry.street.is_(None)),
                    KnowledgeEntry.property_id == conversation.property_id,
                ]
                if prop_street:
                    branches.append(KnowledgeEntry.street == prop_street)
                knowledge_entries = [e.to_dict() for e in
                                    KnowledgeEntry.query.filter(
                                        KnowledgeEntry.category != 'correction',
                                        db.or_(*branches)
                                    ).order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
            else:
                knowledge_entries = [e.to_dict() for e in
                                    KnowledgeEntry.query.filter(
                                        KnowledgeEntry.category != 'correction',
                                        KnowledgeEntry.property_id.is_(None),
                                        KnowledgeEntry.street.is_(None)
                                    ).order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
```

(The key change: the general branch now also requires `street IS NULL`, so street-scoped entries no longer leak into every conversation, and a street branch is added.)

- [ ] **Step 4: Run the test, verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_knowledge_retrieval_scope.py -v`
Expected: PASS.

- [ ] **Step 5: Run the broader message_router/knowledge tests for regressions**

Run: `python -m pytest ChatBotAI/tests/ -k "knowledge or context or per_message" -q`
Expected: PASS (no regressions from the query change).

- [ ] **Step 6: Commit**

```bash
git add ChatBotAI/services/message_router.py ChatBotAI/tests/test_knowledge_retrieval_scope.py
git commit -m "feat(knowledge): street-aware AI-context retrieval"
```

---

### Task 4: Extract endpoint accepts a `scope`

**Files:**
- Modify: `ChatBotAI/routes.py` (`api_extract_knowledge_from_message`, ~lines 4754-4789)
- Test: `ChatBotAI/tests/test_extract_scope.py`

**Interfaces:**
- Consumes: `Property.street` (Task 1), `ai_service.extract_knowledge_from_message` (unchanged signature).
- Produces: `POST /api/messages/<id>/extract-knowledge` accepts optional JSON `{"scope": "room"|"street"|"general"}` (default `"room"`), and saves entries with the resolved `property_id`/`street`.

- [ ] **Step 1: Write the failing test**

Create `ChatBotAI/tests/test_extract_scope.py`. It stubs the AI so no Ollama is needed:

```python
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, User, Property, Conversation, Message, Guest, KnowledgeEntry
from ChatBotAI.services import ai_service as ai_mod


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app, monkeypatch):
    # Stub the AI extractor to return one fixed entry (no Ollama).
    class FakeAI:
        def extract_knowledge_from_message(self, content):
            return [{'category': 'general', 'label': 'Müll', 'value': 'Dienstags'}]
    monkeypatch.setattr(ai_mod, 'get_ai_service', lambda: FakeAI())

    user = User(username='t', display_name='T', is_admin=True)
    user.set_password('pw'); db.session.add(user); db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id); s['_fresh'] = True
    return c


def _make_conv(street='Hertigswalder Str. 27', with_property=True):
    prop = None
    if with_property:
        prop = Property(name='F3', street=street); db.session.add(prop); db.session.flush()
    guest = Guest(name='G'); db.session.add(guest); db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='airbnb',
                        property_id=prop.id if prop else None)
    db.session.add(conv); db.session.flush()
    msg = Message(conversation_id=conv.id, sender_type='owner', content='Müll dienstags raus')
    db.session.add(msg); db.session.commit()
    return msg


def test_scope_street_saves_with_street_only(app, client):
    msg = _make_conv()
    r = client.post(f'/chatbot/api/messages/{msg.id}/extract-knowledge', json={'scope': 'street'})
    assert r.status_code == 201, r.get_data(as_text=True)
    e = KnowledgeEntry.query.filter_by(label='Müll').first()
    assert e.property_id is None and e.street == 'Hertigswalder Str. 27'


def test_scope_general_saves_global(app, client):
    msg = _make_conv()
    r = client.post(f'/chatbot/api/messages/{msg.id}/extract-knowledge', json={'scope': 'general'})
    assert r.status_code == 201
    e = KnowledgeEntry.query.filter_by(label='Müll').first()
    assert e.property_id is None and e.street is None


def test_scope_room_requires_property(app, client):
    msg = _make_conv(with_property=False)
    r = client.post(f'/chatbot/api/messages/{msg.id}/extract-knowledge', json={'scope': 'room'})
    assert r.status_code == 400


def test_scope_street_requires_property_street(app, client):
    msg = _make_conv(street=None)
    r = client.post(f'/chatbot/api/messages/{msg.id}/extract-knowledge', json={'scope': 'street'})
    assert r.status_code == 400
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_extract_scope.py -v`
Expected: FAIL — the endpoint ignores `scope` (street/general entries save with the conversation's property_id, no `street`).

- [ ] **Step 3: Resolve scope in the endpoint**

In `ChatBotAI/routes.py`, replace the body of `api_extract_knowledge_from_message` between the AI-extraction call and the save loop. The current block (lines ~4767-4787) becomes:

```python
    entries = ai_service.extract_knowledge_from_message(message.content)
    if entries is None:
        return jsonify({'error': 'AI extraction failed'}), 500
    if not entries:
        return jsonify({'saved': 0, 'message': 'No useful knowledge found in this message'}), 200

    # Resolve scope: room (default) | street | general
    data = request.get_json(silent=True) or {}
    scope = data.get('scope', 'room')
    conversation = Conversation.query.get(message.conversation_id)
    prop = Property.query.get(conversation.property_id) if conversation and conversation.property_id else None

    if scope == 'room':
        if not prop:
            return jsonify({'error': 'Kein Zimmer für diese Unterhaltung — nur "Allgemein" möglich.'}), 400
        target_property_id, target_street = prop.id, None
    elif scope == 'street':
        if not prop or not prop.street:
            return jsonify({'error': 'Keine Straße für dieses Zimmer bekannt.'}), 400
        target_property_id, target_street = None, prop.street
    elif scope == 'general':
        target_property_id, target_street = None, None
    else:
        return jsonify({'error': f'Invalid scope: {scope}'}), 400

    saved = []
    for entry in entries:
        ke = KnowledgeEntry(
            property_id=target_property_id,
            street=target_street,
            category=entry['category'],
            label=entry['label'],
            value=entry['value']
        )
        db.session.add(ke)
        saved.append(entry)
    db.session.commit()

    return jsonify({'saved': len(saved), 'entries': saved}), 201
```

(Remove the old `conversation`/`property_id` lines and old save loop this replaces. `Property` and `Conversation` are already imported in routes.py.)

- [ ] **Step 4: Run the test, verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_extract_scope.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/routes.py ChatBotAI/tests/test_extract_scope.py
git commit -m "feat(knowledge): extract endpoint resolves room/street/general scope"
```

---

### Task 5: Extract in German

**Files:**
- Modify: `ChatBotAI/services/ai_service.py` (`extract_knowledge_from_message`, prompt at ~lines 705-734)
- Test: `ChatBotAI/tests/test_extract_german_prompt.py`

**Interfaces:**
- Consumes/produces: same method signature; only the prompt text changes.

- [ ] **Step 1: Write the failing test**

Create `ChatBotAI/tests/test_extract_german_prompt.py`. The extraction output is model-dependent, so we assert the German instruction is present in the prompt the method builds. Capture it by stubbing the HTTP call:

```python
from ChatBotAI.services.ai_service import AIService


def test_prompt_instructs_german(monkeypatch):
    # Build an instance without __init__ (no network); set only what the method reads.
    svc = AIService.__new__(AIService)
    svc.timeout = 30
    svc.reasoning_model = 'test-model'
    captured = {}

    # extract_knowledge_from_message calls self.generate_response(prompt, system=system, ...)
    def fake_generate(prompt, system=None, **kwargs):
        captured['system'] = system or ''
        captured['prompt'] = prompt
        return '[]'
    monkeypatch.setattr(svc, 'generate_response', fake_generate)

    svc.extract_knowledge_from_message('The trash goes out on Tuesday')
    blob = (captured['system'] + captured['prompt']).lower()
    assert 'german' in blob or 'deutsch' in blob
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_extract_german_prompt.py -v`
Expected: FAIL — the current prompt never mentions German.

- [ ] **Step 3: Add the German instruction**

In `ChatBotAI/services/ai_service.py`, in `extract_knowledge_from_message`:

Change the system prompt to end with a German directive:

```python
        system = ("You are a JSON extraction assistant for a vacation rental messaging system. "
                  "Analyze host messages and extract useful knowledge that could help an AI assistant "
                  "answer future guest questions. Write every label and value in GERMAN, regardless of "
                  "the source message language. Respond with ONLY a valid JSON array, no other text.")
```

And add a rule line inside the prompt's `Rules:` block (after the existing rules, before `Return ONLY a valid JSON array:`):

```python
- Write the "label" and "value" in German (translate if the message is in another language)
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_extract_german_prompt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/ai_service.py ChatBotAI/tests/test_extract_german_prompt.py
git commit -m "feat(knowledge): extract knowledge entries in German"
```

---

### Task 6: Scope popup on the 🎓 button

**Files:**
- Modify: `ChatBotAI/templates/chatbot/conversation.html` (add `propertyStreet` to the JS config, ~line 347; bump `conversation.js` `?v=`)
- Modify: `ChatBotAI/static/js/conversation.js` (`extractKnowledge` → open popup, then POST with scope)
- Modify: `ChatBotAI/static/js/i18n.js` (popup strings)

**Interfaces:**
- Consumes: `cfg.currentPropertyId`, `cfg.propertyName`, `cfg.propertyStreet` (template); endpoint `scope` param (Task 4).

- [ ] **Step 1: Pass the street to the frontend**

In `ChatBotAI/templates/chatbot/conversation.html`, after the `propertyName` line (~347) add:

```html
        propertyStreet: {{ (conversation.property.street if conversation.property else "")|tojson }},
```

- [ ] **Step 2: Add the popup + scope wiring in `conversation.js`**

In `ChatBotAI/static/js/conversation.js`, change the 🎓 button to open a scope popup instead of extracting immediately. Replace the `function extractKnowledge(messageId, attempt = 1) {` signature so it takes an explicit scope, and add an opener. At the top of the extract section, add:

```javascript
// 🎓 button: ask Room / Street / General before saving, then extract with that scope.
function openKnowledgeScopePopup(messageId) {
    // Remove any existing popup first.
    const old = document.getElementById('kbScopePopup');
    if (old) old.remove();

    const roomName = cfg.propertyName || '';
    const street = cfg.propertyStreet || '';
    const hasRoom = !!cfg.currentPropertyId;

    const t = (k, d) => (typeof i18n !== 'undefined' && i18n.t(k)) || d;
    let buttons = '';
    if (hasRoom) {
        buttons += `<button class="kb-scope-btn" data-scope="room">`
            + `${t('knowledge.scope.room', 'Nur dieses Zimmer')}`
            + (roomName ? ` <span class="kb-scope-hint">(${roomName})</span>` : '') + `</button>`;
    }
    if (hasRoom && street) {
        buttons += `<button class="kb-scope-btn" data-scope="street">`
            + `${t('knowledge.scope.street', 'Diese Straße')}`
            + ` <span class="kb-scope-hint">(${street})</span></button>`;
    }
    buttons += `<button class="kb-scope-btn" data-scope="general">`
        + `${t('knowledge.scope.general', 'Allgemein')}</button>`;

    const overlay = document.createElement('div');
    overlay.id = 'kbScopePopup';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.45);'
        + 'display:flex;align-items:center;justify-content:center;padding:16px;';
    overlay.innerHTML =
        `<div style="background:var(--card-bg,#fff);color:var(--text,#222);border-radius:12px;`
        + `max-width:420px;width:100%;padding:18px;box-shadow:0 8px 30px rgba(0,0,0,.4);">`
        + `<div style="font-weight:600;margin-bottom:4px;">${t('knowledge.scope.title', 'Wo speichern?')}</div>`
        + `<div style="font-size:.9rem;color:var(--text-secondary,#666);margin-bottom:14px;">`
        + `${t('knowledge.scope.subtitle', 'Für wen gilt diese Information?')}</div>`
        + `<div style="display:flex;flex-direction:column;gap:8px;">${buttons}</div>`
        + `<button id="kbScopeCancel" style="margin-top:14px;background:transparent;border:0;`
        + `color:var(--text-secondary,#666);cursor:pointer;">${t('knowledge.scope.cancel', 'Abbrechen')}</button>`
        + `</div>`;
    document.body.appendChild(overlay);

    overlay.querySelectorAll('.kb-scope-btn').forEach(b => {
        b.style.cssText = 'padding:12px;border:1px solid var(--border,#ccc);border-radius:8px;'
            + 'background:var(--sidebar-bg,#4A1520);color:#fff;cursor:pointer;font-size:.95rem;text-align:left;';
        b.onclick = () => { overlay.remove(); extractKnowledge(messageId, b.dataset.scope); };
    });
    overlay.querySelector('#kbScopeCancel').onclick = () => overlay.remove();
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
}
```

Then change `extractKnowledge` to send the scope. Update its signature and the fetch call:

```javascript
function extractKnowledge(messageId, scope = 'room', attempt = 1) {
```

and the fetch (currently line ~803):

```javascript
    fetch(`/chatbot/api/messages/${messageId}/extract-knowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope })
    })
```

and the retry call (currently line ~835) so it keeps the chosen scope:

```javascript
            setTimeout(() => extractKnowledge(messageId, scope, attempt + 1), 1500);
```

- [ ] **Step 3: Point the button at the popup**

In `ChatBotAI/static/js/conversation.js`, the button render (~line 1134) currently has `onclick="extractKnowledge(${message.id})"`. Change it to:

```javascript
        perMsgActionBtn = `<button class="btn-extract-knowledge" onclick="openKnowledgeScopePopup(${message.id})"`;
```

(Keep the rest of that line — the title/icon — unchanged.)

- [ ] **Step 4: Add the i18n strings**

In `ChatBotAI/static/js/i18n.js`, add to the German block (near the other `knowledge.*` keys, ~line 431):

```javascript
        'knowledge.scope.title': 'Wo speichern?',
        'knowledge.scope.subtitle': 'Für wen gilt diese Information?',
        'knowledge.scope.room': 'Nur dieses Zimmer',
        'knowledge.scope.street': 'Diese Straße',
        'knowledge.scope.general': 'Allgemein',
        'knowledge.scope.cancel': 'Abbrechen',
```

And to the English block (~line 995):

```javascript
        'knowledge.scope.title': 'Where to save?',
        'knowledge.scope.subtitle': 'Who does this apply to?',
        'knowledge.scope.room': 'This room only',
        'knowledge.scope.street': 'This street',
        'knowledge.scope.general': 'General',
        'knowledge.scope.cancel': 'Cancel',
```

- [ ] **Step 5: Bump the cache-bust**

In `ChatBotAI/templates/chatbot/conversation.html`, find the `conversation.js` script tag and increment its `?v=` (e.g. `?v=NN` → `?v=NN+1`). Do the same for `i18n.js` if it carries a `?v=`.

- [ ] **Step 6: Syntax check**

Run: `node --check ChatBotAI/static/js/conversation.js && node --check ChatBotAI/static/js/i18n.js`
Expected: no output (valid).

- [ ] **Step 7: Manual verification (no JS harness in repo)**

Restart the server. Open a conversation whose room has a street (e.g. an F-room):
- Click 🎓 → popup shows **Nur dieses Zimmer (F3)**, **Diese Straße (Hertigswalder Str. 27)**, **Allgemein**.
- Pick **Diese Straße** → success toast; confirm on the Wissensdatenbank page (or DB) the new entry has `street` set and `property_id` NULL, in German.
- Open a conversation with no assigned room → popup shows only **Allgemein**.
- Open a room with no street → **Diese Straße** is hidden.

- [ ] **Step 8: Commit**

```bash
git add ChatBotAI/templates/chatbot/conversation.html ChatBotAI/static/js/conversation.js ChatBotAI/static/js/i18n.js
git commit -m "feat(knowledge): scope popup (room/street/general) on the 🎓 button"
```

---

## Self-Review

**Spec coverage:**
- `Property.street` from Smoobu + backfill → Task 1 (backfill) + Task 2 (sync). ✅
- `KnowledgeEntry.street` scope column + 3-scope model → Task 1. ✅
- Retrieval: general OR room OR street; general = both NULL → Task 3. ✅
- Extract endpoint `scope` param + guard rails → Task 4. ✅
- German extraction → Task 5. ✅
- 🎓 popup labelled with real names, hides unavailable scopes → Task 6. ✅
- Manual Add-entry untouched; existing entries untouched → not modified anywhere. ✅

**Placeholder scan:** none — every code step has full content. The two "adjust if the helper name differs" notes (Task 5) are fallbacks around a real, complete implementation, not placeholders.

**Type/name consistency:** `street_from_address` (Task 1) used by the migration backfill (Task 1). `KnowledgeEntry.street` / `Property.street` consistent across Tasks 1-4. Endpoint `scope` values `room|street|general` match between Task 4 (backend) and Task 6 (`data-scope` buttons). `cfg.propertyStreet` set in Task 6 Step 1 and read in Step 2. `extractKnowledge(messageId, scope, attempt)` signature consistent across its definition, the popup call, and the retry call.
