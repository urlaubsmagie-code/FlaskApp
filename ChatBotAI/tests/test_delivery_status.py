"""Send confidence: a platform send that failed must be visibly undelivered.

Before this, a failed Smoobu send fell back to a plain local store — the bubble
looked identical to a delivered one, so nobody ever learned the guest didn't get
it. 9 such messages were sitting in prod.
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
    c.post('/chatbot/login', data={'username': 'tester', 'password': 'pw'},
           follow_redirects=True)
    return c


@pytest.fixture
def conversation(app):
    g = Guest(name='Vaghela Hardik')
    db.session.add(g)
    db.session.commit()
    conv = Conversation(guest_id=g.id, platform='smoobu', smoobu_reservation_id='42')
    db.session.add(conv)
    db.session.commit()
    return conv


def test_delivery_state_defaults_to_sent(app):
    assert Message(content='hi').delivery_state == 'sent'
    assert Message(content='hi', platform_message_id='smoobu-42-7').delivery_state == 'sent'


def test_failed_send_is_marked_undelivered(client, conversation):
    r = client.post(f'/chatbot/api/conversations/{conversation.id}/messages',
                    json={'content': 'Der Schlüssel liegt im Safe',
                          'delivery_failed': True})
    assert r.status_code == 201
    assert r.get_json()['delivery'] == 'failed'

    msg = Message.query.filter_by(conversation_id=conversation.id).first()
    assert msg.delivery_state == 'failed'
    assert msg.platform_message_id.startswith(Message.FAILED_PREFIX)


def test_normal_send_is_not_marked(client, conversation):
    r = client.post(f'/chatbot/api/conversations/{conversation.id}/messages',
                    json={'content': 'Alles klar!'})
    assert r.status_code == 201
    assert r.get_json()['delivery'] == 'sent'


def test_retry_refuses_a_message_that_did_not_fail(client, conversation):
    msg = Message(conversation_id=conversation.id, sender_type='owner',
                  content='schon zugestellt', platform_message_id='smoobu-42-7')
    db.session.add(msg)
    db.session.commit()

    r = client.post(f'/chatbot/api/messages/{msg.id}/retry')
    assert r.status_code == 400


def test_retry_clears_the_marker_on_success(client, conversation, monkeypatch):
    msg = Message(conversation_id=conversation.id, sender_type='owner',
                  content='Parkplatz ist hinter dem Haus',
                  platform_message_id=f'{Message.FAILED_PREFIX}abc')
    db.session.add(msg)
    db.session.commit()

    class FakeSmoobu:
        def is_configured(self):
            return True

        def send_message(self, reservation_id, content):
            return {'id': 99}

    import ChatBotAI.services.smoobu_service as ss
    monkeypatch.setattr(ss, 'get_smoobu_service_for', lambda conv: FakeSmoobu())

    r = client.post(f'/chatbot/api/messages/{msg.id}/retry')
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['delivery'] == 'sent'
    assert db.session.get(Message, msg.id).delivery_state == 'sent'


def test_retry_keeps_the_marker_when_smoobu_still_fails(client, conversation, monkeypatch):
    msg = Message(conversation_id=conversation.id, sender_type='owner',
                  content='WLAN-Passwort folgt',
                  platform_message_id=f'{Message.FAILED_PREFIX}def')
    db.session.add(msg)
    db.session.commit()

    class DeadSmoobu:
        def is_configured(self):
            return True

        def send_message(self, reservation_id, content):
            return None

    import ChatBotAI.services.smoobu_service as ss
    monkeypatch.setattr(ss, 'get_smoobu_service_for', lambda conv: DeadSmoobu())

    r = client.post(f'/chatbot/api/messages/{msg.id}/retry')
    assert r.status_code == 502
    assert db.session.get(Message, msg.id).delivery_state == 'failed'
