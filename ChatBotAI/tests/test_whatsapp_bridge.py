"""WhatsApp bridge: webhook auth, ingestion, and the guarded send path."""

import os
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, mock_open, patch

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, Conversation, Message, User


SECRET = 'test-bridge-secret'


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


@pytest.fixture(autouse=True)
def bridge_secret():
    old = os.environ.get('WHATSAPP_BRIDGE_SECRET')
    os.environ['WHATSAPP_BRIDGE_SECRET'] = SECRET
    yield
    if old is None:
        os.environ.pop('WHATSAPP_BRIDGE_SECRET', None)
    else:
        os.environ['WHATSAPP_BRIDGE_SECRET'] = old


def _post(client, payload, secret=SECRET):
    headers = {'X-Bridge-Secret': secret} if secret is not None else {}
    return client.post('/chatbot/webhook/whatsapp', json=payload, headers=headers)


def test_webhook_rejects_wrong_secret(client):
    r = _post(client, {'jid': '4915112345678@s.whatsapp.net', 'text': 'hi'}, secret='nope')
    assert r.status_code == 403


def test_webhook_rejects_missing_secret(client):
    r = _post(client, {'jid': '4915112345678@s.whatsapp.net', 'text': 'hi'}, secret=None)
    assert r.status_code == 403


def test_webhook_rejects_when_no_secret_configured(client):
    """An unset secret must close the endpoint, not open it — it is reachable
    without a login on a public tunnel."""
    os.environ.pop('WHATSAPP_BRIDGE_SECRET', None)
    r = _post(client, {'jid': '4915112345678@s.whatsapp.net', 'text': 'hi'}, secret='')
    assert r.status_code == 403


def test_webhook_creates_conversation_and_message(client, app):
    jid = '4915112345678@s.whatsapp.net'
    r = _post(client, {'jid': jid, 'phone': '4915112345678', 'name': 'Janine',
                       'text': 'Hallo, kommt ein Hund mit?', 'message_id': 'ABC123'})
    assert r.status_code == 200

    guest = Guest.query.filter_by(whatsapp_id=jid).one()
    assert guest.name == 'Janine'
    conv = Conversation.query.filter_by(platform='whatsapp').one()
    assert conv.guest_id == guest.id
    msg = Message.query.filter_by(conversation_id=conv.id).one()
    assert msg.sender_type == 'guest'
    assert 'Hund' in msg.content


def test_webhook_is_idempotent_on_message_id(client, app):
    payload = {'jid': '4915199999999@s.whatsapp.net', 'phone': '4915199999999',
               'text': 'zweimal', 'message_id': 'DUP1'}
    _post(client, payload)
    _post(client, payload)
    conv = Conversation.query.filter_by(platform='whatsapp').one()
    assert Message.query.filter_by(conversation_id=conv.id).count() == 1


def test_webhook_requires_jid_and_text(client):
    assert _post(client, {'jid': '', 'text': 'hi'}).status_code == 400
    assert _post(client, {'jid': '491@s.whatsapp.net', 'text': '  '}).status_code == 400


def test_reply_sends_and_stores_only_on_success(client, app):
    _post(client, {'jid': '4915177777777@s.whatsapp.net', 'phone': '4915177777777',
                   'text': 'Frage', 'message_id': 'Q1'})
    conv_id = Conversation.query.filter_by(platform='whatsapp').one().id

    # A failed send must leave no owner message behind.
    with patch('ChatBotAI.services.whatsapp_service.WhatsAppService.send_message',
               return_value=None), \
         patch('ChatBotAI.services.whatsapp_service.WhatsAppService.is_configured',
               return_value=True):
        r = client.post(f'/chatbot/api/whatsapp/reply/{conv_id}', json={'message': 'Antwort'})
    assert r.status_code == 502
    assert Message.query.filter_by(conversation_id=conv_id, sender_type='owner').count() == 0

    with patch('ChatBotAI.services.whatsapp_service.WhatsAppService.send_message',
               return_value={'success': True, 'message_id': 'S1'}), \
         patch('ChatBotAI.services.whatsapp_service.WhatsAppService.is_configured',
               return_value=True):
        r = client.post(f'/chatbot/api/whatsapp/reply/{conv_id}', json={'message': 'Antwort'})
    assert r.status_code == 200
    assert Message.query.filter_by(conversation_id=conv_id, sender_type='owner').count() == 1


