"""The knowledge API must accept escalation topics.

Before 2026-08-11 an Eskalation entry could not be saved: the form hides the
Information field but the API required a non-empty value. Escalation rows now
save without a note, and carry trigger words.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, KnowledgeEntry, User


@pytest.fixture
def client():
    app = create_app(config_map['testing'])
    with app.app_context():
        user = User(username='tester', display_name='Tester', is_admin=True)
        user.set_password('pw')
        db.session.add(user)
        db.session.commit()
        with app.test_client() as client:
            client.post('/chatbot/login',
                        data={'username': 'tester', 'password': 'pw'},
                        follow_redirects=True)
            yield client
        db.session.remove()
        db.drop_all()


def test_create_escalation_entry_without_value(client):
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'esc_access',
        'label': 'Aussperrung',
        'value': '',
        'trigger_words': 'ausgesperrt, locked out',
    })
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()['trigger_words'] == 'ausgesperrt, locked out'


def test_create_normal_entry_still_requires_value(client):
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'general',
        'label': 'WLAN',
        'value': '',
    })
    assert resp.status_code == 400
    assert 'Value is required' in resp.get_json()['error']


def test_blank_trigger_words_are_stored_as_null(client):
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'esc_noise',
        'label': 'Lärm',
        'value': '',
        'trigger_words': '   ',
    })
    assert resp.status_code == 201
    assert resp.get_json()['trigger_words'] is None


def test_trigger_words_over_2000_chars_are_rejected(client):
    resp = client.post('/chatbot/api/knowledge', json={
        'category': 'esc_noise',
        'label': 'Lärm',
        'value': '',
        'trigger_words': 'x' * 2001,
    })
    assert resp.status_code == 400


def test_update_sets_trigger_words(client):
    created = client.post('/chatbot/api/knowledge', json={
        'category': 'esc_access', 'label': 'Aussperrung', 'value': '',
        'trigger_words': 'ausgesperrt',
    }).get_json()

    resp = client.put(f"/chatbot/api/knowledge/{created['id']}",
                      json={'trigger_words': 'ausgesperrt, locked out'})
    assert resp.status_code == 200
    assert resp.get_json()['trigger_words'] == 'ausgesperrt, locked out'


def test_update_can_clear_the_internal_note_on_an_escalation_entry(client):
    created = client.post('/chatbot/api/knowledge', json={
        'category': 'esc_access', 'label': 'Aussperrung',
        'value': 'Hausmeister anrufen', 'trigger_words': 'ausgesperrt',
    }).get_json()

    resp = client.put(f"/chatbot/api/knowledge/{created['id']}", json={'value': ''})
    assert resp.status_code == 200
    assert resp.get_json()['value'] == ''
