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