def test_reply_blocks_duplicate(client, app):
    _post(client, {'jid': '4915166666666@s.whatsapp.net', 'phone': '4915166666666',
                   'text': 'Frage', 'message_id': 'Q2'})
    conv_id = Conversation.query.filter_by(platform='whatsapp').one().id

    with patch('ChatBotAI.services.whatsapp_service.WhatsAppService.send_message',
               return_value={'success': True, 'message_id': 'S2'}) as send, \
         patch('ChatBotAI.services.whatsapp_service.WhatsAppService.is_configured',
               return_value=True):
        client.post(f'/chatbot/api/whatsapp/reply/{conv_id}', json={'message': 'Gleiche'})
        r = client.post(f'/chatbot/api/whatsapp/reply/{conv_id}', json={'message': 'Gleiche'})

    assert r.get_json().get('duplicate_skipped') is True
    assert send.call_count == 1   # the guest was messaged once, not twice


def test_existing_guest_matched_by_phone_gets_whatsapp_id(client, app):
    """A Smoobu guest who writes on WhatsApp must get the JID backfilled, or
    replies have no address to send to."""
    db.session.add(Guest(name='Bestandsgast', phone='4915155555555'))
    db.session.commit()

    jid = '4915155555555@s.whatsapp.net'
    _post(client, {'jid': jid, 'phone': '4915155555555', 'text': 'Hi', 'message_id': 'M9'})

    guest = Guest.query.filter_by(phone='4915155555555').one()
    assert guest.whatsapp_id == jid


def test_whatsapp_shows_in_the_normal_inbox_and_badge(client, app):
    """WhatsApp chats live in "Alle" with everything else (the quarantine was
    lifted 2026-09-10); the WhatsApp button still narrows to them."""
    _post(client, {'jid': '4915144444444@s.whatsapp.net', 'phone': '4915144444444',
                   'text': 'Im normalen Posteingang', 'message_id': 'Q1'})
    conv_id = Conversation.query.filter_by(platform='whatsapp').one().id

    ids = [c['id'] for c in client.get('/chatbot/api/conversations').get_json()['conversations']]
    assert conv_id in ids

    ids = [c['id'] for c in
           client.get('/chatbot/api/conversations?channel=whatsapp').get_json()['conversations']]
    assert ids == [conv_id]

    assert client.get('/chatbot/api/conversations/last-updated').get_json()['unread'] == 1


def test_reply_typed_on_the_phone_is_stored_as_owner(client, app):
    """The bridge used to drop every fromMe message, so UMI showed only the
    guest's half of the chat."""
    jid = '4915133333333@s.whatsapp.net'
    now = int(time.time())
    _post(client, {'jid': jid, 'phone': '4915133333333', 'name': 'Janine',
                   'text': 'Wann ist Check-in?', 'message_id': 'G1', 'timestamp': now})
    conv = Conversation.query.filter_by(platform='whatsapp').one()
    assert conv.is_read is False

    r = _post(client, {'jid': jid, 'phone': '4915133333333', 'name': None, 'from_me': True,
                       'text': 'Ab 15 Uhr', 'message_id': 'P1', 'timestamp': now + 60})
    assert r.status_code == 200

    owner = Message.query.filter_by(conversation_id=conv.id, sender_type='owner').one()
    assert owner.content == 'Ab 15 Uhr'
    assert owner.sent_via_app is False
    # Stored as naive UTC like every other message, not the server's local time.
    assert owner.sent_at == datetime.fromtimestamp(now + 60, timezone.utc).replace(tzinfo=None)
    db.session.refresh(conv)
    assert conv.is_read is True                              # handled on the phone
    assert Guest.query.filter_by(whatsapp_id=jid).one().name == 'Janine'   # not renamed


def test_phone_reply_dedups_on_message_id_and_against_umi_send(client, app):
    jid = '4915122222222@s.whatsapp.net'
    _post(client, {'jid': jid, 'phone': '4915122222222', 'text': 'Frage', 'message_id': 'G2'})
    conv_id = Conversation.query.filter_by(platform='whatsapp').one().id

    with patch('ChatBotAI.services.whatsapp_service.WhatsAppService.send_message',
               return_value={'success': True, 'message_id': 'S9'}), \
         patch('ChatBotAI.services.whatsapp_service.WhatsAppService.is_configured',
               return_value=True):
        client.post(f'/chatbot/api/whatsapp/reply/{conv_id}', json={'message': 'Aus UMI'})

    # An echo of UMI's own send, and a bridge retry of a phone reply.
    _post(client, {'jid': jid, 'from_me': True, 'text': 'Aus UMI', 'message_id': 'S9'})
    _post(client, {'jid': jid, 'from_me': True, 'text': 'Vom Handy', 'message_id': 'P2'})
    _post(client, {'jid': jid, 'from_me': True, 'text': 'Vom Handy', 'message_id': 'P2'})

    contents = sorted(m.content for m in
                      Message.query.filter_by(conversation_id=conv_id, sender_type='owner'))
    assert contents == ['Aus UMI', 'Vom Handy']


