"""The Wissensdatenbank must not silently store the same fact twice.

Matching is an exact comparison of a normalised label within one scope
(category + property + street). Normalisation runs in Python: SQLite's LOWER()
is ASCII-only and would let 'Gaestekarte' and 'gaestekarte' both through once
umlauts are involved.
"""

from unittest.mock import patch

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, KnowledgeEntry, Property, User, Guest, Conversation, Message
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


def test_umlaut_case_variant_is_a_duplicate(app):
    existing = _entry(label='Gästekarte')
    hit = _find_duplicate_knowledge('faq', 'GÄSTEKARTE', None, None)
    assert hit is not None and hit.id == existing.id


def test_sharp_s_folds_to_ss(app):
    existing = _entry(label='Bahnhofstraße')
    hit = _find_duplicate_knowledge('faq', 'BAHNHOFSTRASSE', None, None)
    assert hit is not None and hit.id == existing.id


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


def test_409_payload_exposes_the_source(client, app):
    existing = _entry()
    existing.source = 'notion'
    db.session.commit()
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'faq', 'label': 'Gaestekarte', 'value': 'Etwas anderes',
    })
    assert resp.status_code == 409
    assert resp.get_json()['existing']['source'] == 'notion'


def test_create_allows_a_genuinely_new_entry(client, app):
    _entry()
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'faq', 'label': 'WLAN Passwort', 'value': 'sonne2026',
    })
    assert resp.status_code == 201
    assert KnowledgeEntry.query.count() == 2


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


def test_editing_value_of_a_legacy_duplicate_still_works(client, app):
    a = _entry(label='Gästekarte')
    b = _entry(label='gästekarte ')          # legacy twin, predates the guard
    resp = client.put(f'/chatbot/api/knowledge/{b.id}', json={
        'category': 'faq', 'label': 'gästekarte ', 'value': 'Neuer Text',
    })
    assert resp.status_code == 200
    assert KnowledgeEntry.query.get(b.id).value == 'Neuer Text'


def test_cannot_move_an_entry_into_a_category_that_already_has_that_label(client, app):
    _entry(category='nearby', label='Gästekarte')
    mover = _entry(category='faq', label='Gästekarte')
    resp = client.put(f'/chatbot/api/knowledge/{mover.id}', json={
        'category': 'nearby', 'label': 'Gästekarte', 'value': 'egal',
    })
    assert resp.status_code == 409
    assert KnowledgeEntry.query.get(mover.id).category == 'faq'


def test_cannot_move_an_entry_into_a_property_that_already_has_that_label(client, app):
    prop = Property(name='Haus 4')
    db.session.add(prop)
    db.session.commit()
    _entry(label='Gästekarte', property_id=prop.id)
    mover = _entry(label='Gästekarte', property_id=None)
    resp = client.put(f'/chatbot/api/knowledge/{mover.id}', json={
        'category': 'faq', 'label': 'Gästekarte', 'value': 'egal', 'property_id': prop.id,
    })
    assert resp.status_code == 409
    assert KnowledgeEntry.query.get(mover.id).property_id is None


def test_can_move_an_entry_into_a_property_where_the_label_is_free(client, app):
    prop = Property(name='Haus 4')
    db.session.add(prop)
    db.session.commit()
    mover = _entry(label='Gästekarte', property_id=None)
    resp = client.put(f'/chatbot/api/knowledge/{mover.id}', json={
        'category': 'faq', 'label': 'Gästekarte', 'value': 'egal', 'property_id': prop.id,
    })
    assert resp.status_code == 200
    assert KnowledgeEntry.query.get(mover.id).property_id == prop.id


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


def test_empty_extraction_returns_the_full_shape(client, app, owner_message):
    with _fake_ai([]):
        resp = client.post(f'/chatbot/api/messages/{owner_message.id}/extract-knowledge',
                           json={'scope': 'general'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['saved'] == 0
    assert body['skipped'] == 0
    assert body['entries'] == []


def test_room_scope_is_not_blocked_by_a_global_entry(client, app):
    prop = Property(name='Haus 4')
    db.session.add(prop)
    db.session.commit()
    g = Guest(name='Bea')
    db.session.add(g)
    db.session.commit()
    conv = Conversation(guest_id=g.id, platform='smoobu', property_id=prop.id)
    db.session.add(conv)
    db.session.commit()
    m = Message(conversation_id=conv.id, sender_type='owner', content='Die Gästekarte gibt es im Büro.')
    db.session.add(m)
    db.session.commit()
    _entry(label='Gästekarte', property_id=None)      # global entry, same label

    proposed = [{'category': 'faq', 'label': 'Gästekarte', 'value': 'Im Büro abholen'}]
    with _fake_ai(proposed):
        resp = client.post(f'/chatbot/api/messages/{m.id}/extract-knowledge',
                           json={'scope': 'room'})
    body = resp.get_json()
    assert body['saved'] == 1        # global row must not block a room-scoped save
    assert body['skipped'] == 0
    assert KnowledgeEntry.query.filter_by(property_id=prop.id, label='Gästekarte').count() == 1
