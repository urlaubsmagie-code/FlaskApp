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
