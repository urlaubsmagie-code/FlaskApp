"""Tests for playtest-only auto-reply.

The playtest "Auto-Antwort" toggle must trigger an AI reply *only* inside the
playtest world, driven by a per-request flag — never by the global
``master_ai_enabled`` switch (which governs real guest chats). These tests pin
the route wiring: the flag controls whether the AI generator is called, and it
is called via ``generate_ai_response_for_conversation`` which does not consult
the master switch.

The router methods are monkeypatched so no real Ollama call happens.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, AISettings, Conversation, Guest, User
from ChatBotAI.services.message_router import MessageRouter


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    user = User(username='tester', display_name='Tester', is_admin=True)
    user.set_password('pw')
    db.session.add(user)
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id)
        s['_fresh'] = True
    return c


@pytest.fixture
def playtest_conv(app):
    guest = Guest(name='PT Gast', email='pt@test.local')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='playtest',
                        platform_id='playtest-xyz', subject='PT')
    db.session.add(conv)
    db.session.commit()
    return conv


@pytest.fixture
def calls(monkeypatch):
    """Monkeypatch router so no Ollama call happens; record what was invoked."""
    recorded = []

    def fake_incoming(self, **kwargs):
        recorded.append('incoming')
        return {'success': True, 'message_id': 1}

    def fake_owner(self, **kwargs):
        recorded.append('owner')
        return {'success': True, 'message_id': 3}

    def fake_generate(self, conversation_id, save_message=True):
        recorded.append(('generate', conversation_id))
        return {'success': True, 'message_id': 2, 'response': 'AI reply'}

    monkeypatch.setattr(MessageRouter, 'process_incoming_message', fake_incoming)
    monkeypatch.setattr(MessageRouter, 'process_owner_message', fake_owner)
    monkeypatch.setattr(MessageRouter, 'generate_ai_response_for_conversation', fake_generate)
    return recorded


def _send(client, conv_id, role='guest', auto_reply=False):
    return client.post(
        f'/chatbot/api/debug/playtest/{conv_id}/message',
        json={'content': 'Hallo', 'role': role, 'auto_reply': auto_reply},
    )


def test_auto_reply_true_triggers_ai_generation(client, playtest_conv, calls):
    resp = _send(client, playtest_conv.id, role='guest', auto_reply=True)
    assert resp.status_code == 200
    assert ('generate', playtest_conv.id) in calls


def test_auto_reply_false_does_not_trigger_ai(client, playtest_conv, calls):
    resp = _send(client, playtest_conv.id, role='guest', auto_reply=False)
    assert resp.status_code == 200
    assert not any(isinstance(c, tuple) and c[0] == 'generate' for c in calls)


def test_host_message_never_triggers_auto_reply(client, playtest_conv, calls):
    resp = _send(client, playtest_conv.id, role='host', auto_reply=True)
    assert resp.status_code == 200
    assert not any(isinstance(c, tuple) and c[0] == 'generate' for c in calls)


def test_auto_reply_marks_only_this_playtest_conv_auto_approve(client, playtest_conv, calls):
    # Auto-Antwort makes THIS playtest chat auto-send (auto_approve=True) so
    # escalation fires — without touching the global approval-queue setting or
    # any other conversation.
    before = AISettings.get('approval_queue_enabled', 'true')
    _send(client, playtest_conv.id, role='guest', auto_reply=True)
    refreshed = Conversation.query.get(playtest_conv.id)
    assert refreshed.auto_approve is True
    # Global setting untouched
    assert AISettings.get('approval_queue_enabled', 'true') == before


def test_auto_reply_off_leaves_auto_approve_untouched(client, playtest_conv, calls):
    _send(client, playtest_conv.id, role='guest', auto_reply=False)
    refreshed = Conversation.query.get(playtest_conv.id)
    assert refreshed.auto_approve is False


def test_auto_reply_ignores_master_ai_switch(client, playtest_conv, calls):
    # Global master switch OFF — real chats would not auto-respond. Playtest
    # auto-reply must STILL fire, proving it is an isolated world.
    AISettings.set('master_ai_enabled', 'false')
    db.session.commit()
    resp = _send(client, playtest_conv.id, role='guest', auto_reply=True)
    assert resp.status_code == 200
    assert ('generate', playtest_conv.id) in calls
