# KB-Driven Escalation Topics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Eskalation area of the Wissensdatenbank the single, team-editable source of truth for what escalates a conversation — honoured both by the always-on trigger-word matcher and by UMI's own judgement.

**Architecture:** One new nullable column `knowledge_entry.trigger_words` holds comma-separated phrases. The always-on matcher in `MessageRouter` stops reading its hardcoded tuple and reads those rows instead, scoped exactly like every other knowledge entry. The topic *labels* (never the internal notes) are rendered into UMI's guest-reply prompt so she escalates on the same topics when a guest paraphrases. A one-time migration seeds the current hardcoded keywords as 9 editable rows.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate/Alembic, SQLite (WAL), Jinja2 prompt templates, vanilla JS front end, pytest.

**Spec:** `docs/superpowers/specs/2026-08-11-kb-driven-escalation-design.md`

## Global Constraints

- Run tests from the `ChatBotAI` directory: `python -m pytest tests/<file> -q`. The suite imports `ChatBotAI.*`, so the parent `FlaskApp` directory must be on `sys.path` — running from `ChatBotAI` already achieves this. Full runs take ~1 minute.
- **Never run `flask db upgrade` while implementing.** Any `flask db` command in this repo targets the LIVE production database. Write the migration file, verify it by import/inspection only, and leave running it to the user. pytest is safe — the testing config builds a throwaway DB with `create_all()`.
- The escalation category prefix test is `startswith('esc')` everywhere — never `esc_` — so the legacy `escalation` category stays covered. This matches the existing filter at `services/ai_service.py:857`.
- UI strings: German is the default, English is the fallback. Every new user-facing string needs a key in **both** blocks of `static/js/i18n.js`.
- The internal note (`KnowledgeEntry.value`) of an escalation row must never reach the AI prompt. This is the one hard safety rule in this plan.
- Mark deliberate simplifications with a `ponytail:` comment naming the ceiling and the upgrade path.
- Commit after every task.

---

### Task 1: `trigger_words` column and the topic loader

**Files:**
- Modify: `models.py` (class `KnowledgeEntry`, ~line 667-750)
- Test: `tests/test_escalation_topics.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `KnowledgeEntry.trigger_words` — `db.Column(db.Text, nullable=True)`
  - `KnowledgeEntry.parse_trigger_words(raw: str | None) -> list[str]` (staticmethod) — lowercased, stripped, de-duplicated, order preserved, empties dropped
  - `KnowledgeEntry.load_escalation_topics(conversation) -> list[tuple[str, list[str]]]` (classmethod) — `[(label, [word, …]), …]`, scope-filtered, rows with no usable words omitted
  - `KnowledgeEntry._scope_filter(conversation)` (classmethod) — SQLAlchemy clause, extracted from the existing `load_for_conversation_context`
  - `to_dict()` gains a `'trigger_words'` key

- [ ] **Step 1: Write the failing test**

Create `tests/test_escalation_topics.py`:

```python
"""Eskalation topics: the team-editable rows that decide what escalates.

The trigger words used to be a hardcoded tuple in MessageRouter. They now live
in the Wissensdatenbank so the team can add, edit and delete them without a
code change. These tests pin the parsing and the scope rules.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Conversation, Guest, KnowledgeEntry, Property


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _conversation(property_id=None):
    guest = Guest(name='T', email=f'g{property_id}@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', property_id=property_id)
    db.session.add(conv)
    db.session.commit()
    return conv


def _topic(label, words, category='esc_access', property_id=None, street=None, value=''):
    entry = KnowledgeEntry(category=category, label=label, value=value,
                           trigger_words=words, property_id=property_id, street=street)
    db.session.add(entry)
    db.session.commit()
    return entry


def test_parse_splits_lowercases_and_dedupes():
    assert KnowledgeEntry.parse_trigger_words(
        ' Ausgesperrt , locked out,,  AUSGESPERRT , '
    ) == ['ausgesperrt', 'locked out']


def test_parse_handles_empty():
    assert KnowledgeEntry.parse_trigger_words(None) == []
    assert KnowledgeEntry.parse_trigger_words('') == []
    assert KnowledgeEntry.parse_trigger_words(' , , ') == []


def test_load_returns_label_and_words(app):
    conv = _conversation()
    _topic('Aussperrung', 'ausgesperrt, locked out')
    assert KnowledgeEntry.load_escalation_topics(conv) == [
        ('Aussperrung', ['ausgesperrt', 'locked out'])
    ]


def test_load_skips_rows_without_words(app):
    conv = _conversation()
    _topic('Leer', '')
    _topic('Auch leer', None)
    assert KnowledgeEntry.load_escalation_topics(conv) == []


def test_load_ignores_non_escalation_categories(app):
    conv = _conversation()
    _topic('WLAN', 'wlan, wifi', category='general')
    assert KnowledgeEntry.load_escalation_topics(conv) == []


def test_load_includes_legacy_escalation_category(app):
    conv = _conversation()
    _topic('Alt', 'altwort', category='escalation')
    assert KnowledgeEntry.load_escalation_topics(conv) == [('Alt', ['altwort'])]


def test_property_scoped_topic_does_not_leak_to_other_property(app):
    prop_a = Property(name='A', street='Hauptstr.')
    prop_b = Property(name='B', street='Nebenstr.')
    db.session.add_all([prop_a, prop_b])
    db.session.commit()

    _topic('Nur A', 'nurawort', property_id=prop_a.id)

    conv_a = _conversation(property_id=prop_a.id)
    conv_b = _conversation(property_id=prop_b.id)

    assert KnowledgeEntry.load_escalation_topics(conv_a) == [('Nur A', ['nurawort'])]
    assert KnowledgeEntry.load_escalation_topics(conv_b) == []


def test_street_scoped_topic_reaches_properties_on_that_street(app):
    prop = Property(name='A', street='Hauptstr.')
    db.session.add(prop)
    db.session.commit()

    _topic('Strasse', 'strassenwort', street='Hauptstr.')
    conv = _conversation(property_id=prop.id)

    assert KnowledgeEntry.load_escalation_topics(conv) == [('Strasse', ['strassenwort'])]


def test_global_topic_reaches_a_conversation_without_property(app):
    conv = _conversation()
    _topic('Global', 'globalwort')
    assert KnowledgeEntry.load_escalation_topics(conv) == [('Global', ['globalwort'])]


def test_to_dict_exposes_trigger_words(app):
    entry = _topic('Aussperrung', 'ausgesperrt')
    assert entry.to_dict()['trigger_words'] == 'ausgesperrt'
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_escalation_topics.py -q`
Expected: FAIL — `TypeError: 'trigger_words' is an invalid keyword argument for KnowledgeEntry` and `AttributeError: type object 'KnowledgeEntry' has no attribute 'parse_trigger_words'`.

- [ ] **Step 3: Add the column and the `trigger_words` key to `to_dict()`**

In `models.py`, in `class KnowledgeEntry`, directly after the `value` column:

```python
    value = db.Column(db.Text, nullable=False)
    # Comma-separated trigger phrases, escalation categories only. Substring
    # matched (case-insensitive) against incoming guest messages by
    # MessageRouter._match_escalation_topic. NULL/empty = topic never fires.
    trigger_words = db.Column(db.Text, nullable=True)
```

In `to_dict()`, after the `'value'` key:

```python
            'value': self.value,
            'trigger_words': self.trigger_words,
```

- [ ] **Step 4: Extract the scope filter and add the topic loader**

In `models.py`, replace the body of `load_for_conversation_context` and add the two new
helpers. The full replacement for the existing classmethod plus its new neighbours:

```python
    @classmethod
    def _scope_filter(cls, conversation):
        """Rows visible to this conversation: global + its room + its street.

        Single source of truth for KB scope — every AI-context and escalation
        loader must use it so street-scoped rows never leak across buildings."""
        if conversation.property_id:
            prop = conversation.property
            prop_street = prop.street if prop else None
            branches = [
                db.and_(cls.property_id.is_(None), cls.street.is_(None)),
                cls.property_id == conversation.property_id,
            ]
            if prop_street:
                branches.append(cls.street == prop_street)
            return db.or_(*branches)
        return db.and_(cls.property_id.is_(None), cls.street.is_(None))

    @staticmethod
    def parse_trigger_words(raw):
        """Comma-separated trigger phrases -> lowercased, de-duplicated list."""
        if not raw:
            return []
        words = []
        for part in raw.split(','):
            word = part.strip().lower()
            if word and word not in words:
                words.append(word)
        return words

    @classmethod
    def load_escalation_topics(cls, conversation):
        """[(label, [word, ...]), ...] for this conversation's scope.

        Only rows in an escalation category with usable trigger words. The
        internal note (``value``) is deliberately not returned — it is for the
        team and must never reach the AI."""
        rows = (cls.query
                .filter(cls.category.like('esc%'))
                .filter(cls._scope_filter(conversation))
                .order_by(cls.category, cls.sort_order)
                .all())
        topics = []
        for row in rows:
            words = cls.parse_trigger_words(row.trigger_words)
            if words:
                topics.append((row.label, words))
        return topics

    @classmethod
    def load_for_conversation_context(cls, conversation):
        """Knowledge entries the AI may see for this conversation, scope-ordered:
        general (property_id NULL AND street NULL) + this room + this room's street.
        Excludes corrections. Returns a list of to_dict() dicts."""
        q = (cls.query
             .filter(cls.category != 'correction')
             .filter(cls._scope_filter(conversation)))
        return [e.to_dict() for e in q.order_by(cls.category, cls.sort_order).all()]
```

Note: `like('esc%')` also matches the legacy `escalation` category, which is intended.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_escalation_topics.py -q`
Expected: PASS, 10 tests.

- [ ] **Step 6: Run the existing knowledge/scope tests for regressions**

Run: `python -m pytest tests/ -q -k "knowledge or scope or context_filter"`
Expected: PASS. `load_for_conversation_context` was refactored, not changed in behaviour.

- [ ] **Step 7: Commit**

```bash
git add models.py tests/test_escalation_topics.py
git commit -m "feat(escalation): add trigger_words column and KB topic loader"
```

---

### Task 2: Migration p23 — column plus seed of the current keywords

**Files:**
- Create: `migrations/versions/p23_knowledge_trigger_words.py`
- Test: `tests/test_escalation_seed.py` (create)

**Interfaces:**
- Consumes: `KnowledgeEntry.trigger_words` from Task 1.
- Produces: module-level `SEED_TOPICS` in the migration — a tuple of `(category, label, trigger_words)` triples, importable by the test.

No migration in this repo imports application code, so the seed data lives in the
migration file and the test reaches it by path. Keep it that way.

- [ ] **Step 1: Write the failing test**

Create `tests/test_escalation_seed.py`:

```python
"""The p23 seed must carry over every keyword the hardcoded list used to match.

