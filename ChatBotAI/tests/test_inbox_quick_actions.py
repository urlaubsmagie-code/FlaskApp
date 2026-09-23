"""Inbox quick-actions backend: mark-unread endpoint.

The inbox ⋮ menu can flip a conversation back to unread. The existing
`/read` endpoint only advances the read cursor forward, so unread needs its
own route that rewinds the cursor and recomputes `is_read`.
"""

from datetime import datetime

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


def _read_conv_with_guest_msg():
    """A conversation already marked read, with one guest message."""
    guest = Guest(name='G', email='g@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', platform_id='r1',
                        status='active', ai_enabled=True, is_read=True,
                        last_message_at=datetime.utcnow())
    db.session.add(conv)
    db.session.flush()
    msg = Message(conversation_id=conv.id, sender_type='guest', content='hi',
                  sent_at=datetime.utcnow())
    db.session.add(msg)
    db.session.flush()
    conv.last_read_message_id = msg.id
    conv.is_read = True
    db.session.commit()
    return conv.id


def test_conversation_uses_its_smoobu_account_and_renders_safe_composer(client, app, monkeypatch):
    from types import SimpleNamespace
    from ChatBotAI.services import smoobu_service
    conv_id = _read_conv_with_guest_msg()
    checked = []

    def account_service(conversation):
        checked.append(conversation.id)
        return SimpleNamespace(is_configured=lambda: True)

    monkeypatch.setattr(smoobu_service, 'get_smoobu_service_for', account_service)
    response = client.get(f'/chatbot/conversation/{conv_id}')
    assert response.status_code == 200
    assert checked == [conv_id]
    html = response.get_data(as_text=True)
    assert 'smoobuConnected: true' in html
    assert '<dialog id="draftPreview"' not in html
    assert 'id="sendStatus"' in html


def test_mark_unread_sets_unread(client, app):
    cid = _read_conv_with_guest_msg()
    resp = client.post(f'/chatbot/api/conversations/{cid}/unread')
    assert resp.status_code == 200
    assert resp.get_json()['is_read'] is False
    assert Conversation.query.get(cid).is_read is False


def test_mark_unread_missing_conversation_404(client):
    resp = client.post('/chatbot/api/conversations/999999/unread')
    assert resp.status_code == 404


def test_inbox_renders_card_menu_button(client, app):
    """The inbox card must render the ⋮ menu button and the data attributes the
    menu reads — this catches Jinja errors in the new card markup."""
    _read_conv_with_guest_msg()
    resp = client.get('/chatbot/')
    assert resp.status_code == 200
    body = resp.data
    assert b'card-menu-btn' in body
    assert b'openCardMenu' in body
    assert b'data-last-sender' in body
    assert b'data-auto-respond' in body


def test_mark_read_after_unread_sticks(client, app):
    """Marking read again after mark-unread must stick.

    The /read fallback used conversation.messages.order_by(...) — a dynamic
    relationship that APPENDS to its own order_by=Message.sent_at, so it handed
    back the OLDEST message. The cursor landed on message #1 and the chat
    bounced straight back to unread; only "Alle gelesen" worked.
    """
    from datetime import timedelta
    guest = Guest(name='G', email='g2@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', platform_id='r2',
                        status='active', ai_enabled=True, is_read=False,
                        last_message_at=datetime.utcnow())
    db.session.add(conv)
    db.session.flush()
    now = datetime.utcnow()
    for n, when in (('old', now - timedelta(days=2)), ('new', now)):
        db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                               content=n, sent_at=when))
    db.session.commit()
    cid = conv.id

    resp = client.patch(f'/chatbot/api/conversations/{cid}/read', json={})
    assert resp.status_code == 200
    assert resp.get_json()['is_read'] is True
    assert db.session.get(Conversation, cid).is_read is True


def test_last_message_is_the_newest(client, app):
    """Conversation.last_message must not be poisoned by the same append bug."""
    from datetime import timedelta
    guest = Guest(name='G', email='g3@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', platform_id='r3',
                        status='active', last_message_at=datetime.utcnow())
    db.session.add(conv)
    db.session.flush()
    now = datetime.utcnow()
    for n, when in (('old', now - timedelta(days=2)), ('newest', now)):
        db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                               content=n, sent_at=when))
    db.session.commit()
    assert conv.last_message.content == 'newest'