def test_chat_started_from_the_phone_creates_the_conversation(client, app):
    jid = '163170186000001@lid'
    r = _post(client, {'jid': jid, 'phone': None, 'from_me': True,
                       'text': 'Hallo, hier ist Urlaubsmagie', 'message_id': 'P3'})
    assert r.status_code == 200

    conv = Conversation.query.filter_by(platform='whatsapp').one()
    msg = Message.query.filter_by(conversation_id=conv.id).one()
    assert msg.sender_type == 'owner'
    assert Guest.query.filter_by(whatsapp_id=jid).one().phone is None


QR = 'data:image/png;base64,AAAA'
SVC = 'ChatBotAI.services.whatsapp_service'


def test_status_route_never_exposes_the_pairing_qr(client):
    """/api/whatsapp/status is open to every logged-in user; the QR links a device."""
    with patch(f'{SVC}.WhatsAppService.get_status',
               return_value={'connected': False, 'qr_pending': True, 'qr': QR}):
        data = client.get('/chatbot/api/whatsapp/status').get_json()
    assert 'qr' not in data and data['qr_pending'] is True


def test_pairing_route_gives_admins_the_qr(client):
    with patch(f'{SVC}.WhatsAppService.get_status', return_value={'connected': False, 'qr': QR}):
        assert client.get('/chatbot/api/whatsapp/pairing').get_json()['qr'] == QR


def test_pairing_and_start_are_admin_only(app):
    # Own test, no admin request first: the app fixture keeps one app context open,
    # and Flask-Login caches the loaded user in `g` for that context — an earlier
    # admin request in the same test would make the staff request look like admin.
    staff = User(username='staff', display_name='Staff', is_admin=False)
    staff.set_password('pw')
    db.session.add(staff)
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(staff.id)
        s['_fresh'] = True
    with patch(f'{SVC}.subprocess.Popen') as popen:
        assert c.get('/chatbot/api/whatsapp/pairing').status_code == 403
        assert c.post('/chatbot/api/whatsapp/start').status_code == 403
        assert c.post('/chatbot/api/whatsapp/reconnect').status_code == 403
    assert popen.call_count == 0


def test_start_launches_node_only_when_the_bridge_is_down(client):
    with patch.dict(os.environ, {'WHATSAPP_BRIDGE_URL': 'http://127.0.0.1:3001'}), \
         patch(f'{SVC}._whatsapp_service', None), \
         patch(f'{SVC}.open', mock_open(), create=True), \
         patch(f'{SVC}.subprocess.Popen', return_value=MagicMock(pid=4242)) as popen:
        with patch(f'{SVC}.WhatsAppService.get_status', return_value={'connected': True}):
            r = client.post('/chatbot/api/whatsapp/start')
        assert r.get_json()['already_running'] is True
        assert popen.call_count == 0

        with patch(f'{SVC}.WhatsAppService.get_status', return_value={'connected': False, 'error': 'refused'}):
            r = client.post('/chatbot/api/whatsapp/start')
            assert r.get_json() == {'started': True, 'pid': 4242}
            args, kwargs = popen.call_args
            assert args[0][-1] == 'index.js'
            assert kwargs['env']['WHATSAPP_BRIDGE_SECRET'] == SECRET
            assert kwargs['env']['WHATSAPP_BRIDGE_PORT'] == '3001'

            # A second click inside the cooldown must not start a second bridge.
            r = client.post('/chatbot/api/whatsapp/start')
            assert r.get_json() == {'started': False, 'starting': True}
            assert popen.call_count == 1