MessageRouter._URGENT_KEYWORDS is deleted in a later task, so this file keeps a
frozen copy of it as of 2026-08-11. If a word is missing from the seed, a guest
message that escalated yesterday would stop escalating after the migration.
"""

import importlib.util
from pathlib import Path

MIGRATION = (Path(__file__).resolve().parents[1]
             / 'migrations' / 'versions' / 'p23_knowledge_trigger_words.py')

# Frozen copy of MessageRouter._URGENT_KEYWORDS as of 2026-08-11.
LEGACY_KEYWORDS = (
    'notfall', 'notarzt', 'feuer', 'brennt', 'polizei', 'rettungsdienst',
    'einbruch', 'unfall', 'verletzt', 'gasgeruch',
    'wasserschaden', 'überschwemmt', 'überflutet', 'rohrbruch', 'schimmel',
    'kein warmwasser', 'kein wasser', 'kein strom', 'stromausfall',
    'heizung defekt', 'heizung geht nicht', 'heizung kaputt', 'kaputt',
    'funktioniert nicht', 'defekt',
    'ausgesperrt', 'eingesperrt', 'komme nicht rein', 'schlüssel verloren',
    'code funktioniert nicht', 'türe geht nicht', 'tür geht nicht',
    'anwalt', 'rechtsanwalt', 'beschwerde', 'beschweren', 'rückerstattung',
    'geld zurück', 'stornieren', 'storno', 'abbrechen',
    'lärm', 'laut', 'polizei gerufen', 'dreckig', 'schmutzig', 'ungeziefer',
    'bettwanzen', 'kakerlaken',
    'emergency', 'urgent', 'asap', 'fire', 'police', 'ambulance', 'injured',
    'flood', 'flooded', 'water damage', 'leak', 'mold', 'no hot water',
    'no water', 'no power', 'no electricity', 'heating not working',
    'broken', 'not working', 'locked out', 'lost the key', 'lost my key',
    'code does not work', "code doesn't work",
    'lawyer', 'complaint', 'refund', 'money back', 'cancel my booking',
    'bed bugs', 'cockroach', 'filthy', 'dirty',
)


def _seed_topics():
    spec = importlib.util.spec_from_file_location('p23_seed', MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SEED_TOPICS


def test_seed_has_nine_topics():
    assert len(_seed_topics()) == 9


def test_every_topic_has_a_category_label_and_words():
    for category, label, words in _seed_topics():
        assert category.startswith('esc'), category
        assert label.strip(), category
        assert [w.strip() for w in words.split(',') if w.strip()], label


def test_no_legacy_keyword_is_lost():
    seeded = set()
    for _category, _label, words in _seed_topics():
        seeded.update(w.strip().lower() for w in words.split(',') if w.strip())
    assert set(LEGACY_KEYWORDS) - seeded == set()


def test_no_keyword_is_seeded_twice():
    seen, duplicates = set(), set()
    for _category, _label, words in _seed_topics():
        for word in (w.strip().lower() for w in words.split(',') if w.strip()):
            if word in seen:
                duplicates.add(word)
            seen.add(word)
    assert duplicates == set()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_escalation_seed.py -q`
Expected: FAIL — `FileNotFoundError` / `spec_from_file_location` returns `None` because the migration does not exist yet.

- [ ] **Step 3: Write the migration**

Create `migrations/versions/p23_knowledge_trigger_words.py`:

```python
"""Add trigger_words to knowledge_entry and seed the Eskalation topics.

