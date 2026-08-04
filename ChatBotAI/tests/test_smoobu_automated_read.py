"""Automated Smoobu templates (Buchungsbestätigung, Dein Check-in, …) must NOT
mark a conversation read. They are scheduled host→guest messages, not replies to
the guest, so treating them as "someone answered outside the app" hid unanswered
guest messages from the unread list (the missing_message Problem-Report bug).

A genuine manual host reply (empty subject) must still mark the chat read."""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, Conversation, Message
from ChatBotAI.services.smoobu_service import SmoobuService


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _unread_conv():
    """A Smoobu conversation with one unread guest message."""
    g = Guest(name='Krystian', email='k@example.com')
    db.session.add(g)
    db.session.flush()
    conv = Conversation(guest_id=g.id, platform='smoobu', platform_id='smoobu-700',
                        smoobu_reservation_id='700', is_read=False)
    db.session.add(conv)
    db.session.flush()
    db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                           content='Wann kann ich einchecken?',
                           platform_message_id='smoobu-700-10',
                           sent_at=datetime(2026, 3, 24, 10, 0, 0)))
    db.session.commit()
    return conv.id


def _sync_host_message(subject):
    s = SmoobuService(api_key='test-key')
    s.get_reservation = MagicMock(return_value={
        'id': 700, 'firstname': 'Krystian', 'lastname': 'K',
        'email': 'k@example.com', 'apartment': {'id': 999, 'name': 'A1'},
        'arrival': '2026-03-24', 'departure': '2026-03-25', 'adults': 1,
    })
    # The real thread holds both the guest's message (already stored, id 10) and
    # the new host message (id 55). total_items must exceed the known count or the
    # sync early-returns (smoobu_service.py:1109).
    s.get_all_reservation_messages = MagicMock(return_value={
        'total_items': 2,
        'messages': [
            {'id': 10, 'type': 1, 'message': 'Wann kann ich einchecken?',
             'subject': '', 'created_at': '2026-03-24 10:00:00'},
            {'id': 55, 'type': 2, 'message': 'Hallo Krystian, ...',
             'subject': subject, 'created_at': '2026-03-24 13:56:00'},
        ],
    })
    s.sync_conversation_messages('700', force=True)


def test_automated_message_keeps_conversation_unread(app):
    conv_id = _unread_conv()
    # Trailing space + template subject, exactly as Smoobu returns it.
    _sync_host_message('Buchungsbestätigung ')
    conv = Conversation.query.get(conv_id)
    assert conv.is_read is False, "automated template must not clear the guest's unread message"


def test_manual_reply_marks_conversation_read(app):
    conv_id = _unread_conv()
    _sync_host_message('')  # manual chat replies have no subject
    conv = Conversation.query.get(conv_id)
    assert conv.is_read is True, "a genuine host reply must still mark the chat read"
