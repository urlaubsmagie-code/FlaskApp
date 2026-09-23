"""Rule-based check-in auto-reply: fires on Booking's templated arrival message,
and on nothing else. Every guard here exists because tripping it would send a
canned message to a real guest at the wrong moment.
"""
from datetime import datetime, timedelta

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, AISettings, Conversation, Guest, Message
from ChatBotAI.services import quick_replies as qr


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def conv(app):
    g = Guest(name='Michael Kinne')
    db.session.add(g); db.session.commit()
    c = Conversation(guest_id=g.id, platform='smoobu', smoobu_reservation_id='42')
    db.session.add(c); db.session.commit()
    return c


def _msg(conv, text, age_minutes=0):
    m = Message(conversation_id=conv.id, sender_type='guest', content=text,
                sent_at=datetime.utcnow() - timedelta(minutes=age_minutes))
    db.session.add(m); db.session.commit()
    return m


@pytest.mark.parametrize('text', [
    'Ich möchte einen Check-in um 15:00 - 16:00 Uhr',
    'ich moechte einen checkin um 21:00 Uhr',
    'I would like to check-in at 14:00',
    'I will arrive at 16:00 tomorrow',
])
def test_recognises_the_booking_template(text):
    assert qr.is_checkin_time_request(text)


@pytest.mark.parametrize('text', [
    'Where can i park my car?',
    'Hallo, ist der Pool geöffnet?',
    'Wir kommen morgen an',           # no time -> not the template
    '',
])
def test_ignores_everything_else(text):
    assert not qr.is_checkin_time_request(text)


def test_disabled_by_default(app, conv):
    m = _msg(conv, 'Ich möchte einen Check-in um 15:00 Uhr')
    assert qr.should_autoreply(m, conv) is False


def test_fires_when_enabled(app, conv):
    AISettings.set('checkin_autoreply_enabled', 'true')
    m = _msg(conv, 'Ich möchte einen Check-in um 15:00 Uhr')
    assert qr.should_autoreply(m, conv) is True


def test_never_replies_to_an_old_backfilled_message(app, conv):
    """A re-sync replays months of history through the same path — this guard is
    what stops it blasting canned replies at guests whose stay ended long ago."""
    AISettings.set('checkin_autoreply_enabled', 'true')
    m = _msg(conv, 'Ich möchte einen Check-in um 15:00 Uhr', age_minutes=60 * 24 * 30)
    assert qr.should_autoreply(m, conv) is False


def test_never_talks_over_an_escalated_chat(app, conv):
    AISettings.set('checkin_autoreply_enabled', 'true')
    conv.escalated = True
    db.session.commit()
    m = _msg(conv, 'Ich möchte einen Check-in um 15:00 Uhr')
    assert qr.should_autoreply(m, conv) is False


def test_ignores_owner_messages(app, conv):
    AISettings.set('checkin_autoreply_enabled', 'true')
    m = _msg(conv, 'Ich möchte einen Check-in um 15:00 Uhr')
    m.sender_type = 'owner'
    db.session.commit()
    assert qr.should_autoreply(m, conv) is False


def test_custom_text_overrides_the_default(app):
    assert qr.checkin_autoreply_text() == qr.DEFAULT_TEXT_DE
    AISettings.set('checkin_autoreply_text', 'Check-in ab 16 Uhr.')
    assert qr.checkin_autoreply_text() == 'Check-in ab 16 Uhr.'