Revision ID: p23_knowledge_trigger_words
Revises: p22_smoobu_multi_account
Create Date: 2026-08-11

The escalation trigger words used to be a hardcoded tuple in MessageRouter,
invisible and uneditable for the team. They move into the Wissensdatenbank as
nine topic rows so the team owns them.

Additive: one nullable column plus nine global rows. The seed is skipped when
any escalation row already carries trigger words, so re-running is safe.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p23_knowledge_trigger_words'
down_revision = 'p22_smoobu_multi_account'
branch_labels = None
depends_on = None

# (category, label, comma-separated trigger words)
SEED_TOPICS = (
    ('esc_emergency', 'Notfall',
     'notfall, notarzt, feuer, brennt, polizei, rettungsdienst, einbruch, '
     'unfall, verletzt, gasgeruch, emergency, urgent, asap, fire, police, '
     'ambulance, injured'),
    ('esc_maintenance', 'Wasserschaden / Schimmel',
     'wasserschaden, überschwemmt, überflutet, rohrbruch, schimmel, flood, '
     'flooded, water damage, leak, mold'),
    ('esc_maintenance', 'Kein Wasser / Strom / Heizung',
     'kein warmwasser, kein wasser, kein strom, stromausfall, heizung defekt, '
     'heizung geht nicht, heizung kaputt, no hot water, no water, no power, '
     'no electricity, heating not working'),
    # Broad, generic words — deliberately their own row so the team can delete
    # them without losing the specific topics above.
    ('esc_maintenance', 'Defekt / kaputt',
     'kaputt, funktioniert nicht, defekt, broken, not working'),
    ('esc_access', 'Aussperrung / Zugang',
     'ausgesperrt, eingesperrt, komme nicht rein, schlüssel verloren, '
     'code funktioniert nicht, türe geht nicht, tür geht nicht, locked out, '
     "lost the key, lost my key, code does not work, code doesn't work"),
    ('esc_payment', 'Zahlung / Erstattung',
     'rückerstattung, geld zurück, stornieren, storno, abbrechen, refund, '
     'money back, cancel my booking'),
    ('esc_other', 'Beschwerde / Rechtliches',
     'anwalt, rechtsanwalt, beschwerde, beschweren, lawyer, complaint'),
    ('esc_noise', 'Lärm',
     'lärm, laut, polizei gerufen'),
    ('esc_cleanliness', 'Sauberkeit / Ungeziefer',
     'dreckig, schmutzig, ungeziefer, bettwanzen, kakerlaken, bed bugs, '
     'cockroach, filthy, dirty'),
)


def upgrade():
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.add_column(sa.Column('trigger_words', sa.Text(), nullable=True))

    conn = op.get_bind()
    already = conn.execute(sa.text(
        "SELECT COUNT(*) FROM knowledge_entry "
        "WHERE category LIKE 'esc%' AND trigger_words IS NOT NULL "
        "AND TRIM(trigger_words) != ''"
    )).scalar()
    if already:
        return

    for sort_order, (category, label, words) in enumerate(SEED_TOPICS, start=1):
        conn.execute(
            sa.text(
                "INSERT INTO knowledge_entry "
                "(property_id, category, label, value, street, sort_order, "
                " source, trigger_words, created_at, updated_at) "
                "VALUES (NULL, :category, :label, '', NULL, :sort_order, "
                " 'manual', :words, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {'category': category, 'label': label,
             'sort_order': sort_order, 'words': words},
        )


def downgrade():
    conn = op.get_bind()
    for _category, label, _words in SEED_TOPICS:
        conn.execute(
            sa.text("DELETE FROM knowledge_entry "
                    "WHERE label = :label AND property_id IS NULL"),
            {'label': label},
        )
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.drop_column('trigger_words')
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_escalation_seed.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 5: Verify the revision chain without touching the database**

Run: `python -c "import importlib.util,pathlib; s=importlib.util.spec_from_file_location('m', pathlib.Path('migrations/versions/p23_knowledge_trigger_words.py')); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.revision, '<-', m.down_revision)"`
Expected: `p23_knowledge_trigger_words <- p22_smoobu_multi_account`

Do **not** run `flask db upgrade` — it would write to the production database.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/p23_knowledge_trigger_words.py tests/test_escalation_seed.py
git commit -m "feat(escalation): migration p23 — trigger_words column + seed 9 topics"
```

---

### Task 3: Swap the always-on matcher over to the KB

**Files:**
- Modify: `services/message_router.py:555-597` (delete `_URGENT_KEYWORDS` and `_urgent_keyword`, add `_match_escalation_topic`) and `services/message_router.py:216-232` (call site)
- Test: `tests/test_urgency_triage.py` (rewrite the keyword-list portions)

**Interfaces:**
- Consumes: `KnowledgeEntry.load_escalation_topics(conversation)` from Task 1.
- Produces: `MessageRouter._match_escalation_topic(conversation, text) -> tuple[str, str] | None` returning `(label, matched_word)`.
- Removed: `MessageRouter._URGENT_KEYWORDS`, `MessageRouter._urgent_keyword`. Nothing else references them — confirm with `grep -rn "_urgent_keyword\|_URGENT_KEYWORDS" --include=*.py .` before deleting.

- [ ] **Step 1: Write the failing test**

Replace the whole contents of `tests/test_urgency_triage.py`:

```python
"""Guest-side urgency triage — escalation that does not depend on UMI.

The AI's ``[[ESCALATE]]`` marker and the phrase backstop only run when UMI
generates a reply. With ``master_ai_enabled=false`` (the live state) nothing
would ever be flagged, so an important guest message must be caught on the way
in, no matter who is in charge of the chat.

Since 2026-08-11 the trigger words come from the Eskalation area of the
Wissensdatenbank, not from a hardcoded list. These tests pin that wiring, the
recency gate that keeps a historical Smoobu resync from flagging thousands of
closed stays, and the rule that a trigger word never pauses auto-respond.
"""

