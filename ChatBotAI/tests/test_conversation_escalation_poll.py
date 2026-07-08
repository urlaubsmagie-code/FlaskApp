"""The message-poll endpoint must report the conversation's escalation state so
the client can show the escalation banner live (without a manual page refresh).

Today escalation that happens mid-session (auto-reply, background sync) only
shows after a hard refresh because the banner is rendered server-side at page
load. Surfacing `escalated` in the poll response lets the poller inject it.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Conversation, Guest, Message, User


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


def _conv(escalated):
    guest = Guest(name='G', email=f'g{int(escalated)}@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='playtest',
                        platform_id=f'pt-{escalated}', escalated=escalated)
    db.session.add(conv)
    db.session.flush()
    db.session.add(Message(conversation_id=conv.id, sender_type='guest', content='hi'))
    db.session.commit()
    return conv


def test_poll_reports_escalated_true(client):
    conv = _conv(True)
    resp = client.get(f'/chatbot/api/conversations/{conv.id}/messages?after=0')
    assert resp.status_code == 200
    assert resp.get_json()['escalated'] is True


def test_poll_reports_escalated_false(client):
    conv = _conv(False)
    resp = client.get(f'/chatbot/api/conversations/{conv.id}/messages?after=0')
    assert resp.status_code == 200
    assert resp.get_json()['escalated'] is False
