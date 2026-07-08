"""Route tests for playtest note-saving and log export."""

import os

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Conversation, Guest, Message, User
from ChatBotAI.services import playtest_export


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


def _make_playtest_conv(name='PT Gast'):
    guest = Guest(name=name, email=f'{name.replace(" ", "").lower()}@test.local')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='playtest',
                        platform_id=f'playtest-{name}', subject='PT')
    db.session.add(conv)
    db.session.flush()
    db.session.add(Message(conversation_id=conv.id, sender_type='guest', content='Hallo'))
    db.session.commit()
    return conv


def test_save_note_persists_to_sidecar(client, app):
    conv = _make_playtest_conv()
    resp = client.post(f'/chatbot/api/debug/playtest/{conv.id}/note',
                       json={'note': 'WiFi gut, Restaurant erfunden'})
    assert resp.status_code == 200
    assert resp.get_json().get('success') is True
    notes = playtest_export.load_notes(app.instance_path)
    assert notes[str(conv.id)] == 'WiFi gut, Restaurant erfunden'


def test_save_note_rejects_non_playtest(client, app):
    guest = Guest(name='Real', email='real@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', platform_id='smoobu-1')
    db.session.add(conv)
    db.session.commit()
    resp = client.post(f'/chatbot/api/debug/playtest/{conv.id}/note',
                       json={'note': 'should not save'})
    assert resp.status_code == 400


def test_export_writes_log_and_reports_count(client, app, tmp_path, monkeypatch):
    monkeypatch.setattr(playtest_export, '_PACKAGE_ROOT', str(tmp_path))
    _make_playtest_conv('Gast Eins')
    _make_playtest_conv('Gast Zwei')

    resp = client.post('/chatbot/api/debug/playtest/export')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['count'] == 2

    written = os.path.join(str(tmp_path), playtest_export.LOG_FILENAME)
    assert os.path.exists(written)
    with open(written, encoding='utf-8') as f:
        content = f.read()
    assert 'Gast Eins' in content
    assert 'Gast Zwei' in content