from datetime import datetime, timedelta

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, AISettings, Conversation, Guest, KnowledgeEntry, Property
from ChatBotAI.services.message_router import MessageRouter, get_message_router


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _topic(label, words, category='esc_maintenance', property_id=None):
    db.session.add(KnowledgeEntry(category=category, label=label, value='',
                                  trigger_words=words, property_id=property_id))
    db.session.commit()


def _conversation(property_id=None, auto_respond=False):
    guest = Guest(name='G', email=f'g{datetime.utcnow().timestamp()}@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu',
                        property_id=property_id, auto_respond=auto_respond)
    db.session.add(conv)
    db.session.commit()
    return conv


def test_matches_a_trigger_word_case_insensitively(app):
    conv = _conversation()
    _topic('Wasserschaden', 'wasserschaden, water damage')
    assert MessageRouter._match_escalation_topic(
        conv, 'Hallo, wir haben einen WASSERSCHADEN im Bad!'
    ) == ('Wasserschaden', 'wasserschaden')


def test_ordinary_message_does_not_match(app):
    conv = _conversation()
    _topic('Wasserschaden', 'wasserschaden, water damage')
    assert MessageRouter._match_escalation_topic(
        conv, 'Hallo, wann können wir einchecken?'
    ) is None


def test_empty_message_does_not_match(app):
    conv = _conversation()
    _topic('Wasserschaden', 'wasserschaden')
    assert MessageRouter._match_escalation_topic(conv, '') is None
    assert MessageRouter._match_escalation_topic(conv, None) is None


def test_no_topics_means_nothing_matches(app):
    """The team can empty the Eskalation area — then nothing escalates."""
    conv = _conversation()
    assert MessageRouter._match_escalation_topic(
        conv, 'Hilfe, wir haben einen Wasserschaden!'
    ) is None


def test_deleting_the_topic_stops_the_match(app):
    conv = _conversation()
    _topic('Wasserschaden', 'wasserschaden')
    entry = KnowledgeEntry.query.filter_by(label='Wasserschaden').one()
    db.session.delete(entry)
    db.session.commit()
    assert MessageRouter._match_escalation_topic(
        conv, 'Hilfe, Wasserschaden!'
    ) is None


def test_property_scoped_topic_does_not_fire_elsewhere(app):
    prop_a = Property(name='A', street='Hauptstr.')
    prop_b = Property(name='B', street='Nebenstr.')
    db.session.add_all([prop_a, prop_b])
    db.session.commit()

    _topic('Nur A', 'sonderfall', property_id=prop_a.id)

    assert MessageRouter._match_escalation_topic(
        _conversation(property_id=prop_a.id), 'Das ist ein Sonderfall'
    ) == ('Nur A', 'sonderfall')
    assert MessageRouter._match_escalation_topic(
        _conversation(property_id=prop_b.id), 'Das ist ein Sonderfall'
    ) is None


def test_triage_flags_conversation_when_ai_is_off(app, monkeypatch):
    """The whole point: master AI off, auto_respond off — still escalated."""
    AISettings.set('master_ai_enabled', 'false')
    _topic('Wasserschaden', 'wasserschaden')

    router = get_message_router()
    monkeypatch.setattr(router, 'memory_service', None)

    result = router.process_incoming_message(
        platform='smoobu',
        platform_conversation_id='smoobu-urgency-1',
        sender_name='Urgent Guest',
        message_content='Hilfe, wir haben einen Wasserschaden!',
        auto_respond=False,
        skip_push=True,
    )
    conv = db.session.get(Conversation, result['conversation_id'])
    assert conv.escalated is True


def test_triage_does_not_flag_without_matching_topic(app, monkeypatch):
    router = get_message_router()
    monkeypatch.setattr(router, 'memory_service', None)

    result = router.process_incoming_message(
        platform='smoobu',
        platform_conversation_id='smoobu-urgency-3',
        sender_name='Calm Guest',
        message_content='Hilfe, wir haben einen Wasserschaden!',
        auto_respond=False,
        skip_push=True,
    )
    conv = db.session.get(Conversation, result['conversation_id'])
    assert conv.escalated is False


def test_triage_does_not_pause_auto_respond(app):
    """A false-positive trigger word may not silently switch a chat's AI off
    for good — only the AI's own escalation path pauses auto-respond."""
    conv = _conversation(auto_respond=True)
    get_message_router()._apply_escalation(conv, 'topic:Test (test)', pause_ai=False)
    assert conv.escalated is True
    assert db.session.get(Conversation, conv.id).auto_respond is True


def test_historical_message_is_not_flagged(app, monkeypatch):
    """A full resync replays old threads — those must not escalate."""
    _topic('Defekt', 'kaputt')

    router = get_message_router()
    monkeypatch.setattr(router, 'memory_service', None)

    result = router.process_incoming_message(
        platform='smoobu',
        platform_conversation_id='smoobu-urgency-2',
        sender_name='Old Guest',
        message_content='Die Heizung ist kaputt!',
        auto_respond=False,
        skip_push=True,
        sent_at=datetime.utcnow() - timedelta(days=30),
    )
    conv = db.session.get(Conversation, result['conversation_id'])
    assert conv.escalated is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_urgency_triage.py -q`
Expected: FAIL — `AttributeError: type object 'MessageRouter' has no attribute '_match_escalation_topic'`.

- [ ] **Step 3: Replace the keyword tuple with the KB matcher**

In `services/message_router.py`, delete the whole `_URGENT_KEYWORDS` tuple and the
`_urgent_keyword` classmethod (lines ~555-597, from the `# Guest-side urgency triage.`
comment block down to and including the `return next(...)` line) and put this in their place:

