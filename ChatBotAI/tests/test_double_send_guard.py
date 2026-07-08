"""Guard against double-delivering a reply to the guest (Smoobu send has no id,
so a retry / re-click can send the same text twice). Tests the shared helper
`_recent_duplicate_owner_reply`."""
from datetime import datetime, timedelta

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, Conversation, Message
from ChatBotAI.routes import _recent_duplicate_owner_reply


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _conv():
    g = Guest(name='Karina')
    db.session.add(g); db.session.flush()
    c = Conversation(guest_id=g.id, platform='smoobu', smoobu_reservation_id='R1')
    db.session.add(c); db.session.commit()
    return c


def _owner_msg(conv_id, content, when):
    m = Message(conversation_id=conv_id, sender_type='owner', content=content,
                sent_at=when, is_processed=True)
    db.session.add(m); db.session.commit()
    return m


def test_blocks_identical_recent_reply(app):
    c = _conv()
    _owner_msg(c.id, 'Hallo Karina, pro Wohnung gibt es nur eine Gästekarte.', datetime.utcnow())
    # Same text (even with whitespace/case noise) within window -> blocked.
    assert _recent_duplicate_owner_reply(c.id, '  Hallo Karina, pro Wohnung gibt es nur eine Gästekarte.  ')


def test_allows_different_reply(app):
    c = _conv()
    _owner_msg(c.id, 'Hallo Karina, pro Wohnung gibt es nur eine Gästekarte.', datetime.utcnow())
    assert not _recent_duplicate_owner_reply(c.id, 'Guten Tag, wie kann ich helfen?')


def test_allows_identical_reply_after_window(app):
    c = _conv()
    _owner_msg(c.id, 'Vielen Dank!', datetime.utcnow() - timedelta(seconds=200))
    # Older than the 120s window -> a genuine repeat is allowed through.
    assert not _recent_duplicate_owner_reply(c.id, 'Vielen Dank!', within_seconds=120)


def test_scoped_to_conversation(app):
    c1, c2 = _conv(), _conv()
    _owner_msg(c1.id, 'Danke!', datetime.utcnow())
    # Same text in a DIFFERENT conversation must not block.
    assert not _recent_duplicate_owner_reply(c2.id, 'Danke!')