def test_settings_page_renders_the_whatsapp_block_when_configured(client):
    with patch.dict(os.environ, {'WHATSAPP_BRIDGE_URL': 'http://127.0.0.1:3001'}), \
         patch(f'{SVC}.WhatsAppService.get_status', return_value={'connected': True}):
        r = client.get('/chatbot/settings')
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'id="whatsappIntegration"' in html and 'startWhatsAppBridge' in html
    assert 'id="whatsappStatusBadge"' in html   # sidebar badge next to "AI Online"


def test_sidebar_badge_absent_when_whatsapp_is_not_configured(client):
    with patch.dict(os.environ):
        os.environ.pop('WHATSAPP_BRIDGE_URL', None)
        html = client.get('/chatbot/settings').get_data(as_text=True)
    assert 'id="whatsappStatusBadge"' not in html


def test_lid_addressed_chat_is_ingested_without_a_fake_phone(client, app):
    """WhatsApp now addresses chats as `<id>@lid`. The id is NOT a phone number
    — storing it as one creates a junk guest that can never match the Smoobu
    guest with the same real number."""
    jid = '163170186444913@lid'
    r = _post(client, {'jid': jid, 'phone': None, 'name': 'LID-Gast',
                       'text': 'Hallo per LID', 'message_id': 'LID1'})
    assert r.status_code == 200

    guest = Guest.query.filter_by(whatsapp_id=jid).one()
    assert guest.phone is None
    conv = Conversation.query.filter_by(platform='whatsapp').one()
    assert Message.query.filter_by(conversation_id=conv.id).one().content == 'Hallo per LID'


def test_voice_note_is_shown_to_the_team_but_kept_from_umi(client, app, tmp_path):
    import base64
    from ChatBotAI.models import pending_guest_question
    app.instance_path = str(tmp_path)   # never write into the real instance/ folder
    jid = '4915177777777@s.whatsapp.net'
    _post(client, {'jid': jid, 'phone': '4915177777777', 'text': 'Wo ist der Schlüssel?', 'message_id': 'Q1',
                   'timestamp': 1800000000})
    r = _post(client, {'jid': jid, 'phone': '4915177777777', 'text': '[Sprachnachricht]', 'message_id': 'V1',
                       'timestamp': 1800000060,
                       'media': {'mimetype': 'audio/ogg; codecs=opus', 'data': base64.b64encode(b'OggS-fake').decode()}})
    assert r.status_code == 200

    conv = Conversation.query.filter_by(platform='whatsapp').one()
    voice = Message.query.filter_by(platform_message_id='whatsapp-V1').one()
    assert voice.media['kind'] == 'audio'
    assert voice.is_processed   # memory extraction skipped it
    assert client.get(voice.media['url']).data == b'OggS-fake'

    # The pending question is the text, not the voice note.
    _, text = pending_guest_question(conv)
    assert text == 'Wo ist der Schlüssel?'


def test_media_never_served_as_html(client, app, tmp_path):
    import base64
    app.instance_path = str(tmp_path)
    _post(client, {'jid': '4915166666666@s.whatsapp.net', 'text': '[Dokument: x.html]', 'message_id': 'H1',
                   'media': {'mimetype': 'text/html', 'data': base64.b64encode(b'<script>').decode()}})
    msg = Message.query.filter_by(platform_message_id='whatsapp-H1').one()
    r = client.get(msg.media['url'])
    assert r.mimetype == 'application/octet-stream'
    assert 'attachment' in r.headers['Content-Disposition']


def test_reconnect_passes_the_bridge_verdict_through(client):
    """The bridge owns the rules (10-min gap, paired, not connected); UMI relays its answer."""
    refused = MagicMock(status_code=409, json=lambda: {'error': 'Zu früh – manuell nur alle 10 Minuten'})
    ok = MagicMock(status_code=200, json=lambda: {'reconnecting': True})
    with patch.dict(os.environ, {'WHATSAPP_BRIDGE_URL': 'http://127.0.0.1:3001'}),          patch(f'{SVC}._whatsapp_service', None):
        with patch(f'{SVC}.requests.post', return_value=ok) as post:
            r = client.post('/chatbot/api/whatsapp/reconnect')
            assert r.status_code == 200 and r.get_json() == {'reconnecting': True}
            assert post.call_args[0][0] == 'http://127.0.0.1:3001/reconnect'
            assert post.call_args[1]['headers']['X-Bridge-Secret'] == SECRET
        with patch(f'{SVC}.requests.post', return_value=refused):
            r = client.post('/chatbot/api/whatsapp/reconnect')
            assert r.status_code == 409 and '10 Minuten' in r.get_json()['error']