```python
    # Guest-side urgency triage. Runs on EVERY incoming message regardless of
    # who is in charge of the chat (UMI, a human, master AI off) — an important
    # message must surface even when no AI ever looks at it.
    #
    # The trigger words live in the Eskalation area of the Wissensdatenbank so
    # the team owns them: they can add, edit and delete topics without a code
    # change. Empty Eskalation area = nothing escalates by trigger word, which
    # is the deliberate trade for making the behaviour visible on screen.
    @staticmethod
    def _match_escalation_topic(conversation, text):
        """(topic label, matched word) for the first Eskalation topic whose
        trigger words appear in the message, else None.

        ponytail: one SELECT per recent incoming message (~150/day) and a plain
        substring scan. Cache the topics per property if message volume ever
        makes this show up in a profile."""
        if not text:
            return None
        lowered = text.lower()
        for label, words in KnowledgeEntry.load_escalation_topics(conversation):
            for word in words:
                if word in lowered:
                    return label, word
        return None
```

`KnowledgeEntry` is already imported at `services/message_router.py:19`.

- [ ] **Step 4: Update the call site**

In `services/message_router.py`, in `process_incoming_message` Step 6.6, replace:

```python
                    keyword = self._urgent_keyword(message_content)
                    if keyword:
                        self._apply_escalation(conversation, f'keyword:{keyword}',
                                               pause_ai=False)
                        result['escalated'] = True
```

with:

```python
                    hit = self._match_escalation_topic(conversation, message_content)
                    if hit:
                        label, word = hit
                        self._apply_escalation(conversation,
                                               f'topic:{label} ({word})',
                                               pause_ai=False)
                        result['escalated'] = True
```

Leave the surrounding `is_recent` / `not conversation.escalated` guard and the
`try/except` exactly as they are.

- [ ] **Step 5: Confirm nothing else referenced the deleted names**

Run: `grep -rn "_urgent_keyword\|_URGENT_KEYWORDS" --include=*.py .`
Expected: no output.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_urgency_triage.py tests/test_escalation_topics.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/message_router.py tests/test_urgency_triage.py
git commit -m "feat(escalation): drive urgency triage from KB topics, drop hardcoded list"
```

---

### Task 4: API accepts `trigger_words`, and `value` becomes optional for escalation rows

**Files:**
- Modify: `routes.py:4991-5035` (`api_create_knowledge`) and `routes.py:5039-5087` (`api_update_knowledge`)
- Test: `tests/test_knowledge_trigger_words_api.py` (create)

**Interfaces:**
- Consumes: `KnowledgeEntry.trigger_words` from Task 1.
- Produces: `POST` and `PUT /chatbot/api/knowledge` accept an optional `trigger_words` string (max 2000 chars; blank stored as `NULL`), and skip the "Value is required" check when the category starts with `esc`.

This is what unblocks saving an Eskalation entry at all — today the API rejects the empty
`value` the escalation form sends.

- [ ] **Step 1: Write the failing test**

Create `tests/test_knowledge_trigger_words_api.py`:

```python
"""The knowledge API must accept escalation topics.

Before 2026-08-11 an Eskalation entry could not be saved: the form hides the
Information field but the API required a non-empty value. Escalation rows now
save without a note, and carry trigger words.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, KnowledgeEntry, User


@pytest.fixture
def client():
    app = create_app(config_map['testing'])
    with app.app_context():
        user = User(username='tester', is_admin=True)
        user.set_password('pw')
        db.session.add(user)
        db.session.commit()
        with app.test_client() as client:
            client.post('/chatbot/login',
                        data={'username': 'tester', 'password': 'pw'},
                        follow_redirects=True)
            yield client
        db.session.remove()
        db.drop_all()


def test_create_escalation_entry_without_value(client):
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'esc_access',
        'label': 'Aussperrung',
        'value': '',
        'trigger_words': 'ausgesperrt, locked out',
    })
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()['trigger_words'] == 'ausgesperrt, locked out'


def test_create_normal_entry_still_requires_value(client):
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'general',
        'label': 'WLAN',
        'value': '',
    })
    assert resp.status_code == 400
    assert 'Value is required' in resp.get_json()['error']


def test_blank_trigger_words_are_stored_as_null(client):
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'esc_noise',
        'label': 'Lärm',
        'value': '',
        'trigger_words': '   ',
    })
    assert resp.status_code == 201
    assert resp.get_json()['trigger_words'] is None


def test_trigger_words_over_2000_chars_are_rejected(client):
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'esc_noise',
        'label': 'Lärm',
        'value': '',
        'trigger_words': 'x' * 2001,
    })
    assert resp.status_code == 400


def test_update_sets_trigger_words(client):
    created = client.post('/chatbot/api/knowledge', json={
        'category': 'esc_access', 'label': 'Aussperrung', 'value': '',
        'trigger_words': 'ausgesperrt',
    }).get_json()

    resp = client.put(f"/chatbot/api/knowledge/{created['id']}",
                      json={'trigger_words': 'ausgesperrt, locked out'})
    assert resp.status_code == 200
    assert resp.get_json()['trigger_words'] == 'ausgesperrt, locked out'


def test_update_can_clear_the_internal_note_on_an_escalation_entry(client):
    created = client.post('/chatbot/api/knowledge', json={
        'category': 'esc_access', 'label': 'Aussperrung',
        'value': 'Hausmeister anrufen', 'trigger_words': 'ausgesperrt',
    }).get_json()

    resp = client.put(f"/chatbot/api/knowledge/{created['id']}", json={'value': ''})
    assert resp.status_code == 200
    assert resp.get_json()['value'] == ''
```

If the login route or `User` constructor differs, mirror whatever an existing
authenticated API test in `tests/` does — do not invent a new auth path.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_knowledge_trigger_words_api.py -q`
Expected: FAIL — `test_create_escalation_entry_without_value` returns 400 "Value is required".

- [ ] **Step 3: Update `api_create_knowledge`**

In `routes.py`, inside `api_create_knowledge`, replace:

```python
    if not value:
        return jsonify({'error': 'Value is required'}), 400
    if len(value) > 2000:
        return jsonify({'error': 'Value must be 2000 characters or less'}), 400
```

with:

```python
    # Escalation topics are category + label + trigger words; the note is
    # optional. Every other category still needs its information text.
    if not value and not category.startswith('esc'):
        return jsonify({'error': 'Value is required'}), 400
    if len(value) > 2000:
        return jsonify({'error': 'Value must be 2000 characters or less'}), 400

    trigger_words = (data.get('trigger_words') or '').strip()
    if len(trigger_words) > 2000:
        return jsonify({'error': 'Trigger words must be 2000 characters or less'}), 400
```

and add the field to the constructor call:

```python
    entry = KnowledgeEntry(
        property_id=property_id,
        category=category,
        label=label,
        value=value,
        trigger_words=trigger_words or None,
        sort_order=max_order + 1
    )
```

- [ ] **Step 4: Update `api_update_knowledge`**

In `routes.py`, inside `api_update_knowledge`, replace:

```python
    if 'value' in data:
        value = data['value'].strip()
        if not value:
            return jsonify({'error': 'Value is required'}), 400
        if len(value) > 2000:
            return jsonify({'error': 'Value must be 2000 characters or less'}), 400
        entry.value = value
```

with:

```python
    if 'value' in data:
        value = data['value'].strip()
        # entry.category is already updated above when the payload changed it.
        if not value and not entry.category.startswith('esc'):
            return jsonify({'error': 'Value is required'}), 400
        if len(value) > 2000:
            return jsonify({'error': 'Value must be 2000 characters or less'}), 400
        entry.value = value

    if 'trigger_words' in data:
        trigger_words = (data['trigger_words'] or '').strip()
        if len(trigger_words) > 2000:
            return jsonify({'error': 'Trigger words must be 2000 characters or less'}), 400
        entry.trigger_words = trigger_words or None
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_knowledge_trigger_words_api.py -q`
Expected: PASS, 6 tests.

- [ ] **Step 6: Commit**

```bash
git add routes.py tests/test_knowledge_trigger_words_api.py
git commit -m "feat(escalation): knowledge API accepts trigger_words, value optional for esc"
```

---

### Task 5: Put the topic names into UMI's prompt

**Files:**
- Modify: `services/context_filter.py:329-356` (`_filter_knowledge_entries`)
- Modify: `services/ai_service.py:854-866` (label derivation) and the `load_prompt(...)` call at `services/ai_service.py:910-931`
- Modify: `prompts/rich/guest_reply.txt` (after the CASE 3 block, ~line 59)
- Modify: `prompts/compact/guest_reply.txt` (after line 32)
- Test: `tests/test_escalation_prompt_injection.py` (create)

**Interfaces:**
- Consumes: escalation rows already present in the `knowledge_entries` list produced by `KnowledgeEntry.load_for_conversation_context` (Task 1).
- Produces: a new `escalation_topics_text` template variable (comma-joined labels, or `None`) rendered by both prompt tiers. No function signature changes and no call-site changes anywhere.

- [ ] **Step 1: Write the failing test**

Create `tests/test_escalation_prompt_injection.py`:

```python
"""UMI must escalate on the team's Eskalation topics — and must never see the
team's internal notes.

