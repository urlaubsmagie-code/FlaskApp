"""Unattended auto-respond must not fire on replayed history.

Full Smoobu syncs, webhook backfills and the email reconcile all push OLD
messages through process_incoming_message(), which cannot tell a live message
from a replayed one. Urgency triage has guarded against this since it started
push-notifying thousands of finished stays; auto-respond sat fifteen lines
below with no such guard, so enabling UMI plus one press of the full-sync
button would have written to guests whose stay ended two years ago.

An explicit auto_respond=True from the caller (the inbox "UMI-Antwort" button,
the test routes) is a person asking for a reply on a chosen message and stays
ungated.
"""

from datetime import datetime, timedelta

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, AISettings, Conversation, Guest, Message
from ChatBotAI.services import message_router as mr_mod


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def router(app, monkeypatch):
    """Router whose AI step only records that it was reached."""
    r = mr_mod.MessageRouter()
    calls = []

    def fake_generate(conversation, trigger_message):
        calls.append(trigger_message.id)
        return {'content': 'reply', 'message_id': -1}

    monkeypatch.setattr(r, '_generate_ai_response', fake_generate)
    monkeypatch.setattr(r, '_get_services', lambda: None)
    r.calls = calls
    AISettings.set('master_ai_enabled', 'true')
    db.session.commit()
    return r


def _conv(auto_respond=True):
    guest = Guest(name='G', email='g@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', platform_id='r1',
                        status='active', ai_enabled=True,
                        auto_respond=auto_respond)
    db.session.add(conv)
    db.session.commit()
    return conv


def _incoming(router, conv, age, auto_respond=False):
    """Mirrors how the Smoobu sync and the webhook call in: auto_respond=False,
    so the per-conversation flag is what decides. auto_respond=True is the
    explicit-request path."""
    return router.process_incoming_message(
        platform='smoobu',
        platform_conversation_id=conv.platform_id,
        sender_email='g@x.com',
        sender_name='G',
        message_content='Hallo, eine Frage zur Wohnung',
        sent_at=datetime.utcnow() - age,
        auto_respond=auto_respond,
    )


def test_fresh_message_still_gets_an_answer(router, app):
    conv = _conv()
    _incoming(router, conv, timedelta(minutes=5))
    assert router.calls, 'a live message must still be answered'


def test_replayed_history_is_not_answered(router, app):
    """The regression: a two-year-old message replayed by a full sync."""
    conv = _conv()
    _incoming(router, conv, timedelta(days=730))
    assert not router.calls, 'UMI answered a message from a finished stay'


def test_explicit_request_is_never_age_gated(router, app):
    """The ⋮ UMI-Antwort button on an old chat is a deliberate action."""
    conv = _conv(auto_respond=False)
    _incoming(router, conv, timedelta(days=730), auto_respond=True)
    assert router.calls, 'an explicitly requested reply must not be blocked'


def test_gate_matches_the_escalation_window(app):
    """One window for both unattended paths — they guard the same hazard."""
    assert mr_mod.MessageRouter.RECENT_WINDOW == timedelta(hours=48)