The topic labels are rendered into the guest-reply prompt so UMI catches a
paraphrase no trigger word matches. The note (`value`) stays team-only: it can
contain phone numbers and procedures that must not reach a guest.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db
from ChatBotAI.services.ai_service import AIService
from ChatBotAI.services.context_filter import ContextFilter


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


ESC_ENTRY = {
    'category': 'esc_access',
    'label': 'Aussperrung',
    'value': 'Hausmeister 0171-1234567 anrufen, Ersatzschlüssel im Büro',
    'trigger_words': 'ausgesperrt',
}


def _build(app, entries):
    service = AIService()
    return service._build_guest_reply_prompt(
        guest_profile={'name': 'Anna', 'language': 'de'},
        conversation_history=[],
        clean_latest='Ich komme nicht in die Wohnung',
        unanswered_count=1,
        knowledge_entries=entries,
    )


def test_topic_label_reaches_the_prompt(app):
    prompt = _build(app, [ESC_ENTRY])
    assert 'Aussperrung' in prompt


def test_internal_note_never_reaches_the_prompt(app):
    """Safety-critical: the note must not be renderable to a guest."""
    prompt = _build(app, [ESC_ENTRY])
    assert '0171-1234567' not in prompt
    assert 'Ersatzschlüssel' not in prompt


def test_no_escalation_entries_means_no_topic_line(app):
    prompt = _build(app, [{'category': 'general', 'label': 'WLAN', 'value': 'pw123'}])
    assert 'Aussperrung' not in prompt


def test_duplicate_labels_are_listed_once(app):
    prompt = _build(app, [ESC_ENTRY, dict(ESC_ENTRY)])
    assert prompt.count('Aussperrung') == 1


def test_context_filter_keeps_escalation_entries(app):
    """Relevance filtering must not drop topics — the list UMI sees has to be
    the same on every message, not whatever matched today's keywords."""
    entries = [ESC_ENTRY] + [
        {'category': 'general', 'label': f'Info {i}', 'value': f'text {i}'}
        for i in range(10)
    ]
    result = ContextFilter.filter(
        latest_message='Wo kann ich parken?',
        conversation_history=[],
        knowledge_entries=entries,
    )
    labels = [e['label'] for e in result.knowledge_entries]
    assert 'Aussperrung' in labels
```

Note: `ContextFilter.filter` short-circuits to empty context for pure gratitude messages
(`services/context_filter.py:167`). That path is left alone — a "danke, alles super"
message needs no escalation topics.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_escalation_prompt_injection.py -q`
Expected: FAIL — `test_topic_label_reaches_the_prompt` fails because escalation entries are stripped from the prompt today.

- [ ] **Step 3: Keep escalation rows out of relevance filtering**

In `services/context_filter.py`, at the top of `_filter_knowledge_entries`, split the
escalation rows off and re-attach them afterwards. Replace:

```python
        if not entries or not message_keywords:
            # No keywords extracted — return up to 3 fallback entries
            return cls._fallback_entries(entries, 3)

        scored = []
        for entry in entries:
            score = cls._score_entry(entry, message_keywords)
            if score > 0:
                scored.append((score, entry))

        if not scored:
            # No matches — return fallback entries
            return cls._fallback_entries(entries, 3)

        # Sort by score descending, take top N
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:max_entries]]
```

with:

```python
        # Escalation topics bypass relevance scoring and the cap: UMI must see
        # the same topic list on every message, not whatever happened to match
        # today's keywords. They are labels only — a handful of short strings.
        escalation, scorable = [], []
        for entry in entries:
            target = escalation if (entry.get('category') or '').startswith('esc') else scorable
            target.append(entry)

        if not scorable or not message_keywords:
            # No keywords extracted — return up to 3 fallback entries
            return escalation + cls._fallback_entries(scorable, 3)

        scored = []
        for entry in scorable:
            score = cls._score_entry(entry, message_keywords)
            if score > 0:
                scored.append((score, entry))

        if not scored:
            # No matches — return fallback entries
            return escalation + cls._fallback_entries(scorable, 3)

        # Sort by score descending, take top N
        scored.sort(key=lambda x: x[0], reverse=True)
        return escalation + [entry for _, entry in scored[:max_entries]]
```

- [ ] **Step 4: Derive the topic labels in the prompt builder**

In `services/ai_service.py`, in `_build_guest_reply_prompt`, the block that builds
`kb_for_template` currently reads:

```python
        # KB entries: top 3, exclude escalation, truncate value to 80 chars.
        kb_for_template = None
        if knowledge_entries:
            regular = [e for e in knowledge_entries if not (e.get('category') or '').startswith('esc')][:3]
```

Insert the label derivation immediately **above** that block, leaving the block itself
untouched:

```python
        # Escalation topics: LABELS ONLY. The team's internal note (`value`) may
        # hold phone numbers and procedures and must never reach the model — the
        # kb_for_template filter below keeps stripping the whole entry.
        escalation_topics_text = None
        if knowledge_entries:
            labels = [e.get('label') for e in knowledge_entries
                      if (e.get('category') or '').startswith('esc') and e.get('label')]
            if labels:
                escalation_topics_text = ", ".join(dict.fromkeys(labels))
```

Then add the variable to the `load_prompt(...)` call at the end of the method, next to
`knowledge_entries=kb_for_template`:

```python
            knowledge_entries=kb_for_template,
            escalation_topics_text=escalation_topics_text,
```

- [ ] **Step 5: Render it in both prompt tiers**

In `prompts/rich/guest_reply.txt`, after the CASE 3 bullet list (the line ending
`- Safety or emergencies: lockout, gas, medical, anything urgent.`) and before the
`Hard rule against guessing:` paragraph, insert:

```
{% if escalation_topics_text %}
- Team-defined escalation topics — always escalate when the message is about any of these: {{ escalation_topics_text }}.
{% endif %}
```

In `prompts/compact/guest_reply.txt`, after the line starting
`- Always escalate, even if data exists:` and before the `To escalate:` line, insert:

```
{% if escalation_topics_text %}
- Always escalate these team topics: {{ escalation_topics_text }}.
{% endif %}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_escalation_prompt_injection.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 7: Refresh the prompt snapshot test if it fails**

Run: `python -m pytest tests/test_compact_prompt_snapshot.py tests/test_prompt_loader.py -q`
Expected: PASS. Both prompts gained a conditional block that renders nothing when there
are no escalation entries, so a snapshot built without them should be unchanged. If a
snapshot does fail, read the diff first and confirm the only change is the new topic
line before updating the expected value.

- [ ] **Step 8: Commit**

```bash
git add services/ai_service.py services/context_filter.py prompts/rich/guest_reply.txt prompts/compact/guest_reply.txt tests/test_escalation_prompt_injection.py
git commit -m "feat(escalation): render team escalation topics into UMI's prompt"
```

---

### Task 6: Wissensdatenbank UI — the Auslöser-Wörter field

**Files:**
- Modify: `templates/chatbot/knowledge.html` (modal form ~lines 113-122, script tag line 134)
- Modify: `static/js/knowledge.js` (`CATEGORY_DESCRIPTIONS` ~line 70, `updateCategoryOptions` ~line 300, `openEditModal` ~line 353, `saveEntry` ~line 384, `renderEntries` ~line 208)
- Modify: `static/js/i18n.js` (German block ~line 396, English block ~line 979)

**Interfaces:**
- Consumes: the `trigger_words` field on the knowledge API from Task 4.
- Produces: no new JS API. New DOM ids `entryTriggerWords` and `entryTriggerRow`; new i18n keys `knowledge.triggers`, `knowledge.triggers.placeholder`, `knowledge.triggers.help`, `knowledge.value.internal`.

There is no JS test harness in this repo — this task is verified by hand in the browser,
which is how the other front-end work here is checked.

- [ ] **Step 1: Add the field to the modal and drop the blocking `required`**

In `templates/chatbot/knowledge.html`, replace the Information field block:

```html
            <div class="setting-item" style="flex-direction: column; align-items: stretch;">
                <label for="entryValue" data-i18n="knowledge.value">Information</label>
                <textarea id="entryValue" class="setting-textarea" rows="4" style="width: 100%;"
                    data-i18n-placeholder="knowledge.value.placeholder" placeholder="z.B. SunnyBeach2024" required maxlength="2000"></textarea>
            </div>
```

with (note: `required` removed — it is what blocks saving an escalation entry today, since
the field is hidden for those categories; the API still enforces it for the others):

```html
            <div class="setting-item" id="entryTriggerRow" style="flex-direction: column; align-items: stretch;">
                <label for="entryTriggerWords" data-i18n="knowledge.triggers">Auslöser-Wörter</label>
                <textarea id="entryTriggerWords" class="setting-textarea" rows="3" style="width: 100%;"
                    data-i18n-placeholder="knowledge.triggers.placeholder"
                    placeholder="ausgesperrt, locked out, komme nicht rein" maxlength="2000"></textarea>
                <small id="entryTriggerHelp" style="color: var(--text-secondary);" data-i18n="knowledge.triggers.help">Mit Komma trennen. Kommt eines dieser Wörter in einer Gästenachricht vor, wird der Chat eskaliert — auch wenn UMI nicht antwortet.</small>
            </div>

            <div class="setting-item" style="flex-direction: column; align-items: stretch;">
                <label for="entryValue" id="entryValueLabel" data-i18n="knowledge.value">Information</label>
                <textarea id="entryValue" class="setting-textarea" rows="4" style="width: 100%;"
                    data-i18n-placeholder="knowledge.value.placeholder" placeholder="z.B. SunnyBeach2024" maxlength="2000"></textarea>
            </div>
```

Bump the cache-buster on the same file, line 134: `js/knowledge.js') }}?v=8` becomes `?v=9`.

- [ ] **Step 2: Show the field only for escalation categories**

In `static/js/knowledge.js`, in `updateCategoryOptions`, replace:

```javascript
        const select = document.getElementById('entryCategory');
        const categoryRow = select.closest('.setting-item');
        const valueRow = document.getElementById('entryValue').closest('.setting-item');
        const lang = (typeof i18n !== 'undefined' && i18n.currentLanguage) || 'de';
```

with:

```javascript
        const select = document.getElementById('entryCategory');
        const categoryRow = select.closest('.setting-item');
        const valueRow = document.getElementById('entryValue').closest('.setting-item');
        const triggerRow = document.getElementById('entryTriggerRow');
        const valueLabel = document.getElementById('entryValueLabel');
        const lang = (typeof i18n !== 'undefined' && i18n.currentLanguage) || 'de';
        const t = (key, fallback) => (typeof i18n !== 'undefined' ? i18n.t(key) : fallback);
```

Then in the same method, in the corrections branch, hide the trigger row:

```javascript
        if (this.currentTab === 'corrections') {
            buildOptions(['correction']);
            categoryRow.style.display = 'none';
            valueRow.style.display = '';
            triggerRow.style.display = 'none';
            valueLabel.textContent = t('knowledge.value', 'Information');
            select.value = 'correction';
            return;
        }
```

and replace the two lines that hide the Information field for escalation:

```javascript
        // Hide Information field for escalation (category + label is enough)
        valueRow.style.display = this.currentTab === 'escalation' ? 'none' : '';
        categoryRow.style.display = '';
```

with:

```javascript
        // Escalation topics: trigger words decide what escalates, and the
        // Information field becomes a team-only note UMI never sees.
        const isEscalation = this.currentTab === 'escalation';
        triggerRow.style.display = isEscalation ? '' : 'none';
        valueRow.style.display = '';
        valueLabel.textContent = isEscalation
            ? t('knowledge.value.internal', 'Interne Notiz (nur fürs Team)')
            : t('knowledge.value', 'Information');
        categoryRow.style.display = '';
```

- [ ] **Step 3: Load and save the field**

In `openEditModal`, after the `entryValue` line:

```javascript
        document.getElementById('entryValue').value = entry.value;
        document.getElementById('entryTriggerWords').value = entry.trigger_words || '';
```

In `saveEntry`, add the field to the payload:

```javascript
        const data = {
            category: document.getElementById('entryCategory').value,
            label: document.getElementById('entryLabel').value.trim(),
            value: document.getElementById('entryValue').value.trim(),
            trigger_words: document.getElementById('entryTriggerWords').value.trim(),
            property_id: isProperty ? parseInt(document.getElementById('entryPropertyId').value) : null,
        };
```

- [ ] **Step 4: Show the trigger words on the entry card**

In `renderEntries`, replace the value line:

```javascript
                html += '<div style="color:var(--text-secondary);margin-top:4px;white-space:pre-line;">' + this.escapeHtml(entry.value) + '</div>';
```

with:

```javascript
                if (entry.trigger_words) {
                    html += '<div style="color:var(--text-secondary);margin-top:4px;font-size:12px;">'
                        + '<i class="fas fa-bell"></i> ' + this.escapeHtml(entry.trigger_words) + '</div>';
                }
                if (entry.value) {
                    html += '<div style="color:var(--text-secondary);margin-top:4px;white-space:pre-line;">' + this.escapeHtml(entry.value) + '</div>';
                }
```

- [ ] **Step 5: Reword the escalation category descriptions**

In `static/js/knowledge.js`, replace the seven `esc_*` entries in `CATEGORY_DESCRIPTIONS`:

```javascript
    esc_maintenance: 'Eskaliert bei Defekten & Reparaturen — kaputte Geräte, Heizung, Wasser, Strom.',
    esc_cleanliness: 'Eskaliert bei Sauberkeitsproblemen — unsaubere Unterkunft, Beschwerden zur Reinigung.',
    esc_noise: 'Eskaliert bei Lärm & Nachbarschaft — laute Nachbarn, Ruhestörung, Beschwerden.',
    esc_payment: 'Eskaliert bei Zahlungsproblemen — Rückerstattung, Kaution, falsche Beträge.',
    esc_access: 'Eskaliert bei Zugangsproblemen — Schlüssel verloren, Code funktioniert nicht, Aussperrung.',
    esc_emergency: 'Eskaliert bei echten Notfällen — Gesundheit, Sicherheit, Wasserschaden, dringend.',
    esc_other: 'Alles andere, was an das Team eskaliert werden muss.',
```

- [ ] **Step 6: Add the i18n keys**

In `static/js/i18n.js`, in the **German** block next to `'knowledge.value'`:

```javascript
        'knowledge.value.internal': 'Interne Notiz (nur fürs Team, UMI sieht das nie)',
        'knowledge.triggers': 'Auslöser-Wörter',
        'knowledge.triggers.placeholder': 'ausgesperrt, locked out, komme nicht rein',
        'knowledge.triggers.help': 'Mit Komma trennen. Kommt eines dieser Wörter in einer Gästenachricht vor, wird der Chat eskaliert — auch wenn UMI nicht antwortet.',
```

In the **English** block next to the English `'knowledge.value'`:

```javascript
        'knowledge.value.internal': 'Internal note (team only — UMI never sees this)',
        'knowledge.triggers': 'Trigger words',
        'knowledge.triggers.placeholder': 'locked out, ausgesperrt, cannot get in',
        'knowledge.triggers.help': 'Separate with commas. If one of these appears in a guest message, the chat is escalated — even when UMI is not replying.',
```

- [ ] **Step 7: Verify in the browser**

Start the app, open `/chatbot/knowledge?tab=escalation` and confirm, at desktop width and
at 390px:

1. "Eintrag hinzufügen" shows Kategorie, Bezeichnung, **Auslöser-Wörter**, and
   **Interne Notiz** — and saving with an empty note succeeds (this fails on `main`).
2. The Wissen tab shows **no** Auslöser-Wörter field and its Information label is
   unchanged.
3. A saved topic lists its trigger words with a bell icon on the card.
4. Editing a topic pre-fills the trigger words; deleting removes the row.
5. Switching the language to English relabels the new field and help text.

Hard-refresh once (the `?v=9` bump handles returning users).

- [ ] **Step 8: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: PASS. Report any failure rather than adjusting an unrelated test.

- [ ] **Step 9: Commit**

```bash
git add templates/chatbot/knowledge.html static/js/knowledge.js static/js/i18n.js
git commit -m "feat(escalation): Auslöser-Wörter field in the Wissensdatenbank"
```

---

## After the plan

The migration is **not** applied by this work. Hand the user these two steps:

1. Run `flask db upgrade` against production during a quiet moment — it adds one nullable
   column and inserts nine global rows, and is safe to re-run.
2. Open `/chatbot/knowledge?tab=escalation` and review the nine seeded topics with the
   team. The "Defekt / kaputt" row is the deliberate false-positive candidate — deleting
   it is a one-click decision that used to require a code change.

Until step 1 runs, the Eskalation area has no topics and the trigger-word path escalates
nothing, because the hardcoded list is gone. Do not deploy Task 3 to production without
running the migration in the same window.
